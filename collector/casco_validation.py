"""Fail-closed evidence gate; uncertain statements remain review candidates."""
from dataclasses import dataclass
import re
import unicodedata
from collector.casco_sources import official_url
from collector.casco_provider import FIELD_KEYS
from core.condition_audit import audit_condition
from core.evidence_quality import is_supported_condition, semantic_alignment_issue


def normalize(text: str) -> str:
    # Whitespace and Unicode normalization only; never delete punctuation,
    # negations or words to manufacture a matching quotation.
    return " ".join(unicodedata.normalize("NFKC", text).split())


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str


def validate_fact(key: str, fact: dict, document, *, insurer: str, source_url: str,
                  source_type: str = "pdf") -> Verdict:
    def fail(reason):
        return Verdict(False, reason)
    if key not in FIELD_KEYS or source_type != "pdf" or not official_url(insurer, source_url):
        return fail("unofficial_or_diagnostic_source")
    if not document.promotable:
        return fail("parser_degraded")
    if not isinstance(fact, dict):
        return fail("invalid_fact")
    value, quote, page, section = (fact.get(k) for k in ("value", "exact_quote", "page", "section"))
    if not all(isinstance(t, str) and t.strip() for t in (value, quote, section)):
        return fail("missing_value_quote_section")
    if type(page) is not int or page not in document.pages:
        return fail("invalid_page")
    page_text, quote_n, section_n = map(normalize, (document.pages[page], quote, section))
    if len(quote_n) < 25 or quote_n not in page_text:
        return fail("quote_not_on_claimed_page")
    start = page_text.index(quote_n)
    # Section must actually precede/contain this quote on this page.
    prefix = page_text[:start + len(quote_n)]
    if not re.search(r"(?<!\w)" + re.escape(section_n) + r"(?!\w)", prefix):
        return fail("section_not_on_claimed_page")
    # An excerpt cannot omit a nearby exclusion or a condition and reverse it.
    context = page_text[max(0, start - 350):start + len(quote_n)]
    value_n = normalize(value).lower()
    quote_lower = quote_n.lower()
    neg = r"не\s+(?:покрыва|возмещ|явля|предусмотр|включ|оплач|призна)|исключ"
    pos = r"покрыва|возмещ|включ|оплач|предостав|страховым случаем"
    if re.search(neg, context.lower()) and re.search(pos, value_n) and not re.search(neg, value_n):
        return fail("exclusion_context_requires_review")
    conditional = r"если[^.]{0,80}(?:предусмотр|договор)|при условии|по соглашению|договором|договоре|дополнительн\\w*\\s+(?:соглаш|плат|опци|покрыт|услов)"
    if re.search(conditional, quote_lower) and not re.search(conditional + r"|зависит|опци", value_n):
        return fail("omitted_contract_condition")
    # Every digit and unit in the summary must occur in the quotation, for all fields.
    number = r"\d+(?:[.,]\d+)?"
    numbers = lambda s: {v.replace(",", ".") for v in re.findall(number, s)}
    if not numbers(value_n).issubset(numbers(quote_lower)):
        return fail("unsupported_number")
    for pattern in (
        rf"({number})\s*%", rf"({number})\s*рабоч\w*\s*д",
        rf"({number})\s*календарн\w*\s*д", rf"({number})\s*руб",
    ):
        if not set(re.findall(pattern, value_n)).issubset(set(re.findall(pattern, quote_lower))):
            return fail("unsupported_numeric_unit")
    # Use quote-only relevance too: a summary must not supply the missing topic.
    if not is_supported_condition(key, "Проверка условия первоисточника", quote) or not is_supported_condition(key, value, quote):
        return fail("quote_does_not_prove_field")
    issue = semantic_alignment_issue(key, value, quote)
    if issue:
        return fail(issue)
    audit = audit_condition(key, value, quote, source_level=1, source_type="pdf",
                            confidence=1.0, verification_status="verified")
    if audit.status not in {"confirmed", "conditional"}:
        return fail(audit.reason)
    return Verdict(True, "PASS")
