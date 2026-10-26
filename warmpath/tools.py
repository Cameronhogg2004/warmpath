"""The scout's tools, and the evidence ledger they write to.

Every fact a tool returns gets a source id (S1, S2...) and is kept, with its
URL and text, in the run's ledger. Later stages may only cite those ids, so a
claim with no source behind it cannot survive to the briefing.

Sources (all public, no key needed):
* ClinicalTrials.gov API v2: active trials a company sponsors at a Yale site.
* Europe PMC: recent papers with both a Yale and a company author.
* data/faculty.csv.gz: a sample of the Yale School of Medicine faculty directory.
* data/companies.json: names, aliases and Connecticut presence of 35 companies.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx
from pydantic_ai import RunContext

from . import config, db, guards

COMPANIES = json.loads((config.DATA / "companies.json").read_text(encoding="utf-8"))
YALE_SITE = re.compile(r"yale|smilow|new haven", re.I)
ACTIVE = "RECRUITING,ACTIVE_NOT_RECRUITING,NOT_YET_RECRUITING,ENROLLING_BY_INVITATION"


@dataclass
class Source:
    id: str
    kind: str          # trial | paper | directory | company | web
    url: str
    title: str
    text: str          # what the tool showed the model, used for grounding checks
    year: int | None = None


@dataclass
class Deps:
    run_id: str
    company: str
    aliases: list[str]
    ledger: dict[str, Source] = field(default_factory=dict)
    calls: dict[str, int] = field(default_factory=dict)
    seen_args: set[str] = field(default_factory=set)
    emit: Callable[[dict], None] = lambda event: None
    # Red-team mode: the paper search returns a poisoned fixture instead.
    poisoned: bool = False

    def add(self, kind: str, url: str, title: str, text: str, year: int | None = None) -> Source:
        for s in self.ledger.values():
            if s.url == url and s.kind == kind:
                return s
        src = Source(f"S{len(self.ledger) + 1}", kind, url, title, text, year)
        self.ledger[src.id] = src
        return src


def _gate(ctx: RunContext[Deps], tool: str, args: dict) -> str | None:
    """Per-tool call cap and repeat detection. Returns a refusal or None."""
    d = ctx.deps
    key = tool + json.dumps(args, sort_keys=True).lower()
    if key in d.seen_args:
        d.emit({"type": "guard", "detail": f"Repeated call to {tool} with the same arguments blocked."})
        return "You already called this tool with these arguments. Use the earlier result."
    d.calls[tool] = d.calls.get(tool, 0) + 1
    if d.calls[tool] > config.PER_TOOL_CALL_LIMIT:
        d.emit({"type": "guard", "detail": f"{tool} hit its limit of {config.PER_TOOL_CALL_LIMIT} calls."})
        return f"Limit reached: {tool} can be called {config.PER_TOOL_CALL_LIMIT} times per run. Finish with what you have."
    d.seen_args.add(key)
    return None


def _clean(ctx: RunContext[Deps], tool: str, text: str) -> str:
    clean, hits = guards.sanitize(text)
    for h in hits:
        ctx.deps.emit({"type": "safety", "detail": f"Injection-like text removed from {tool} result: {h[:160]!r}"})
        db.log_safety(ctx.deps.run_id, "injection_removed", f"{tool}: {h}")
    return clean


def _get_json(url: str, params: dict) -> dict:
    key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    cached = db.cache_get(key)
    if cached:
        return json.loads(cached)
    last = None
    for attempt in range(3):
        try:
            r = httpx.get(url, params=params, timeout=25,
                          headers={"User-Agent": "WarmPath/1.0 (university class project)"})
            r.raise_for_status()
            db.cache_put(key, r.text)
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"{type(last).__name__}: {last}")


def _emit_call(ctx, tool, args, summary):
    ctx.deps.emit({"type": "tool", "tool": tool, "args": args, "summary": summary})


# --- Tools --------------------------------------------------------------------------

def company_profile(ctx: RunContext[Deps], name: str) -> str:
    """The company's other names (aliases), sector, headquarters and Connecticut presence.

    Call this first. Searches below use the aliases automatically.

    Args:
        name: The company name as the user gave it.
    """
    if refusal := _gate(ctx, "company_profile", {"name": name}):
        return refusal
    low = name.lower()
    hit = next((c for c in COMPANIES if low in c["name"].lower()
                or any(low == a.lower() for a in c["aliases"])), None)
    if not hit:
        _emit_call(ctx, "company_profile", {"name": name}, "not in the sample; searching by name")
        return json.dumps({"found": False, "note": "Not in the local sample. Searches will use the name as given."})
    ctx.deps.aliases = hit["aliases"]
    src = ctx.deps.add("company", hit["website"], hit["name"], json.dumps(hit))
    _emit_call(ctx, "company_profile", {"name": name}, f"{hit['name']} ({src.id})")
    return json.dumps({"source_id": src.id, **hit})


def find_trials(ctx: RunContext[Deps]) -> str:
    """Active clinical trials the company sponsors or collaborates on with a Yale site.

    Returns trial id, title, status, start year and the people named at the
    Yale site (often none: many sponsors list only a call centre).
    """
    if refusal := _gate(ctx, "find_trials", {}):
        return refusal
    trials, seen = [], set()
    try:
        for alias in ctx.deps.aliases[:2]:
            data = _get_json("https://clinicaltrials.gov/api/v2/studies", {
                "query.spons": alias, "query.locn": "Yale", "filter.overallStatus": ACTIVE,
                "pageSize": 25, "sort": "StartDate:desc", "format": "json"})
            for st in data.get("studies", []):
                p = st["protocolSection"]
                nct = p["identificationModule"]["nctId"]
                if nct in seen:
                    continue
                seen.add(nct)
                cl = p.get("contactsLocationsModule", {})
                yale_people = []
                for loc in cl.get("locations", []):
                    if YALE_SITE.search(loc.get("facility", "") + " " + loc.get("city", "")):
                        for c in loc.get("contacts", []):
                            if c.get("name") and "call" not in c["name"].lower():
                                yale_people.append(f"{c['name']} ({c.get('role', 'contact').lower().replace('_', ' ')})")
                officials = [f"{o['name']} ({o.get('affiliation', '')})" for o in cl.get("overallOfficials", [])
                             if o.get("name") and "call" not in o["name"].lower()]
                start = p.get("statusModule", {}).get("startDateStruct", {}).get("date", "")
                sc = p.get("sponsorCollaboratorsModule", {})
                sponsor = sc.get("leadSponsor", {}).get("name", "")
                collaborators = [c.get("name", "") for c in sc.get("collaborators", [])][:3]
                trials.append({"nct": nct, "title": p["identificationModule"]["briefTitle"][:140],
                               "status": p["statusModule"]["overallStatus"], "start": start[:7],
                               "sponsor": sponsor, "collaborators": collaborators,
                               "yale_site_people": yale_people[:4], "overall_officials": officials[:2]})
    except RuntimeError as exc:
        _emit_call(ctx, "find_trials", {}, f"error: {exc}")
        return f"ClinicalTrials.gov could not be reached ({exc}). Continue without trials."
    named = [t for t in trials if t["yale_site_people"]]
    keep = (named + [t for t in trials if not t["yale_site_people"]])[:10]
    out = []
    for t in keep:
        text = _clean(ctx, "find_trials", json.dumps(t))
        t = json.loads(text)
        src = ctx.deps.add("trial", f"https://clinicaltrials.gov/study/{t['nct']}", t["title"], text,
                           int(t["start"][:4]) if t["start"][:4].isdigit() else None)
        out.append({"source_id": src.id, **t})
    _emit_call(ctx, "find_trials", {}, f"{len(trials)} active trials at Yale sites, {len(named)} name a Yale person")
    return guards.untrusted(json.dumps({"active_trials_at_yale": len(trials), "trials": out}))


def _poisoned_papers() -> dict:
    return json.loads((config.DATA / "fixtures" / "poisoned_papers.json").read_text(encoding="utf-8"))


def find_copublications(ctx: RunContext[Deps]) -> str:
    """Recent papers (last 3 years) with at least one Yale author and one company author.

    Returns title, year, PubMed id, the Yale authors and the company authors.
    """
    if refusal := _gate(ctx, "find_copublications", {}):
        return refusal
    first = config.current_year() - config.RECENT_YEARS
    alias_q = " OR ".join(f'AFF:"{a}"' for a in ctx.deps.aliases[:3])
    try:
        data = (_poisoned_papers() if ctx.deps.poisoned else _get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            {"query": f'AFF:"Yale" AND ({alias_q}) AND PUB_YEAR:[{first} TO {config.current_year()}]',
             "format": "json", "pageSize": 25, "resultType": "core", "sort": "P_PDATE_D desc"}))
    except RuntimeError as exc:
        _emit_call(ctx, "find_copublications", {}, f"error: {exc}")
        return f"Europe PMC could not be reached ({exc}). Continue without papers."
    alias_re = re.compile("|".join(re.escape(a) for a in ctx.deps.aliases[:3]), re.I)
    papers = []
    for x in data.get("resultList", {}).get("result", []):
        yale, company = [], []
        for a in x.get("authorList", {}).get("author", []):
            affs = " ".join(y.get("affiliation", "") for y in
                            a.get("authorAffiliationDetailsList", {}).get("authorAffiliation", []))
            if "yale" in affs.lower():
                yale.append(a.get("fullName", ""))
            elif alias_re.search(affs):
                company.append(f"{a.get('fullName', '')} ({affs[:90]})")
        if not yale or not company:
            continue
        papers.append({"title": x.get("title", "")[:160], "year": x.get("pubYear"),
                       "pmid": x.get("pmid") or x.get("id"), "journal": x.get("journalTitle", ""),
                       "yale_authors": yale[:6], "company_authors": company[:3]})
        if len(papers) == 10:
            break
    out = []
    for p in papers:
        text = _clean(ctx, "find_copublications", json.dumps(p))
        p = json.loads(text)
        src = ctx.deps.add("paper", f"https://pubmed.ncbi.nlm.nih.gov/{p['pmid']}/", p["title"], text,
                           int(p["year"]) if str(p["year"]).isdigit() else None)
        out.append({"source_id": src.id, **p})
    _emit_call(ctx, "find_copublications", {}, f"{data.get('hitCount', len(papers))} hits, {len(papers)} with Yale and company authors")
    return guards.untrusted(json.dumps({"papers": out}))


def search_faculty(ctx: RunContext[Deps], query: str) -> str:
    """Search the Yale School of Medicine faculty directory by name, title or topic.

    Use a person's name to confirm their Yale role, or the company name to
    find named chairs and titles that mention it (e.g. "Boehringer Ingelheim
    Professor").

    Args:
        query: A name ("John Forrest") or words in a title or research summary.
    """
    if refusal := _gate(ctx, "search_faculty", {"query": query}):
        return refusal
    rows = db.faculty_search(query, limit=6)
    out = []
    for r in rows:
        text = json.dumps({k: r[k] for k in ("name", "title", "departments", "email")})
        src = ctx.deps.add("directory", r["profile_url"], r["name"], text)
        out.append({"source_id": src.id, "name": r["name"], "title": r["title"][:220],
                    "departments": r["departments"][:120]})
    _emit_call(ctx, "search_faculty", {"query": query}, f"{len(out)} people")
    return json.dumps({"people": out} if out else {"people": [], "note": "No match in the directory sample."})


SCOUT_TOOLS = [company_profile, find_trials, find_copublications, search_faculty]
