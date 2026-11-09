"""Who runs the site and the versions of the legal documents (09.11.2026).

The operator's details come from Vercel settings, so the owner fills them in
without a code change: OPERATOR_NAME (full name or the self-employed name),
OPERATOR_INN, OPERATOR_EMAIL. Until they are set, the pages name the service
and its contact mailbox.
"""
from __future__ import annotations

import os

# Bump when a document changes: users accept the version they saw.
DOCUMENTS_VERSION = "2026-11-09"
MINIMUM_AGE = 18


def operator() -> dict[str, str]:
    email = os.environ.get("OPERATOR_EMAIL") or os.environ.get("SMTP_USER") or "strahovoy.analitik@yandex.ru"
    return {
        "name": os.environ.get("OPERATOR_NAME") or "владелец сервиса «Страховой аналитик»",
        "inn": os.environ.get("OPERATOR_INN", ""),
        "email": email,
        "site": "https://insurance-comparator-eta.vercel.app",
        "named": bool(os.environ.get("OPERATOR_NAME")),
    }
