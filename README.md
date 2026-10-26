# WarmPath

**Find the Yale person who can actually introduce you.**

WarmPath is an AI agent app for a university corporate-engagement office. You give it a company
and a goal (for example *"Medtronic: recruit clinicians into the MHS program"*). It finds the
Yale people with a **current, direct, documented** tie to that company: named at the Yale site
of an active trial the company sponsors, a recent co-author of company scientists, or holder
of a chair the company endowed. It then drafts the request for an introduction. Every claim
links to its public source. A claim that cannot be traced to a source is dropped, and email
addresses are never guessed.

Three agents (Scout → Verifier → Writer) run on `gpt-6-luna`, with checks in code between
them. The app shows each run's agent trace, its token use (input, cached input, output) and
its cost.

---

## Run it (about 3 minutes)

You need **Python 3.10 or newer** and an internet connection. ClinicalTrials.gov and
Europe PMC are public and need no key.

**1. Get the code**

```bash
git clone <this repo's URL> warmpath
cd warmpath
```

**2. Add a key.** WarmPath reads `.env` from **this folder first, then the folder above it**,
so a `.env` in the parent folder (for example `submissions/.env`) works without copying. It
uses `PORTKEY_API_KEY` if that is set, and otherwise `OPENAI_API_KEY`. If you have neither in
a `.env` yet:

```bash
cp .env.example .env      # then paste your key into .env
```

**3. Install and start** (macOS / Linux):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

On Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

**4. Open http://127.0.0.1:8077**

The first screen shows a recorded example run. Type a company (try **Medtronic**, **Pfizer**
or **Boehringer Ingelheim**), pick a goal chip and press **Find introducers**. A run takes
about 20 to 40 seconds and costs about a fifth of a cent.

If port 8077 is taken, use another one: `PORT=8090 .venv/bin/python app.py`.

## What to try

| Where | What it shows |
|---|---|
| **New search** | A briefing: ranked introducers, the tie behind each one with source links, the Yale directory email when there is one, a draft intro request, and anything the checks dropped. The right-hand column shows the live agent trace and a token and cost table for the run. |
| **Run the red-team test** (link under the form) | The real agents run against a planted paper record with a prompt injection and two fake email addresses. The Safety page and the trace show the injection being removed; the briefing contains neither fake email nor the fake person. |
| **Safety → Send a prompt-injection request** | The request is refused before any model call: 0 tokens, $0. |
| **History** | Every run, with its tokens, cost and time. |
| **Cost** | Average cost per run, per user per month, and at 100 and 10,000 users, with a per-agent cost bar for every run. |

## Tests (no API key needed)

```bash
.venv/bin/python -m pytest -q
```

There are 20 tests. They cover:

- prompt injection and off-limits requests being refused;
- the poisoned fixture being fully neutralised;
- unsourced emails and links being stripped;
- the daily budget;
- the cost formula;
- the code checks that drop invented sources, people the source does not name, and out-of-date ties.

## Command-line tools

```bash
.venv/bin/python scripts/run_once.py "Medtronic" "MHS recruitment"          # one run, printed
.venv/bin/python scripts/run_once.py "Pfizer" "Sponsored research" --web    # with web search
.venv/bin/python scripts/run_once.py "Thermo Fisher Scientific" "" --red-team
.venv/bin/python scripts/benchmark.py                                       # the runs behind the report
```

## How it works

```
request ─► guards ─► Scout ─► code checks ─► Verifier ─► Writer ─► code checks ─► briefing
                     │ tools
                     ├─ company_profile      data/companies.json (35 companies, aliases)
                     ├─ find_trials          ClinicalTrials.gov API v2 (active trials at Yale sites)
                     ├─ find_copublications  Europe PMC (Yale + company authors, last 3 years)
                     ├─ search_faculty       data/faculty.csv.gz (4,788 YSM faculty, public directory)
                     └─ web_search           optional, OpenAI native tool
```

- **Scout** (`gpt-6-luna`, tools): gathers candidates. Each one must cite source ids (`S1`, `S2`…) that the tools issued.
- **Code checks**: a candidate is dropped if a cited source does not exist, does not name the person, or is out of date (a paper more than 3 years old, a chair whose title does not name the company). Web-search claims are re-fetched, and the page must name both the person and the company.
- **Verifier** (`gpt-6-luna`, no tools): an LLM judge. It reads each claim next to the exact source text and rules on whether the tie is supported and current.
- **Writer** (`gpt-6-luna`, no tools): ranks the people who are left and drafts the intro request. Afterwards, code removes any email or link that no source contains.

Limits:

| What | Limit |
|---|---|
| Scout model requests | 14 |
| Scout tool calls | 16 |
| Calls to any one tool | 6 |
| Repeated calls with the same arguments | Blocked |
| Tokens | Per-agent caps |
| Run time | 4 minutes |
| Daily budget | `$2` (`WARMPATH_DAILY_BUDGET_USD`) |
| Runs per minute | 6 |

## Project layout

```
app.py                 FastAPI server and API
warmpath/config.py     .env loading (repo folder, then parent), model, prices, limits
warmpath/agents.py     the three agents, prompts, the pipeline, the code checks
warmpath/tools.py      the Scout's tools and the evidence ledger
warmpath/guards.py     request guard, injection sanitiser, email/link stripping, budget
warmpath/db.py         SQLite: runs, safety events, faculty directory, API cache
static/                the web app (plain HTML/CSS/JS, no build step)
data/                  faculty sample, company list, red-team fixture, example runs
tests/                 pytest suite
scripts/               run_once.py, benchmark.py
report.html            the report (self-contained)
slides.html            the slides (reveal.js from a CDN)
docs/                  screenshots, architecture diagram, benchmark results
```

## Data

| File | What it is |
|---|---|
| `data/faculty.csv.gz` | Name, title, department, research summary, profile URL and email of the 4,788 faculty listed in the public Yale School of Medicine directory, as scraped in September 2026. An email appears only where the directory page printed it; none are inferred. |
| `data/companies.json` | 35 companies with their common aliases (e.g. Medtronic / Covidien) and Connecticut presence. |
| `data/fixtures/poisoned_papers.json` | Planted test records, used only by the red-team test. |
| `data/example_runs.json` | Real recorded runs, loaded on first start so the app is not empty. |

`data/warmpath.db` is created on first start; delete it to reset.

## Troubleshooting

| Problem | Fix |
|---|---|
| Yellow banner: "No API key found" | Put `PORTKEY_API_KEY` or `OPENAI_API_KEY` in `.env` here or one folder up, then restart. |
| "Today's budget … is used up" | Raise `WARMPATH_DAILY_BUDGET_USD` in `.env`, or delete `data/warmpath.db`. |
| A run says ClinicalTrials.gov or Europe PMC could not be reached | The run continues without that source. Check your connection and run it again. |
