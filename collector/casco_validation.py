"""Fail-closed evidence gate; uncertain statements remain review candidates."""
from dataclasses import dataclass
import re
import unicodedata
from collector.casco_sources import official_url
from collector.casco_provider import FIELD_KEYS
from core.condition_audit import audit_condition
from core.numeric_evidence import numeric_text
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
                  source_type: str = "pdf", source_level: int = 1,
                  require_evidence: bool = True) -> Verdict:
    def fail(reason):
        return Verdict(False, reason)
    if key not in FIELD_KEYS or source_type not in {"pdf", "official_site", "web_search", "fallback"}:
        return fail("unofficial_or_diagnostic_source")
    if source_level in {1, 2} and not official_url(insurer, source_url):
        return fail("unofficial_or_diagnostic_source")
    if not document.promotable:
        return fail("parser_degraded")
    if not isinstance(fact, dict):
        return fail("invalid_fact")
    value, quote, page, section = (fact.get(k) for k in ("value", "exact_quote", "page", "section"))
    # Levels 1–2 are already official product sources. The model's contextual
    # answer is accepted without a second quote/section gate; the source URL,
    # document checksum and AI answer remain attached for traceability.
    if (not require_evidence and source_level in {1, 2}
            and source_type in {"pdf", "official_site"}
            and isinstance(value, str) and value.strip()
            and fact.get("answer_status") in (None, "answered")):
        return Verdict(True, "OFFICIAL_SOURCE_AI_ANSWER")
    if (not require_evidence and source_level >= 3
            and source_type in {"web_search", "fallback"}
            and isinstance(value, str) and value.strip()):
        return Verdict(True, "OPEN_SOURCE_REVIEW")
    evidence = fact.get("evidence")
    if evidence is not None:
        if (not isinstance(evidence, list) or not 1 <= len(evidence) <= 5
                or not all(isinstance(item, dict) for item in evidence)
                or any(fact.get(part) != evidence[0].get(part)
                       for part in ("exact_quote", "page", "section"))):
            return fail("invalid_evidence_list")
    else:
        evidence = [{"exact_quote": quote, "page": page, "section": section}]
    if fact.get("answer_status") not in (None, "answered") and not all(
            isinstance(t, str) and t.strip() for t in (value, quote, section)):
        return fail("incomplete_answer")
    if not all(isinstance(t, str) and t.strip() for t in (value, quote, section)):
        return fail("missing_value_quote_section")
    quotes, contexts = [], []
    for item in evidence:
        item_quote, item_page, item_section = (item.get(k) for k in
            ("exact_quote", "page", "section"))
        if not isinstance(item_quote, str) or not isinstance(item_section, str) or not item_section.strip():
            return fail("missing_value_quote_section")
        if type(item_page) is not int or item_page not in document.pages:
            return fail("invalid_page")
        page_text, quote_n, section_n = map(normalize,
            (document.pages[item_page], item_quote, item_section))
        if len(quote_n) < 25 or quote_n not in page_text:
            return fail("quote_not_on_claimed_page")
        start = page_text.index(quote_n)
        prefix = page_text[:start + len(quote_n)]
        if not re.search(r"(?<!\w)" + re.escape(section_n) + r"(?!\w)", prefix):
            return fail("section_not_on_claimed_page")
        quotes.append(quote_n)
        contexts.append(page_text[max(0, start - 350):start + len(quote_n)])
    if fact.get("answer_status") not in (None, "answered"):
        return fail("incomplete_answer")
    # An excerpt cannot omit a nearby exclusion or a condition and reverse it.
    context = " ".join(contexts)
    value_n = normalize(value).lower()
    quote = "\n".join(quotes)
    quote_lower = quote.lower()
    if key == "terrorism" and not any(
            re.search(r"террор", item.lower()) and re.search(
                r"покрыв|включ|возмещ|страхов\w*\s+случ|не\s+(?:покрыв|возмещ|явля)|исключ",
                item.lower()) for item in quotes):
        return fail("quote_does_not_prove_terrorism_polarity")
    if key == "total_loss" and re.search(r"за исключением[^.]{0,100}гибел", quote_lower):
        # A compensation clause that excludes constructive loss and happens
        # to mention a percentage does not establish the loss threshold.
        return fail("quote_does_not_define_total_loss")
    neg = r"не\s+(?:покрыва|возмещ|явля|включ|оплач|призна)|исключ"
    pos = r"покрыва|возмещ|включ|оплач|предостав|страховым случаем"
    coverage_fields = {"without_certificates", "gap", "self_ignition", "terrorism", "drone", "tow_truck", "repair_type"}
    if (key in coverage_fields and re.search(neg, context.lower())
            and re.search(pos, value_n) and not re.search(neg, value_n)):
        return fail("exclusion_context_requires_review")
    conditional = r"если[^.]{0,80}(?:предусмотр|договор)|при условии|по условию|по соглашению|договором|договоре|дополнительн\w*\s+(?:соглаш|плат|опци|покрыт|услов)"
    if re.search(conditional, quote_lower) and not re.search(conditional + r"|зависит|опци", value_n):
        return fail("omitted_contract_condition")
    verbs = (r"примен" if key == "franchise" else
        r"примен|производ|допуска|осуществ|требу|покрыва|возмещ|предусмотр|включ|оплач|предостав|призна")
    negative = rf"не\s+(?:{verbs})|исключен\b|исключён\b"
    value_negative = bool(re.search(negative, value_n))
    quote_negative = bool(re.search(negative, quote_lower))
    if value_negative != quote_negative and re.search(verbs, value_n) and re.search(verbs, quote_lower):
        return fail("contradictory_polarity")
    # Equal numbers do not justify reversing a threshold.
    if key == "total_loss":
        def direction(text):
            if re.search(r"не менее", text):
                return "at_least"
            if re.search(r"не более|не превыш", text):
                return "at_most"
            if re.search(r"менее|меньше", text):
                return "less_than"
            if re.search(r"более|превыш|свыше", text):
                return "greater_than"
            return None
        if direction(value_n) and direction(quote_lower) and direction(value_n) != direction(quote_lower):
            return fail("contradictory_threshold")
    # Every digit and unit in the summary must occur in the quotation, for all fields.
    number = r"\d+(?:[.,]\d+)?"
    numbers = lambda s: {v.replace(",", ".") for v in re.findall(number, s)}
    value_numeric, quote_numeric = numeric_text(value_n), numeric_text(quote_lower)
    if not numbers(value_numeric).issubset(numbers(quote_numeric)):
        return fail("unsupported_number")
    for pattern in (
        rf"({number})\s*%", rf"({number})\s*рабоч\w*\s*д",
        rf"({number})\s*календарн\w*\s*д", rf"({number})\s*руб",
    ):
        if not set(re.findall(pattern, value_numeric)).issubset(set(re.findall(pattern, quote_numeric))):
            return fail("unsupported_numeric_unit")
    # Use quote-only relevance too: a summary must not supply the missing topic.
    if not is_supported_condition(key, "Проверка условия первоисточника", quote) or not is_supported_condition(key, value, quote):
        return fail("quote_does_not_prove_field")
    issue = semantic_alignment_issue(key, value, quote)
    if issue:
        return fail(issue)
    audit = audit_condition(key, value, quote, source_level=source_level, source_type=source_type,
                            confidence=1.0, verification_status="verified")
    if audit.status not in {"confirmed", "conditional"}:
        return fail(audit.reason)
    return Verdict(True, "PASS")

