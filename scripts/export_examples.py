"""Copy a few real runs into data/example_runs.json, so a fresh clone opens with results.

    .venv/bin/python scripts/export_examples.py <run_id> [<run_id> ...]
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from warmpath import db

runs = []
for rid in sys.argv[1:]:
    r = db.get_run(rid)
    r["example"] = True
    runs.append(r)
(ROOT / "data" / "example_runs.json").write_text(json.dumps(runs, indent=1), encoding="utf-8")
print(f"saved {len(runs)} runs")
