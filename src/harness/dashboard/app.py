"""FastAPI dashboard for reviewing persisted Plan C evidence on localhost."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from harness.persistence.store import ExperimentStore, ReviewState


def _timeline(trajectory_path: str | None) -> list[dict[str, Any]]:
    if not trajectory_path or not Path(trajectory_path).is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in Path(trajectory_path).read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("record_type") == "initial_observation":
            events.append({"kind": "experiment_start", "time": entry["observation"]["simulation_time"]})
            continue
        if entry.get("record_type") != "step":
            continue
        result = entry["result"]
        events.append({"kind": "robot_action", "time": result["simulation_time"], "action": entry["action"]})
        for event in result.get("events", []):
            events.append({"kind": "environmental_event", "time": result["simulation_time"], "event": event})
        if result.get("done"):
            events.append({"kind": "termination", "time": result["simulation_time"]})
    return events


def build_pair_view(store: ExperimentStore, pair_id: str) -> dict[str, Any] | None:
    pair = store.get_pair(pair_id)
    if not pair:
        return None
    isaac, reactor = store.get_experiment(pair["isaac_run_id"]), store.get_experiment(pair["reactor_run_id"])
    return {
        "pair": pair,
        "isaac": isaac,
        "reactor": reactor,
        "isaac_artifacts": store.artifacts_for("experiment", pair["isaac_run_id"]),
        "reactor_artifacts": store.artifacts_for("experiment", pair["reactor_run_id"]),
        "pair_artifacts": store.artifacts_for("pair", pair_id),
        "isaac_timeline": _timeline(isaac["trajectory_path"] if isaac else None),
        "reactor_timing_note": "Reactor chunks/sequences are shown independently; no precise clock synchronization is claimed.",
        "authority": {
            "isaac": "PHYSICS-GROUNDED SIMULATION",
            "reactor": "NEURAL WORLD VISUAL EVIDENCE",
        },
    }


class ReviewUpdate(BaseModel):
    review_state: ReviewState


def create_app(store: ExperimentStore) -> FastAPI:
    app = FastAPI(title="Physical AI Failure Harness", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """<!doctype html><title>Physical AI Failure Harness</title>
<style>body{font:15px system-ui;margin:2rem;max-width:1200px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:.6rem;text-align:left}.tag{font-weight:700}.isaac{color:#165c2e}.reactor{color:#6650a4}a{color:#145da0}</style>
<h1>Plan C comparison dashboard</h1><p>Read-only development view. <span class=isaac>PHYSICS-GROUNDED SIMULATION</span> is the reference; <span class=reactor>NEURAL WORLD VISUAL EVIDENCE</span> is not physics ground truth.</p>
<table><thead><tr><th>Pair / run</th><th>Task / scenario</th><th>Isaac outcome</th><th>Reactor visual outcome</th><th>Comparison</th><th>Timestamp</th></tr></thead><tbody id=rows></tbody></table>
<script>fetch('/api/pairs').then(r=>r.json()).then(rows=>document.querySelector('#rows').innerHTML=rows.map(p=>`<tr><td><a href='/pairs/${p.pair_id}'>${p.pair_id}</a></td><td>${p.task}<br><small>${p.scenario_id||''}</small></td><td>${p.physics_failure_type||'no environmental failure'}</td><td>${p.visual_observed===null?'indeterminate':p.visual_observed?'observed':'not observed'} (${p.visual_confidence??'n/a'})</td><td>${p.comparison_status}</td><td>${p.created_at||'unknown'}</td></tr>`).join(''))</script>"""

    @app.get("/pairs/{pair_id}", response_class=HTMLResponse)
    def pair_page(pair_id: str) -> str:
        if not store.get_pair(pair_id): raise HTTPException(404, "pair not found")
        return f"""<!doctype html><title>{pair_id}</title><style>body{{font:15px system-ui;margin:2rem;max-width:1300px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:2rem}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:1rem}}video,img{{max-width:100%;max-height:420px}}h2{{margin-top:2rem}}</style><a href='/'>← experiments</a><h1>SAME EXPERIMENT: {pair_id}</h1><div class=grid><section><h2>PHYSICS-GROUNDED SIMULATION</h2><div id=isaac></div></section><section><h2>NEURAL WORLD VISUAL EVIDENCE</h2><div id=reactor></div></section></div><h2>COMPARISON</h2><pre id=comparison></pre><h2>Event timeline (Isaac simulation time)</h2><pre id=timeline></pre><h2>Human review</h2><select id=review></select> <button onclick='save()'>Save</button><script>const states={json.dumps([item.value for item in ReviewState])};fetch('/api/pairs/{pair_id}').then(r=>r.json()).then(d=>{{window.d=d; const render=(x,el)=>document.querySelector(el).innerHTML=`<pre>${{JSON.stringify(x,null,2)}}</pre>`+(x.artifacts||[]).map(a=>a.kind==='video'?`<video controls src='/artifacts/${{a.artifact_id}}'></video>`:a.kind==='image'?`<img src='/artifacts/${{a.artifact_id}}'>`:`<a href='/artifacts/${{a.artifact_id}}'>${{a.kind}}</a>`).join('<br>'); d.isaac.artifacts=d.isaac_artifacts;d.reactor.artifacts=d.reactor_artifacts;render(d.isaac,'#isaac');render(d.reactor,'#reactor');document.querySelector('#comparison').textContent=JSON.stringify(d.pair,null,2);document.querySelector('#timeline').textContent=JSON.stringify(d.isaac_timeline,null,2);document.querySelector('#review').innerHTML=states.map(s=>`<option ${{s===d.pair.review_state?'selected':''}}>${{s}}</option>`).join('')}});function save(){{fetch('/api/pairs/{pair_id}/review',{{method:'PUT',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{review_state:document.querySelector('#review').value}})}}).then(()=>location.reload())}}</script>"""

    @app.get("/api/experiments")
    def experiments() -> list[dict[str, Any]]: return store.list_experiments()

    @app.get("/api/pairs")
    def pairs() -> list[dict[str, Any]]: return store.list_pairs()

    @app.get("/api/pairs/{pair_id}")
    def pair_detail(pair_id: str) -> dict[str, Any]:
        detail = build_pair_view(store, pair_id)
        if not detail: raise HTTPException(404, "pair not found")
        return detail

    @app.put("/api/pairs/{pair_id}/review")
    def update_review(pair_id: str, update: ReviewUpdate) -> dict[str, str]:
        try: store.set_review_state(pair_id, update.review_state)
        except KeyError as exc: raise HTTPException(404, str(exc)) from exc
        return {"pair_id": pair_id, "review_state": update.review_state.value}

    @app.get("/artifacts/{artifact_id}")
    def artifact(artifact_id: int) -> FileResponse:
        for pair in store.list_pairs():
            candidates = store.artifacts_for("pair", pair["pair_id"])
            if match := next((item for item in candidates if item["artifact_id"] == artifact_id), None):
                break
        else:
            match = next((item for record in store.list_experiments() for item in store.artifacts_for("experiment", record["run_id"]) if item["artifact_id"] == artifact_id), None)
        if not match or not Path(match["path"]).is_file(): raise HTTPException(404, "artifact not available")
        return FileResponse(match["path"])

    return app
