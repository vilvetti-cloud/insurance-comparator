"""Persistent PostgreSQL storage for the insurance comparator.

The current Flask application historically stored its complete data snapshot in
insurance_data.json. This module keeps that exact application-facing shape for
now, while also writing the important pieces into normalized PostgreSQL tables
so the data model can grow into products, sources and evidence later.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "franchise": "Франшиза",
    "without_certificates": "Без справок",
    "gap": "GAP-страхование",
    "total_loss": "Порог тотала",
    "fire": "Пожар",
    "terrorism": "Терроризм",
    "drone": "БПЛА / Дроны",
    "tow_truck": "Эвакуатор",
    "repair_type": "Тип ремонта",
    "payment_terms": "Срок выплат",
    "advantages": "Преимущества",
    "weak_points": "Недостатки",
    "rating": "Рейтинг",
    "offices": "Офисы",
}


def _database_url() -> Optional[str]:
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRES_URL_NON_POOLING")
    )


def _connect():
    url = _database_url()
    if not url:
        return None
    try:
        import psycopg
        return psycopg.connect(url, connect_timeout=8)
    except Exception as exc:
        logger.exception("❌ Не удалось подключиться к PostgreSQL: %s", exc)
        return None


def init_db() -> bool:
    """Create the database schema if DATABASE_URL is configured."""
    conn = _connect()
    if conn is None:
        return False

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS products (
                    id BIGSERIAL PRIMARY KEY,
                    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    product_type TEXT NOT NULL DEFAULT 'insurance',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(company_id, name)
                );

                CREATE TABLE IF NOT EXISTS comparison_fields (
                    id BIGSERIAL PRIMARY KEY,
                    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    field_key TEXT NOT NULL,
                    label TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(product_id, field_key)
                );

                CREATE TABLE IF NOT EXISTS conditions (
                    id BIGSERIAL PRIMARY KEY,
                    field_id BIGINT NOT NULL REFERENCES comparison_fields(id) ON DELETE CASCADE,
                    value TEXT,
                    source_type TEXT,
                    source_url TEXT,
                    checked_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS sources (
                    id BIGSERIAL PRIMARY KEY,
                    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    source_type TEXT,
                    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_checked_at TIMESTAMPTZ,
                    UNIQUE(company_id, url)
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    id BIGSERIAL PRIMARY KEY,
                    condition_id BIGINT REFERENCES conditions(id) ON DELETE CASCADE,
                    source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL,
                    document_name TEXT,
                    document_date TEXT,
                    page_number INTEGER,
                    text_fragment TEXT,
                    verification_status TEXT NOT NULL DEFAULT 'unverified',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    state_key TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.exception("❌ Ошибка инициализации БД: %s", exc)
        return False
    finally:
        conn.close()


def _json_fallback_path() -> Path:
    return Path(__file__).resolve().parent / "insurance_data.json"


def _load_json_fallback() -> Dict[str, Any]:
    path = _json_fallback_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("⚠️ Не удалось прочитать локальные данные: %s", exc)
        return {}


def _save_json_fallback(data: Dict[str, Any]) -> bool:
    path = _json_fallback_path()
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as exc:
        logger.warning("⚠️ Не удалось сохранить локальные данные: %s", exc)
        return False


def load_data() -> Dict[str, Any]:
    """Return data in the exact shape expected by the existing Flask app."""
    if not _database_url():
        return _load_json_fallback()

    conn = _connect()
    if conn is None:
        return _load_json_fallback()

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM app_state WHERE state_key = 'insurance_data'")
            row = cur.fetchone()
            if row and row[0]:
                return dict(row[0])
    except Exception as exc:
        logger.exception("❌ Ошибка чтения данных из БД: %s", exc)
    finally:
        conn.close()

    legacy = _load_json_fallback()
    if legacy:
        save_data(legacy)
    return legacy


def save_data(data: Dict[str, Any]) -> bool:
    """Persist the current application snapshot and its normalized records."""
    if not _database_url():
        return _save_json_fallback(data)

    conn = _connect()
    if conn is None:
        return False

    now = datetime.now(timezone.utc)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_state (state_key, payload, updated_at)
                VALUES ('insurance_data', %s::jsonb, %s)
                ON CONFLICT (state_key)
                DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at
                """,
                (json.dumps(data, ensure_ascii=False), now),
            )

            for company_name, company_data in data.items():
                if str(company_name).startswith("_") or not isinstance(company_data, dict):
                    continue

                cur.execute(
                    """
                    INSERT INTO companies (name)
                    VALUES (%s)
                    ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    (company_name,),
                )
                company_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO products (company_id, name, product_type)
                    VALUES (%s, 'КАСКО', 'insurance')
                    ON CONFLICT (company_id, name)
                    DO UPDATE SET product_type = EXCLUDED.product_type
                    RETURNING id
                    """,
                    (company_id,),
                )
                product_id = cur.fetchone()[0]

                for field_key, field_data in company_data.items():
                    if not isinstance(field_data, dict):
                        value = field_data
                        source_type = None
                        source_url = None
                    else:
                        value = field_data.get("value")
                        source_type = field_data.get("source")
                        source_url = field_data.get("url")

                    if value is None and not field_data:
                        continue

                    cur.execute(
                        """
                        INSERT INTO comparison_fields (product_id, field_key, label)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (product_id, field_key)
                        DO UPDATE SET label = EXCLUDED.label
                        RETURNING id
                        """,
                        (product_id, field_key, FIELD_LABELS.get(field_key, field_key)),
                    )
                    field_id = cur.fetchone()[0]

                    cur.execute(
                        """
                        INSERT INTO conditions (field_id, value, source_type, source_url, checked_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            field_id,
                            None if value is None else str(value),
                            source_type,
                            source_url,
                            now,
                            now,
                        ),
                    )
                    condition_id = cur.fetchone()[0]

                    source_id = None
                    if source_url:
                        cur.execute(
                            """
                            INSERT INTO sources (company_id, url, source_type, last_checked_at)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (company_id, url)
                            DO UPDATE SET source_type = EXCLUDED.source_type,
                                          last_checked_at = EXCLUDED.last_checked_at
                            RETURNING id
                            """,
                            (company_id, source_url, source_type, now),
                        )
                        source_id = cur.fetchone()[0]

                    if value is not None or source_id is not None:
                        cur.execute(
                            """
                            INSERT INTO evidence (condition_id, source_id, text_fragment, verification_status)
                            VALUES (%s, %s, %s, 'unverified')
                            """,
                            (condition_id, source_id, None if value is None else str(value)),
                        )

        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.exception("❌ Ошибка сохранения данных в PostgreSQL: %s", exc)
        return False
    finally:
        conn.close()
