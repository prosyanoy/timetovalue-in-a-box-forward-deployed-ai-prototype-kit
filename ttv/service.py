"""Model service: consumes events from the bus, scores + summarizes them, and serves results over HTTP."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from fastapi import FastAPI, HTTPException

from . import generator
from .bus import make_bus
from .config import Settings
from .dashboard import make_router
from .metrics import Metrics
from .pipeline import Pipeline
from .scenarios import get_scenario
from .scoring import AnomalyScorer
from .summarizer import Summarizer
from .telemetry import Telemetry

log = logging.getLogger("ttv.service")


def create_app(settings: Settings | None = None, with_dashboard: bool = False) -> FastAPI:
    settings = settings or Settings.from_env()
    scenario = get_scenario(settings.scenario)
    metrics = Metrics(start_epoch=settings.start_epoch)
    telemetry = Telemetry("ttv-model-service", settings.otel_endpoint,
                          ttv_getter=lambda: metrics.snapshot()["time_to_first_insight_s"])
    scorer = AnomalyScorer(scenario, seed=settings.seed)
    summarizer = Summarizer(scenario, settings.llm_base_url, settings.llm_model, settings.llm_api_key,
                            settings.llm_timeout)
    pipeline = Pipeline(scenario, scorer, summarizer, metrics)
    state = {"ready": False, "bus": "disconnected"}

    async def handle(event: dict) -> None:
        with telemetry.tracer.start_as_current_span("score_event") as span:
            insight = await asyncio.to_thread(pipeline.process, event)
            span.set_attribute("ttv.alert", insight["alert"])
            span.set_attribute("ttv.score", insight["score"])
        telemetry.observe(insight)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        bus = make_bus(settings.bus_url)
        tasks: list[asyncio.Task] = []

        async def start_bus() -> None:
            await bus.connect()
            await bus.subscribe(settings.subject, handle)
            state.update(ready=True, bus="connected")
            if settings.embedded_generator:
                tasks.append(asyncio.create_task(generator.run(bus, settings)))

        # connect in the background so /healthz answers while NATS is still starting
        tasks.append(asyncio.create_task(start_bus()))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await bus.close()
            telemetry.shutdown()

    app = FastAPI(title="TimeToValue model service", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict:
        if not state["ready"]:
            raise HTTPException(503, "event bus not connected yet")
        return {"status": "ready", "bus": state["bus"], "scenario": scenario.name}

    @app.post("/score")
    async def score(event: dict) -> dict:
        """Synchronous scoring for ad-hoc events: {"entity": ..., "features": {...}}."""
        try:
            event.setdefault("ts", time.time())
            insight = await asyncio.to_thread(pipeline.process, event)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        telemetry.observe(insight)
        return insight

    @app.get("/stats")
    async def stats() -> dict:
        return metrics.snapshot()

    @app.get("/insights")
    async def insights(limit: int = 20) -> list[dict]:
        return metrics.recent_insights(min(max(limit, 1), 50))

    async def get_state() -> dict:
        return {
            "scenario": {"name": scenario.name, "title": scenario.title, "description": scenario.description},
            "stats": metrics.snapshot(),
            "insights": metrics.recent_insights(20),
            "summarizer": "llm" if settings.llm_base_url else "template",
        }

    app.get("/state")(get_state)
    if with_dashboard:
        app.include_router(make_router(get_state))
    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(with_dashboard=False), host="0.0.0.0", port=8081)  # noqa: S104 (container)


def dashboard_main() -> None:
    import uvicorn

    from .dashboard import create_app as create_dashboard

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_dashboard(Settings.from_env().model_url), host="0.0.0.0", port=8080)  # noqa: S104


if __name__ == "__main__":
    main()
