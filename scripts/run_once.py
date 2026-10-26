"""Run the pipeline once from the command line and print the result.

    .venv/bin/python scripts/run_once.py "Medtronic" "MHS enrolment" [--web] [--red-team]
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from warmpath import agents, db

db.init()
args = [a for a in sys.argv[1:] if not a.startswith("--")]
run = agents.new_run(args[0], args[1] if len(args) > 1 else "", "--web" in sys.argv, "--red-team" in sys.argv)
asyncio.run(agents.execute(run))
for e in run["trace"]:
    print(f"{e['t']:>6}s  {e['type']:<10} {e.get('agent', e.get('tool', ''))} {e.get('detail', e.get('summary', ''))} {e.get('args', '')}")
print(json.dumps({k: run[k] for k in ("status", "usage", "cost_usd", "duration_s")}, indent=1))
print(json.dumps(run["result"], indent=1)[:6000])
