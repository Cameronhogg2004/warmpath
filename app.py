"""WarmPath: find the Yale person who can actually introduce you.

Run:  .venv/bin/python app.py   then open http://127.0.0.1:8077
"""
from __future__ import annotations

import asyncio
import os

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from warmpath import agents, config, db, guards

db.init()
app = FastAPI(title="WarmPath")
app.mount("/static", StaticFiles(directory=config.STATIC), name="static")


class RunRequest(BaseModel):
    company: str
    goal: str = ""
    web: bool = False
    red_team: bool = False


@app.get("/")
def index():
    return FileResponse(config.STATIC / "index.html")


@app.get("/api/status")
def status():
    return {"provider": config.provider(), "model": config.MODEL_NAME,
            "budget_usd": config.DAILY_BUDGET_USD, "spent_today_usd": round(db.spent_today(), 5),
            "prices": {"input": config.PRICE_INPUT, "cached_input": config.PRICE_CACHED_INPUT,
                       "output": config.PRICE_OUTPUT, "web_search_call": config.PRICE_WEB_SEARCH_CALL}}


@app.post("/api/runs")
async def start_run(req: RunRequest):
    try:
        company, goal = guards.check_request(req.company, req.goal)
        agents.model()          # fails clearly if no key is set
        guards.check_budget()
    except guards.Refused as exc:
        db.log_safety(None, "request_refused", f"{req.company!r} / {req.goal!r}: {exc}")
        return {"refused": True, "error": str(exc)}
    run = agents.new_run(company, goal, req.web, poisoned=req.red_team)
    asyncio.create_task(agents.execute(run))
    return {"id": run["id"]}


@app.get("/api/runs")
def runs():
    return db.list_runs()


@app.get("/api/runs/{run_id}")
def run(run_id: str):
    live = agents.RUNS.get(run_id)
    if live and live["status"] == "running":
        return live
    saved = db.get_run(run_id)
    if not saved:
        raise HTTPException(404, "No such run")
    return saved


@app.get("/api/safety")
def safety():
    return db.safety_events()


@app.get("/api/stats")
def stats():
    live = [r for r in db.list_runs(500) if r["status"] == "done"]
    if not live:
        return {"runs": 0}
    n = len(live)
    tot = lambda k: sum(r["usage"].get("total", {}).get(k, 0) for r in live)
    avg_cost = sum(r["cost_usd"] for r in live) / n
    per_user_month = avg_cost * RUNS_PER_USER_MONTH
    return {"runs": n, "avg_cost_usd": avg_cost, "avg_duration_s": sum(r["duration_s"] for r in live) / n,
            "avg_input": tot("input") / n, "avg_cached": tot("cached") / n, "avg_output": tot("output") / n,
            "avg_reasoning": tot("reasoning") / n, "runs_per_user_month": RUNS_PER_USER_MONTH,
            "per_user_month_usd": per_user_month,
            "users_100_month_usd": per_user_month * 100, "users_10000_month_usd": per_user_month * 10_000}


# A corporate engagement officer researches about two companies a working day.
RUNS_PER_USER_MONTH = 40

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8077))
    print(f"\n  WarmPath is running: open http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
