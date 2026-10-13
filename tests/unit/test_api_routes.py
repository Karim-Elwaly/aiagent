"""The routes the UI calls must stay registered."""

from __future__ import annotations

from src.api.main import app


def test_ui_routes_are_registered():
    routes = {(m, r.path) for r in app.routes for m in getattr(r, "methods", None) or ()}
    for method, path in (
        ("POST", "/solve"),
        ("POST", "/solve/async"),
        ("POST", "/approve/{workflow_id}"),
        ("POST", "/clarify/{workflow_id}"),
        ("POST", "/api/workflows/{workflow_id}/tasks/{task_id}/agent"),
        ("GET", "/stream/{workflow_id}"),
        ("GET", "/status/{workflow_id}"),
    ):
        assert (method, path) in routes, f"{method} {path} is not registered"
