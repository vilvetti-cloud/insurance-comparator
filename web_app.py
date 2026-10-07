from __future__ import annotations

import logging

from flask import Flask, jsonify, redirect, render_template, request

from collector.registry import INSURERS
from core.catalog import KASKO_FIELDS
from core.services.comparison_service import ComparisonService
from core.services.sales_insights_service import SalesInsightsService
from core.services.sales_script_ai_service import SalesScriptAIService
from core.services.data_quality_report_service import DataQualityReportService


app = Flask(__name__)

comparison_service = ComparisonService()
sales_insights_service = SalesInsightsService()
sales_script_ai_service = SalesScriptAIService()
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
            diagnostic = contextual.get(field, {})
            failure = diagnostic.get("analysis_validation")
            prepared[f"{field}_review_note"] = (
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
    return render_template(
        "index.html",
        companies=COMPANIES,
        last_updated=snapshot.get("_last_updated", "Не обновлялось"),
    )


@app.route("/compare", methods=["GET", "POST"])
def compare():
    company1 = request.values.get("company1")
    company2 = request.values.get("company2")

    if (
        not company1
        or company1 not in COMPANIES
        or not company2
        or company2 not in COMPANIES
        or company1 == company2
    ):
        return redirect("/")

    snapshot = comparison_service.load_snapshot()
    report = data_quality_report_service.load()
    contextual = {
        company["name"]: {field["key"]: field for field in company["fields"]}
        for company in report.get("companies", [])
    }
    data1 = _prepare_company_data(snapshot, company1, contextual.get(company1))
    data2 = _prepare_company_data(snapshot, company2, contextual.get(company2))
    reportable = {"confirmed", "conditional"}
    found1 = sum(1 for field in FIELD_KEYS if data1.get(f"{field}_quality_status") in reportable)
    found2 = sum(1 for field in FIELD_KEYS if data2.get(f"{field}_quality_status") in reportable)
    comparable_fields = [
        field
        for field in FIELD_KEYS
        if data1.get(f"{field}_sales_eligible") and data2.get(f"{field}_sales_eligible")
    ]
    comparison_ready = len(comparable_fields) > 0

    if comparison_ready:
        sales = sales_insights_service.analyze(
            company=company1,
            competitor=company2,
            data=data1,
            competitor_data=data2,
            field_labels=FIELD_LABELS,
        )
        sales = sales_script_ai_service.enrich(
            company=company1,
            competitor=company2,
            sales=sales,
        )
    else:
        sales = {
            "advantages": [],
            "cards": [],
            "cautions": [],
            "client_message": "",
        }

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
        found1=found1,
        found2=found2,
        last_updated=snapshot.get("_last_updated", "Не обновлялось"),
    )


@app.route("/data-report")
def data_report():
    report = data_quality_report_service.load()
    return render_template("data_report.html", report=report)


@app.route("/health")
def health():
    snapshot = comparison_service.load_snapshot()
    companies_with_data = sum(
        1
        for company in COMPANIES
        if isinstance(snapshot.get(company), dict) and snapshot.get(company)
    )
    return jsonify(
        {
            "status": "ok",
            "companies_configured": len(COMPANIES),
            "companies_with_data": companies_with_data,
            "last_updated": snapshot.get("_last_updated"),
        }
    )


@app.route("/update")
def update():
    return (
        "Сбор данных выполняется отдельным ежедневным GitHub Actions pipeline. "
        "Веб-приложение больше не запускает долгий сбор внутри Vercel.",
        409,
    )




# Free-provider Skills integration
try:
    from skill_manager import register_skill_routes
    register_skill_routes(app)
except Exception as _skills_exc:
    logging.getLogger(__name__).warning("Skills routes unavailable: %s", _skills_exc)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
