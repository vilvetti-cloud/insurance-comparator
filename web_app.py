from __future__ import annotations

from datetime import datetime
import os
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, redirect, render_template, request

from collector.registry import INSURERS
from collector.source_watch import load_status as load_source_status
from core.catalog import KASKO_FIELDS
from core.services.comparison_service import ComparisonService
from core.services.sales_insights_service import SalesInsightsService
from core.services.data_quality_report_service import DataQualityReportService
import web_accounts


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.register_blueprint(web_accounts.bp)

SOURCE_STATUS_LABELS = {
    "ok": "правила на сайте не менялись",
    "changed": "на сайте новая редакция правил — автоматический разбор не прошёл проверку, ответы пока по прежней",
    "unavailable": "сайт не дал проверить автоматически — проверьте вручную",
}


def _ru_date(value: str | None, with_time: bool = False) -> str | None:
    """2026-10-20T06:00+03:00 -> 20.10.2026 в 06:00; 2026-10-14 -> 14.10.2026."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    return moment.strftime("%d.%m.%Y в %H:%M" if with_time else "%d.%m.%Y")


@app.context_processor
def source_check_context() -> dict:
    """Nightly source check (data/source-check.json) for every page."""
    status = load_source_status() or {}
    companies = {}
    for name, item in (status.get("companies") or {}).items():
        state = item.get("status", "unavailable")
        new_documents = [
            link for page in item.get("pages", []) for link in page.get("new_documents", [])
        ]
        companies[name] = {
            "status": state,
            "label": SOURCE_STATUS_LABELS.get(state, SOURCE_STATUS_LABELS["unavailable"]),
            "verified": _ru_date(item.get("verified_at"), with_time=True),
            "auto_updated": _ru_date(item.get("auto_updated_at")),
            "changed_files": [f for f in item.get("files", []) if f.get("status") == "changed"],
            "new_documents": new_documents,
            "files": item.get("files", []),
            "web_copy": next((urlparse(f["copy_url"]).netloc.removeprefix("www.")
                              for f in item.get("files", []) if f.get("via") == "web_copy"), None),
            "pages_unavailable": sum(p.get("status") == "unavailable" for p in item.get("pages", [])),
        }
    snapshot_date = comparison_service.load_snapshot().get("_last_updated")
    return {
        "source_check": {
            "checked": _ru_date(status.get("checked_at"), with_time=True),
            "agreed": _ru_date(snapshot_date),
            "companies": companies,
            "ok_count": sum(c["status"] == "ok" for c in companies.values()),
            "total": len(companies),
        }
    }

comparison_service = ComparisonService()
sales_insights_service = SalesInsightsService()
data_quality_report_service = DataQualityReportService()
COMPANIES = [insurer.name for insurer in INSURERS]
FIELD_KEYS = [field["key"] for field in KASKO_FIELDS]
FIELD_LABELS = {field["key"]: field["label"] for field in KASKO_FIELDS}
REVIEW_REASONS = {
    "quote_not_on_claimed_page": "Цитата модели не совпала с текстом указанной страницы PDF.",
    "section_not_on_claimed_page": "Раздел модели не совпал с текстом указанной страницы PDF.",
    "incomplete_answer": "Ответ из документа неполный.",
    "missing_value_quote_section": "Не хватает точной цитаты или раздела документа.",
}


def _prepare_company_data(snapshot: dict, company: str, contextual: dict | None = None) -> dict:
    raw = snapshot.get(company, {})
    contextual = contextual or {}
    prepared: dict = {}

    for field in FIELD_KEYS:
        field_data = raw.get(field, {})
        if isinstance(field_data, dict):
            prepared[field] = field_data.get("value", "Не найдено") or "Не найдено"
            prepared[f"{field}_source"] = field_data.get("source", "none")
            prepared[f"{field}_url"] = field_data.get("url")
            prepared[f"{field}_source_level"] = field_data.get("source_level")
            prepared[f"{field}_confidence"] = field_data.get("confidence")
            prepared[f"{field}_verification_status"] = field_data.get(
                "verification_status", "unverified"
            )
            prepared[f"{field}_quality_status"] = field_data.get(
                "quality_status", "review"
            )
            prepared[f"{field}_quality_label"] = field_data.get(
                "quality_label", "Нужно перепроверить"
            )
            prepared[f"{field}_quality_reason"] = field_data.get(
                "quality_reason"
            )
            prepared[f"{field}_sales_eligible"] = bool(
                field_data.get("sales_eligible", False)
            )
            # Structured facts decide whether the condition is stated at all;
            # SalesInsightsService falls back to reading the text without them.
            prepared[f"{field}_facts"] = field_data.get("facts")
            diagnostic = contextual.get(field, {})
            failure = diagnostic.get("analysis_validation")
            has_accepted_value = (
                bool(prepared[field])
                and not str(prepared[field]).strip().lower().startswith("не найдено")
                and prepared[f"{field}_source_level"] in {1, 2}
            )
            prepared[f"{field}_review_note"] = None if has_accepted_value else (
                REVIEW_REASONS.get(failure, "Ответ модели требует проверки по документу.")
                if diagnostic.get("analysis_answer") else field_data.get("quality_reason")
            ) if field_data.get("quality_status") not in {"confirmed", "conditional"} else None
        else:
            prepared[field] = "Не найдено"
            prepared[f"{field}_source"] = "none"
            prepared[f"{field}_url"] = None
            prepared[f"{field}_source_level"] = None
            prepared[f"{field}_confidence"] = None
            prepared[f"{field}_verification_status"] = "unverified"
            prepared[f"{field}_quality_status"] = "missing"
            prepared[f"{field}_quality_label"] = "Не найдено"
            prepared[f"{field}_quality_reason"] = "Значение отсутствует."
            prepared[f"{field}_sales_eligible"] = False
            prepared[f"{field}_facts"] = None
            diagnostic = contextual.get(field, {})
            failure = diagnostic.get("analysis_validation")
            prepared[f"{field}_review_note"] = (
                REVIEW_REASONS.get(failure, "Ответ модели требует проверки по документу.")
                if diagnostic.get("analysis_answer") else None
            )

    return prepared


@app.route("/")
def index():
    snapshot = comparison_service.load_snapshot()
    user = web_accounts.current_user()
    return render_template(
        "index.html",
        companies=COMPANIES,
        main_insurer=user["main_insurer"] if user else None,
        group_compare=GROUP_COMPARE,
        last_updated=snapshot.get("_last_updated", "Не обновлялось"),
    )


ABOUT_EXAMPLE = ("Ренессанс Страхование", "ВСК")


@app.route("/about")
def about():
    """What the service is, for people who have not used it yet."""
    snapshot = comparison_service.load_snapshot()
    first, second = ABOUT_EXAMPLE
    example = sales_insights_service.analyze(
        company=first,
        competitor=second,
        data=_prepare_company_data(snapshot, first),
        competitor_data=_prepare_company_data(snapshot, second),
        field_labels=FIELD_LABELS,
    )
    return render_template(
        "about.html",
        active_section="about",
        companies=COMPANIES,
        fields=[field["label"] for field in KASKO_FIELDS],
        example=example["client_message"],
        example_pair=ABOUT_EXAMPLE,
        plans=web_accounts.PLANS,
        free=web_accounts.FREE_COMPARISONS,
        last_updated=snapshot.get("_last_updated", "Не обновлялось"),
    )


@app.route("/compare", methods=["GET", "POST"])
def compare():
    company1 = request.values.get("company1")
    competitors = list(dict.fromkeys(c for c in request.values.getlist("company2") if c))
    if len(competitors) > 1 and GROUP_COMPARE:
        return _compare_group(company1, competitors)
    company2 = competitors[0] if competitors else None

    if (
        not company1
        or company1 not in COMPANIES
        or not company2
        or company2 not in COMPANIES
        or company1 == company2
    ):
        return redirect("/")
    # 3 free comparisons, then registration and a subscription.
    blocked = web_accounts.comparison_gate(company1, company2)
    if blocked is not None:
        return blocked

    snapshot = comparison_service.load_snapshot()
    if snapshot.get("_data_source") == "normalized_json":
        contextual = {}
    else:
        report = data_quality_report_service.load()
        contextual = {
            company["name"]: {field["key"]: field for field in company["fields"]}
            for company in report.get("companies", [])
        }
    data1 = _prepare_company_data(snapshot, company1, contextual.get(company1))
    data2 = _prepare_company_data(snapshot, company2, contextual.get(company2))
    def has_value(data: dict, field: str) -> bool:
        value = data.get(field)
        return bool(value) and not str(value).strip().lower().startswith("не найдено")

    def has_official_value(data: dict, field: str) -> bool:
        return data.get(f"{field}_source_level") in {1, 2} and has_value(data, field)

    # Accepted answer text from official documents/sites is the source of truth.
    # Quality/audit statuses are diagnostics and must not hide populated values.
    found1 = sum(1 for field in FIELD_KEYS if has_official_value(data1, field))
    found2 = sum(1 for field in FIELD_KEYS if has_official_value(data2, field))
    comparable_fields = [
        field for field in FIELD_KEYS
        if data1.get(f"{field}_source_level") in {1, 2}
        and data2.get(f"{field}_source_level") in {1, 2}
        and (has_value(data1, field) or has_value(data2, field))
    ]
    comparison_ready = bool(comparable_fields)

    # Audit statuses do not gate accepted official values. The only readiness
    # gate is whether the selected companies have any official-source field data.
    if comparison_ready:
        sales = sales_insights_service.analyze(
            company=company1,
            competitor=company2,
            data=data1,
            competitor_data=data2,
            field_labels=FIELD_LABELS,
        )
    else:
        sales = {
            "advantages": [],
            "conditional_advantages": [],
            "cards": [],
            "comparisons": [],
            "cautions": [
                "Для выбранных компаний нет значений из официальных источников, пригодных для сравнения."
            ],
            "client_message": "Нужно выбрать пары компаний с доступными официальными условиями.",
        }

    comparison_by_field = {
        key: {
            "field_key": key,
            "outcome": "incomparable",
            "title": "Недостаточно подтверждённых данных",
            "reason": "Нет двух сопоставимых значений, прошедших проверку источника. Это не означает, что покрытия нет.",
        }
        for key in FIELD_KEYS
    }
    comparison_by_field.update({
        item["field_key"]: item
        for item in sales.get("comparisons", [])
        if isinstance(item, dict) and item.get("field_key")
    })

    return render_template(
        "result.html",
        company1=company1,
        company2=company2,
        data1=data1,
        data2=data2,
        fields=FIELD_KEYS,
        field_labels=FIELD_LABELS,
        comparable_count=len(comparable_fields),
        comparison_ready=comparison_ready,
        sales=sales,
        comparison_by_field=comparison_by_field,
        found1=found1,
        found2=found2,
        last_updated=snapshot.get("_last_updated", "Не обновлялось"),
    )


MAX_COMPETITORS = 3
# Several competitors at once is kept for a future paid plan (owner's decision,
# 21.10.2026); turned on with the environment variable GROUP_COMPARE=1.
GROUP_COMPARE = os.environ.get("GROUP_COMPARE") == "1"


def _compare_group(company1: str | None, competitors: list[str]):
    """One insurer against two or three competitors: a shared message and a summary table."""
    if (
        company1 not in COMPANIES
        or len(competitors) > MAX_COMPETITORS
        or any(c not in COMPANIES or c == company1 for c in competitors)
    ):
        return redirect("/")
    snapshot = comparison_service.load_snapshot()
    data1 = _prepare_company_data(snapshot, company1)
    group = sales_insights_service.analyze_group(
        company=company1,
        competitors=competitors,
        data=data1,
        competitor_data={c: _prepare_company_data(snapshot, c) for c in competitors},
        field_labels=FIELD_LABELS,
    )
    outcomes = {
        competitor: {item["field_key"]: item.get("outcome") for item in result["comparisons"]}
        for competitor, result in group["pairs"].items()
    }
    return render_template(
        "compare_group.html",
        company1=company1,
        competitors=competitors,
        fields=FIELD_KEYS,
        field_labels=FIELD_LABELS,
        outcomes=outcomes,
        client_message=group["client_message"],
        last_updated=snapshot.get("_last_updated", "Не обновлялось"),
    )


def _json_data_report(snapshot: dict) -> dict:
    companies = []
    total_found = total_confirmed = total_conditional = total_review = total_contextual = 0
    total_possible = len(INSURERS) * len(FIELD_KEYS)
    for insurer in INSURERS:
        name = insurer.name
        company_data = snapshot.get(name, {})
        fields = []
        counts = {"confirmed": 0, "conditional": 0, "review": 0, "missing": 0}
        source_counts = {"pdf": 0, "official": 0, "internet": 0, "fallback": 0}
        for meta in KASKO_FIELDS:
            key, label = meta["key"], meta["label"]
            item = company_data.get(key, {})
            raw = item.get("raw_field", {}) if isinstance(item, dict) else {}
            value = item.get("value", "Не найдено") if isinstance(item, dict) else "Не найдено"
            raw_found = value not in (None, "", "Не найдено") and not str(value).startswith("Не найдено в тексте правил")
            quality = item.get("quality_status", "missing") if isinstance(item, dict) else "missing"
            if quality not in counts:
                quality = "review"
            counts[quality] += 1
            total_contextual += int(bool(item.get("diagnostic_value"))) if isinstance(item, dict) else 0
            source = item.get("source", "none") if isinstance(item, dict) else "none"
            if source == "pdf": source_counts["pdf"] += 1
            elif source == "official": source_counts["official"] += 1
            elif source == "internet": source_counts["internet"] += 1
            elif source == "fallback": source_counts["fallback"] += 1
            pages = raw.get("text_search_pages") or []
            quote = item.get("evidence_quote") if isinstance(item, dict) else ""
            source_url = item.get("url") if isinstance(item, dict) else None
            fields.append({
                "label": label, "raw_found": raw_found, "value": value,
                "evidence_items": ([{"page": ", ".join(str(p) for p in pages), "section": raw.get("source_clause_refs", ""), "quote": quote}] if quote or pages else []),
                "analysis_status": raw.get("source_analysis_status", ""),
                "analysis_answer": item.get("diagnostic_value") or value if isinstance(item, dict) else value,
                "analysis_explanation": item.get("quality_reason", "") if isinstance(item, dict) else "",
                "analysis_missing": "" if raw_found else "Ответ отсутствует в JSON.",
                "analysis_validation": raw.get("source_quote_check", "") or (item.get("quality_reason", "") if isinstance(item, dict) else ""),
                "analysis_source_url": source_url, "source_level": item.get("source_level", 4) if isinstance(item, dict) else 4,
                "source_label": {
                    "pdf": "Официальные правила PDF",
                    "official": "Официальный сайт",
                    "internet": "Интернет-источник",
                    "fallback": "Резервный источник",
                }.get(source, "Источник требует уточнения"),
                "page_number": ", ".join(str(p) for p in pages), "source_url": source_url,
                "quality_status": quality,
                "quality_label": item.get("quality_label", "Перепроверить") if isinstance(item, dict) else "Не найдено",
                "quality_reason": item.get("quality_reason", "") if isinstance(item, dict) else "",
                "checked_at": snapshot.get("_last_updated", ""), "quarantined": raw_found and quality not in {"confirmed", "conditional"},
            })
        found = counts["confirmed"] + counts["conditional"]
        total_found += found
        total_confirmed += counts["confirmed"]
        total_conditional += counts["conditional"]
        total_review += counts["review"]
        companies.append({
            "name": name, "found_count": found, "missing_count": len(FIELD_KEYS) - found,
            "confirmed_count": counts["confirmed"], "conditional_count": counts["conditional"],
            "review_count": counts["review"], "contextual_answer_count": sum(bool(company_data.get(k, {}).get("diagnostic_value")) for k in FIELD_KEYS),
            "official_pdf_count": source_counts["pdf"], "official_count": source_counts["official"],
            "web_count": source_counts["internet"], "fallback_count": source_counts["fallback"],
            "quarantined_count": sum(bool(f["quarantined"]) for f in fields),
            "last_checked": snapshot.get("_last_updated"), "latest_run": None, "fields": fields,
        })
    return {
        "analysis_counts": {
            status: sum(
                1 for name in COMPANIES for item in snapshot.get(name, {}).values()
                if isinstance(item, dict)
                and (item.get("raw_field") or {}).get("source_analysis_status") == status
            )
            for status in ("found", "partial", "not_found")
        },
        "total_found": total_found, "total_possible": total_possible,
        "coverage_percent": round(100 * total_found / total_possible) if total_possible else 0,
        "total_confirmed": total_confirmed, "total_conditional": total_conditional,
        "total_contextual_answers": total_contextual, "total_review": total_review, "companies": companies,
    }


@app.route("/data-report")
def data_report():
    # Service menu: only the owner sees how the answers are filled in.
    if web_accounts.enabled() and not web_accounts.is_admin():
        abort(404)
    snapshot = comparison_service.load_snapshot()
    report = (_json_data_report(snapshot) if snapshot.get("_data_source") == "normalized_json"
              else data_quality_report_service.load())
    return render_template(
        "data_report.html",
        report=report,
        active_section="report",
        last_updated=snapshot.get("_last_updated", "Не обновлялось"),
    )


@app.route("/health")
def health():
    snapshot = comparison_service.load_snapshot()
    companies_with_data = sum(
        1
        for company in COMPANIES
        if isinstance(snapshot.get(company), dict) and snapshot.get(company)
    )
    audit_status_counts = {}
    for company in COMPANIES:
        company_data = snapshot.get(company)
        if not isinstance(company_data, dict):
            continue
        for field in company_data.values():
            if not isinstance(field, dict):
                continue
            raw_field = field.get("raw_field")
            if not isinstance(raw_field, dict):
                raw_field = field
            status = raw_field.get("source_analysis_status") or "missing"
            audit_status_counts[status] = audit_status_counts.get(status, 0) + 1
    return jsonify(
        {
            "status": "ok",
            "companies_configured": len(COMPANIES),
            "companies_with_data": companies_with_data,
            "last_updated": snapshot.get("_last_updated"),
            "data_source": snapshot.get("_data_source", "database"),
            "dataset_version": snapshot.get("_dataset_version"),
            "audit_status_counts": audit_status_counts,
        }
    )


@app.route("/update")
def update():
    return (
        "Сбор данных выполняется отдельным ежедневным GitHub Actions pipeline. "
        "Веб-приложение больше не запускает долгий сбор внутри Vercel.",
        409,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
