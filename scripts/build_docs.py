"""Build report.html and slides.html from the measured runs and the screenshots.

Numbers come from docs/benchmark*.json (written by scripts/benchmark.py), so
the report says exactly what the runs measured. Images are embedded as base64,
so each HTML file stands alone.

    .venv/bin/python scripts/build_docs.py
"""
from __future__ import annotations

import base64
import html
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from warmpath import config  # noqa: E402

DOCS = ROOT / "docs"
SHOTS = DOCS / "screenshots"
REPO_URL = "https://github.com/Cameronhogg2004/warmpath"
RUNS_PER_USER_MONTH = 40

bench = json.loads((DOCS / "benchmark.json").read_text())
effort_med = json.loads((DOCS / "benchmark_effort_medium.json").read_text())

lean = [r for r in bench if not r["web"] and not r["red_team"] and r["status"] == "done"]
web = [r for r in bench if r["web"] and r["status"] == "done"]
red = next(r for r in bench if r["red_team"])
lean_by = {r["company"]: r for r in lean}


def img(name: str, alt: str, cls: str = "shot") -> str:
    p = SHOTS / name
    mime = "image/png" if p.suffix == ".png" else "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode()
    return f'<img class="{cls}" alt="{html.escape(alt)}" src="data:{mime};base64,{data}"/>'


def svg() -> str:
    return (DOCS / "architecture.svg").read_text()


def t(r, k):
    return r["usage"]["total"][k]


def money(v, d=4):
    return f"${v:,.{d}f}"


def avg(rows, f):
    return st.mean(f(r) for r in rows) if rows else 0


A = {
    "n_lean": len(lean),
    "lean_cost": avg(lean, lambda r: r["cost_usd"]),
    "lean_in": avg(lean, lambda r: t(r, "input")),
    "lean_cached": avg(lean, lambda r: t(r, "cached")),
    "lean_out": avg(lean, lambda r: t(r, "output")),
    "lean_reason": avg(lean, lambda r: t(r, "reasoning")),
    "lean_time": avg(lean, lambda r: r["duration_s"]),
    "lean_people": avg(lean, lambda r: len(r["introducers"])),
    "web_cost": avg(web, lambda r: r["cost_usd"]),
    "web_in": avg(web, lambda r: t(r, "input")),
    "web_out": avg(web, lambda r: t(r, "output")),
    "web_time": avg(web, lambda r: r["duration_s"]),
    "web_people": avg(web, lambda r: len(r["introducers"])),
    "web_searches": avg(web, lambda r: t(r, "web_searches")),
}
A["user_month"] = A["lean_cost"] * RUNS_PER_USER_MONTH
A["cache_share"] = A["lean_cached"] / A["lean_in"] if A["lean_in"] else 0
web_same = [lean_by[r["company"]] for r in web if r["company"] in lean_by]
A["web_lean_cost_same"] = avg(web_same, lambda r: r["cost_usd"])
A["web_ratio"] = A["web_cost"] / A["web_lean_cost_same"] if A["web_lean_cost_same"] else 0

med_rows = [r for r in effort_med if r["status"] == "done"]
low_same = [lean_by[r["company"]] for r in med_rows if r["company"] in lean_by]
A["med_cost"] = avg(med_rows, lambda r: r["cost_usd"])
A["med_out"] = avg(med_rows, lambda r: t(r, "output"))
A["med_reason"] = avg(med_rows, lambda r: t(r, "reasoning"))
A["med_time"] = avg(med_rows, lambda r: r["duration_s"])
A["low_cost_same"] = avg(low_same, lambda r: r["cost_usd"])
A["low_out_same"] = avg(low_same, lambda r: t(r, "output"))
A["low_reason_same"] = avg(low_same, lambda r: t(r, "reasoning"))
A["low_time_same"] = avg(low_same, lambda r: r["duration_s"])


def people(r, limit=6):
    return ", ".join(p[0] for p in r["introducers"][:limit]) or "none"


def run_table(rows):
    out = ['<table class="data"><tr><th>Company</th><th>Mode</th><th class="n">Input</th><th class="n">Cached</th>'
           '<th class="n">Output</th><th class="n">Reasoning</th><th class="n">Requests</th><th class="n">Tool calls</th>'
           '<th class="n">Web searches</th><th class="n">Time</th><th class="n">Cost</th><th class="n">Verified people</th></tr>']
    for r in rows:
        u = r["usage"]["total"]
        out.append(f"<tr><td>{html.escape(r['company'])}</td><td>{'web' if r['web'] else 'lean'}{' · red team' if r['red_team'] else ''}</td>"
                   f"<td class='n'>{u['input']:,}</td><td class='n'>{u['cached']:,}</td><td class='n'>{u['output']:,}</td>"
                   f"<td class='n'>{u['reasoning']:,}</td><td class='n'>{u['requests']}</td><td class='n'>{u['tool_calls']}</td>"
                   f"<td class='n'>{u['web_searches']}</td><td class='n'>{r['duration_s']:.0f}s</td>"
                   f"<td class='n'>{money(r['cost_usd'])}</td><td class='n'>{len(r['introducers'])}</td></tr>")
    out.append("</table>")
    return "".join(out)


def stage_table(r):
    rows = []
    for k in ("scout", "verifier", "writer", "total"):
        u = r["usage"].get(k)
        if not u:
            continue
        rows.append(f"<tr><td>{'<b>Total</b>' if k == 'total' else k.title()}</td><td class='n'>{u['input']:,}</td>"
                    f"<td class='n'>{u['cached']:,}</td><td class='n'>{u['output']:,}</td><td class='n'>{u['reasoning']:,}</td>"
                    f"<td class='n'>{u['requests']}</td><td class='n'>{money(u['cost_usd'], 5)}</td></tr>")
    return ('<table class="data"><tr><th>Agent</th><th class="n">Input</th><th class="n">Cached input</th>'
            '<th class="n">Output</th><th class="n">of which reasoning</th><th class="n">Requests</th><th class="n">Cost</th></tr>'
            + "".join(rows) + "</table>")


exec((ROOT / "scripts" / "report_text.py").read_text(encoding="utf-8"))   # defines REPORT and SLIDES

(ROOT / "report.html").write_text(REPORT, encoding="utf-8")   # noqa: F821
(ROOT / "slides.html").write_text(SLIDES, encoding="utf-8")   # noqa: F821
print("wrote report.html and slides.html")
print(json.dumps({k: round(v, 6) if isinstance(v, float) else v for k, v in A.items()}, indent=1))
