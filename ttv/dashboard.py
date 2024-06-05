"""Dashboard + ROI calculator page. Reads a `/state` snapshot from the model service (or in-process)."""
from __future__ import annotations

from typing import Awaitable, Callable

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from . import roi
from .scenarios import get_scenario

StateProvider = Callable[[], Awaitable[dict]]

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>TimeToValue-in-a-Box</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1b2430;--mut:#5b6674;--card:#f3f5f8;--acc:#1f6feb;--bad:#c62828}
@media(prefers-color-scheme:dark){:root{--bg:#10151c;--fg:#e6ebf2;--mut:#9aa6b5;--card:#1a222d;--acc:#5aa2ff;--bad:#ff6b6b}}
body{font:15px/1.5 system-ui,sans-serif;margin:0;background:var(--bg);color:var(--fg)}
main{max-width:1000px;margin:0 auto;padding:24px}h1{margin:0 0 4px}p.sub{color:var(--mut);margin-top:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0}
.card{background:var(--card);border-radius:10px;padding:12px 14px}.card b{display:block;font-size:24px}
.card span{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--card)}
.sev-critical,.sev-high{color:var(--bad);font-weight:600}label{display:inline-block;margin:4px 12px 4px 0;font-size:13px}
input{width:90px}h2{margin-top:28px}</style></head><body><main>
<h1>TimeToValue-in-a-Box</h1><p class="sub" id="scn">loading…</p>
<div class="grid" id="kpis"></div>
<h2>Latest insights</h2><table><thead><tr><th>Severity</th><th>Entity</th><th>Summary</th></tr></thead>
<tbody id="rows"></tbody></table>
<h2>ROI calculator</h2><p class="sub">Measured values come from this live run; edit the customer assumptions to re-estimate.</p>
<div id="inputs"></div><div class="grid" id="roi"></div><p class="sub" id="roimsg"></p>
<script>
const FIELDS=["anomalies_per_month","baseline_detect_minutes","baseline_alerts_per_month","baseline_fp_share",
"triage_minutes_per_alert","analyst_hourly_cost","incident_cost_per_hour"];
const $=id=>document.getElementById(id);
const fmt=(v,d=1)=>v==null?"–":Number(v).toLocaleString(undefined,{maximumFractionDigits:d});
const card=(l,v)=>`<div class="card"><span>${l}</span><b>${v}</b></div>`;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let built=false;
async function refresh(){
 const s=await (await fetch("api/state")).json(),st=s.stats;
 $("scn").textContent=s.scenario.title+" — "+s.scenario.description;
 const p=x=>x==null?"–":(x*100).toFixed(1)+"%";
 $("kpis").innerHTML=card("Time to first insight",st.time_to_first_insight_s==null?"waiting…":fmt(st.time_to_first_insight_s,1)+" s")
  +card("Events scored",fmt(st.processed,0))+card("Alerts",fmt(st.alerts,0))+card("Recall",p(st.recall))
  +card("False-positive share",p(st.false_positive_share))
  +card("Mean detection latency",st.detection_latency_s.mean==null?"–":fmt(st.detection_latency_s.mean*1000,1)+" ms");
 $("rows").innerHTML=s.insights.slice(0,12).map(i=>`<tr><td class="sev-${esc(i.severity)}">${esc(i.severity)}</td><td>${esc(i.entity)}</td><td>${esc(i.summary)}</td></tr>`).join("");
 const q=new URLSearchParams();
 if(built)FIELDS.forEach(f=>q.set(f,$("f_"+f).value));
 const r=await fetch("api/roi?"+q);
 if(!r.ok){$("roimsg").textContent=(await r.json()).detail;return}
 const d=await r.json();$("roimsg").textContent="";
 if(!built){$("inputs").innerHTML=FIELDS.map(f=>`<label>${f.replaceAll("_"," ")}<br><input id="f_${f}" type="number" step="any" value="${d.inputs[f]}"></label>`).join("");
  FIELDS.forEach(f=>$("f_"+f).addEventListener("change",refresh));built=true}
 const c=d.currency,m=d.monthly,a=d.annual;
 $("roi").innerHTML=card("Hours saved / month",fmt(m.hours_saved))+card("Cost saved / month",c+" "+fmt(m.cost_saved,0))
  +card("Hours saved / year",fmt(a.hours_saved,0))+card("Cost saved / year",c+" "+fmt(a.cost_saved,0))
  +card("False alerts avoided / month",fmt(m.false_alerts_baseline-m.false_alerts_with_kit,0));
}
refresh();setInterval(refresh,3000);
</script></main></body></html>"""

ROI_PARAMS = (
    "anomalies_per_month", "baseline_detect_minutes", "baseline_alerts_per_month", "baseline_fp_share",
    "triage_minutes_per_alert", "analyst_hourly_cost", "incident_cost_per_hour",
)


def make_router(provider: StateProvider) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return PAGE

    @router.get("/api/state")
    async def state() -> dict:
        try:
            return await provider()
        except httpx.HTTPError as exc:
            raise HTTPException(503, f"model service unreachable: {exc}") from exc

    @router.get("/api/roi")
    async def roi_endpoint(
        anomalies_per_month: float | None = Query(None, ge=0),
        baseline_detect_minutes: float | None = Query(None, ge=0),
        baseline_alerts_per_month: float | None = Query(None, ge=0),
        baseline_fp_share: float | None = Query(None, ge=0, le=1),
        triage_minutes_per_alert: float | None = Query(None, ge=0),
        analyst_hourly_cost: float | None = Query(None, ge=0),
        incident_cost_per_hour: float | None = Query(None, ge=0),
    ) -> dict:
        snapshot = await state()
        overrides = {k: v for k, v in locals().items() if k in ROI_PARAMS and v is not None}
        try:
            scenario = get_scenario(snapshot["scenario"]["name"])
            return roi.from_stats(scenario.roi, snapshot["stats"], **overrides)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router


def create_app(model_url: str) -> FastAPI:
    """Stand-alone dashboard that proxies the model service (the in-cluster deployment)."""
    app = FastAPI(title="TimeToValue dashboard")
    client = httpx.AsyncClient(base_url=model_url, timeout=5.0)

    async def provider() -> dict:
        resp = await client.get("/state")
        resp.raise_for_status()
        return resp.json()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    app.include_router(make_router(provider))
    return app
