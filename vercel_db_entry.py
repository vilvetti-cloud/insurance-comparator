"""Vercel entrypoint for the normalized insurance comparator.

The web function must stay lightweight: schema creation/migrations belong to
deployment or collection jobs, not to every serverless cold start.
"""

from web_app import app

__all__ = ["app"]
