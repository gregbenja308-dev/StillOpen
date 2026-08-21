"""Health probe."""

from __future__ import annotations

from fastapi import APIRouter
from stillopen_core.agents.adk_graph import RUN_GRAPH, build_sequential_agent, graph_names
from stillopen_core.config import get_settings

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    settings = get_settings()
    graph = build_sequential_agent()
    adk = settings.has_gemini and graph is not None
    if adk:
        clerk = "adk"
    elif settings.has_gemini:
        clerk = "adk_missing"
    else:
        clerk = "heuristic"
    return {
        "status": "ok",
        "env": settings.env.value,
        "service": settings.service_name,
        "gemini": (
            "vertex"
            if settings.use_vertex and settings.gcp_project
            else "configured"
            if settings.has_gemini
            else "fakes"
        ),
        "gcp_project": settings.gcp_project or "",
        "vertex_location": settings.gcp_location if settings.use_vertex else "",
        "otel": settings.otel_exporter.value,
        "armor": settings.armor_backend,
        "bank": "firestore" if settings.use_firestore else "local_json",
        "clerk": clerk,
        "run_graph": ">".join(graph_names(graph) or [n.name for n in RUN_GRAPH]),
    }
