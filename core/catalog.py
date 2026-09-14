from __future__ import annotations

KASKO_FIELDS = (
    {"key": "franchise", "label": "Франшиза", "category": "damage", "sort_order": 10},
    {"key": "without_certificates", "label": "Без справок", "category": "damage", "sort_order": 20},
    {"key": "gap", "label": "GAP-страхование", "category": "financial", "sort_order": 30},
    {"key": "total_loss", "label": "Порог тотала", "category": "total_loss", "sort_order": 40},
    {"key": "fire", "label": "Пожар", "category": "risks", "sort_order": 50},
    {"key": "terrorism", "label": "Терроризм", "category": "risks", "sort_order": 60},
    {"key": "drone", "label": "БПЛА / Дроны", "category": "risks", "sort_order": 70},
    {"key": "tow_truck", "label": "Эвакуатор", "category": "assistance", "sort_order": 80},
    {"key": "repair_type", "label": "Тип ремонта", "category": "repair", "sort_order": 90},
    {"key": "payment_terms", "label": "Срок выплат", "category": "claims", "sort_order": 100},
)

PRODUCT_TYPES = {
    "insurance": "Страхование",
    "casco": "КАСКО",
    "osago": "ОСАГО",
}

VERIFICATION_STATUSES = {
    "unverified",
    "needs_review",
    "verified",
    "rejected",
}

SOURCE_TYPES = {
    "official_site",
    "rules",
    "policy_terms",
    "tariff",
    "pdf",
    "faq",
    "other",
}
