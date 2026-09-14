"""PostgreSQL persistence layer.

The Flask application still exposes the legacy load_data/save_data interface,
but persistence is now backed by a normalized insurance data model. The legacy
JSON snapshot is kept only as a local-development fallback during migration.
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
    "self_ignition": "Самовозгорание",
    "fire": "Самовозгорание",
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


def _schema_path() -> Path:
    return Path(__file__).resolve().parent / "database" / "schema.sql"


def init_db() -> bool:
    """Create or upgrade the normalized PostgreSQL schema."""
    conn = _connect()
    if conn is None:
        return False
    try:
        schema = _schema_path().read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()
        logger.info("✅ PostgreSQL schema initialized")
        return True
    except Exception as exc:
        conn.rollback()
        logger.exception("❌ Ошибка инициализации PostgreSQL schema: %s", exc)
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


def _as_value(field_data: Any) -> tuple[Any, Optional[str], Optional[str]]:
    if isinstance(field_data, dict):
        return field_data.get("value"), field_data.get("source"), field_data.get("url")
    return field_data, None, None


def _upsert_company(cur, name: str, now: datetime) -> int:
    cur.execute(
        """
        INSERT INTO companies (name, slug, short_name, status, updated_at)
        VALUES (%s, %s, %s, 'active', %s)
        ON CONFLICT (name) DO UPDATE SET updated_at = EXCLUDED.updated_at
        RETURNING id
        """,
        (name, None, name, now),
    )
    return cur.fetchone()[0]


def _upsert_product(cur, company_id: int, now: datetime) -> int:
    cur.execute(
        """
        INSERT INTO products (company_id, name, slug, product_type, status, updated_at)
        VALUES (%s, 'КАСКО', 'kasko', 'casco', 'active', %s)
        ON CONFLICT (company_id, name)
        DO UPDATE SET updated_at = EXCLUDED.updated_at, product_type = EXCLUDED.product_type
        RETURNING id
        """,
        (company_id, now),
    )
    return cur.fetchone()[0]


def _upsert_field(cur, product_id: int, field_key: str, now: datetime) -> int:
    cur.execute(
        """
        INSERT INTO comparison_fields
            (product_id, field_key, label, data_type, is_active, updated_at)
        VALUES (%s, %s, %s, 'text', TRUE, %s)
        ON CONFLICT (product_id, field_key)
        DO UPDATE SET label = EXCLUDED.label, updated_at = EXCLUDED.updated_at
        RETURNING id
        """,
        (product_id, field_key, FIELD_LABELS.get(field_key, field_key), now),
    )
    return cur.fetchone()[0]


def _upsert_source(cur, company_id: int, source_url: str, source_type: Optional[str], now: datetime) -> int:
    cur.execute(
        """
        INSERT INTO sources
            (company_id, url, source_type, source_level, status, last_checked_at, last_success_at)
        VALUES (%s, %s, %s, 2, 'active', %s, %s)
        ON CONFLICT (company_id, url)
        DO UPDATE SET source_type = COALESCE(EXCLUDED.source_type, sources.source_type),
                      last_checked_at = EXCLUDED.last_checked_at,
                      last_success_at = EXCLUDED.last_success_at
        RETURNING id
        """,
        (company_id, source_url, source_type or "official_site", now, now),
    )
    return cur.fetchone()[0]


def _save_condition(cur, field_id: int, value: Any, source_id: Optional[int], now: datetime) -> None:
    normalized_value = None if value is None else str(value)
    cur.execute(
        """
        SELECT id, value, verification_status
        FROM conditions
        WHERE field_id = %s AND status = 'active'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (field_id,),
    )
    current = cur.fetchone()

    if current:
        condition_id, old_value, verification_status = current
        if old_value != normalized_value:
            cur.execute(
                """
                INSERT INTO condition_versions
                    (condition_id, value, source_id, text_fragment, verification_status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (condition_id, old_value, source_id, old_value, verification_status or "unverified"),
            )
            cur.execute(
                """
                INSERT INTO change_log
                    (entity_type, entity_id, field_name, old_value, new_value, reason)
                VALUES ('condition', %s, 'value', %s, %s, 'source_refresh')
                """,
                (condition_id, old_value, normalized_value),
            )
        cur.execute(
            """
            UPDATE conditions
            SET value = %s, checked_at = %s, updated_at = %s,
                verification_status = CASE
                    WHEN %s IS DISTINCT FROM %s THEN 'unverified'
                    ELSE verification_status
                END
            WHERE id = %s
            """,
            (normalized_value, now, now, old_value, normalized_value, condition_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO conditions (field_id, value, verification_status, checked_at, updated_at)
            VALUES (%s, %s, 'unverified', %s, %s)
            RETURNING id
            """,
            (field_id, normalized_value, now, now),
        )
        condition_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO evidence (condition_id, source_id, text_fragment, verification_status)
        VALUES (%s, %s, %s, 'unverified')
        """,
        (condition_id, source_id, normalized_value),
    )


def save_data(data: Dict[str, Any]) -> bool:
    """Persist the current snapshot and update normalized records."""
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
                company_id = _upsert_company(cur, str(company_name), now)
                product_id = _upsert_product(cur, company_id, now)
                for field_key, field_data in company_data.items():
                    value, source_type, source_url = _as_value(field_data)
                    if value is None and not field_data:
                        continue
                    field_id = _upsert_field(cur, product_id, str(field_key), now)
                    source_id = _upsert_source(cur, company_id, str(source_url), source_type, now) if source_url else None
                    _save_condition(cur, field_id, value, source_id, now)
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.exception("❌ Ошибка сохранения данных в PostgreSQL: %s", exc)
        return False
    finally:
        conn.close()


def load_data() -> Dict[str, Any]:
    """Load the legacy-shaped snapshot used by the current Flask UI."""
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
        logger.exception("❌ Ошибка чтения данных из PostgreSQL: %s", exc)
    finally:
        conn.close()
    return _load_json_fallback()
