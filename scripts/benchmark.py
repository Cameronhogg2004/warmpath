"""Run the real pipeline on several companies, lean and with web search, and
save the measured tokens, cost and results to docs/benchmark.json.

    .venv/bin/python scripts/benchmark.py
"""
import asyncio, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from warmpath import agents, db

GOAL = "Recruit clinicians and scientists into the Master of Health Science (MHS) program"
LEAN = ["Medtronic", "Pfizer", "Boehringer Ingelheim", "Thermo Fisher Scientific", "AstraZeneca", "Merck", "Cigna", "Arvinas"]
WEB = ["Medtronic", "Pfizer", "Cigna"]


async def one(company, web, poisoned=False, goal=GOAL):
    run = agents.new_run(company, goal, web, poisoned)
    await agents.execute(run)
    res = run["result"]
    row = {"id": run["id"], "company": company, "web": web, "red_team": poisoned, "status": run["status"],
           "duration_s": run["duration_s"], "cost_usd": run["cost_usd"], "usage": run["usage"],
           "introducers": [(p["name"], p["strength"], [t["type"] for t in p["ties"]]) for p in res.get("introducers", [])],
           "dropped": res.get("dropped", []), "error": res.get("error"),
           "safety": [e["detail"] for e in run["trace"] if e["type"] in ("safety", "guard")]}
    print(json.dumps({k: row[k] for k in ("company", "web", "status", "duration_s", "cost_usd", "introducers")}), flush=True)
    return row


async def main():
    db.init()
    rows = []
    if "--red-team-only" in sys.argv:
        path = ROOT / "docs" / "benchmark.json"
        rows = [r for r in json.loads(path.read_text()) if not r["red_team"]]
        rows.append(await one("Thermo Fisher Scientific", False, True,
                              "Red-team test: the paper search returns a planted, poisoned record"))
        path.write_text(json.dumps(rows, indent=1))
        return
    if "--web-only" in sys.argv:
        # Re-run the web-search rows and replace them in docs/benchmark.json.
        path = ROOT / "docs" / "benchmark.json"
        rows = [r for r in json.loads(path.read_text()) if not r["web"]]
        for c in WEB:
            rows.insert(len([r for r in rows if not r["red_team"]]), await one(c, True))
        path.write_text(json.dumps(rows, indent=1))
        return
    if "--effort" in sys.argv:
        # Ablation: same companies at a different reasoning effort, saved separately.
        from warmpath import config
        config.REASONING_EFFORT = sys.argv[sys.argv.index("--effort") + 1]
        for c in ["Medtronic", "Boehringer Ingelheim", "Thermo Fisher Scientific"]:
            rows.append(await one(c, False))
        (ROOT / "docs" / f"benchmark_effort_{config.REASONING_EFFORT}.json").write_text(json.dumps(rows, indent=1))
        return
    for c in LEAN:
        rows.append(await one(c, False))
    for c in WEB:
        rows.append(await one(c, True))
    rows.append(await one("Thermo Fisher Scientific", False, True,
                          "Red-team test: the paper search returns a planted, poisoned record"))
    (ROOT / "docs" / "benchmark.json").write_text(json.dumps(rows, indent=1))

asyncio.run(main())
