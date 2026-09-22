"""Vercel entrypoint for the normalized insurance comparator."""

import db

db.init_db()

from web_app import app

__all__ = ["app"]
