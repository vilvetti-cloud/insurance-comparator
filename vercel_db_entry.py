"""Vercel entrypoint for the normalized insurance comparator.

Keep the serverless cold start lightweight and, critically, never let an import
error crash the Vercel function before Flask can return a response.
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify

logger = logging.getLogger(__name__)

_import_error: Exception | None = None

try:
    from web_app import app as app
except Exception as exc:  # pragma: no cover - production safety net
    _import_error = exc
    logger.exception("Failed to import web_app during Vercel cold start")

    app = Flask(__name__)

    @app.get("/")
    def startup_error():
        return (
            "Insurance Comparator startup error: "
            f"{type(_import_error).__name__}: {_import_error}",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    @app.get("/health")
    def startup_health():
        return jsonify(
            {
                "status": "startup_error",
                "error_type": type(_import_error).__name__,
                "error": str(_import_error),
            }
        ), 500


__all__ = ["app"]
