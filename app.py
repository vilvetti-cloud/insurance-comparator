# app.py — PDF + ИНТЕРНЕТ-ПОИСК (DuckDuckGo + Groq)

from flask import Flask, render_template, request, redirect
from datetime import datetime
import json
import os
import requests
import urllib3
import re
import time
import random
import io
import threading
from urllib.parse import urljoin, urlparse, quote_plus
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
import logging


# ============================================================
# НАСТРОЙКИ
# ============================================================

app = Flask(__name__)

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# GROQ
# ============================================================

GROQ_API_KEY = os.environ.get(
    "GROQ_API_KEY",
    ""
)

GROQ_MODEL = os.environ.get(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
)

GROQ_URL = (
    "https://api.groq.com/openai/v1/chat/completions"
)

GROQ_RETRIES = 2

# Таймаут Groq
GROQ_CONNECT_TIMEOUT = 10
GROQ_READ_TIMEOUT = 60

# Максимальный размер текста для Groq
MAX_GROQ_TEXT_LENGTH = 6000


# ============================================================
# ФАЙЛ ДАННЫХ
# ============================================================

DATA_FILE = os.environ.get("CASCO_COMPARISON_DATA_FILE", "data/casco-comparison-master.json")

# Автоматический сбор при запуске
UPDATE_ON_START = False

# Защита от параллельных обновлений
UPDATE_LOCK = threading.Lock()

UPDATE_RUNNING = False


# ============================================================
# HTTP НАСТРОЙКИ
# ============================================================

HTTP_CONNECT_TIMEOUT = 10
HTTP_READ_TIMEOUT = 20

HTTP_RETRIES = 2

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0"
]


# ============================================================
# ИСТОЧНИКИ СТРАХОВЫХ
# ============================================================

COMPANY_SOURCES = {
    "РЕСО-Гарантия": {
        "url": "https://reso.ru/individual/auto/kasko/",
        "type": "html"
    },
    "ВСК": {
        "url": "https://www.vsk.ru/klientam/avto/kasko/",
        "type": "html"
    },
    "Ингосстрах": {
        "url": "https://www.ingos.ru/auto/kasko/",
        "type": "html"
    },
    "Ренессанс Страхование": {
        "url": "https://www.renins.ru/auto/kasko/",
        "type": "html"
    },
    "АльфаСтрахование": {
        "url": "https://www.alfastrah.ru/individuals/auto/kasko/",
        "type": "html"
    },
    "Согласие": {
        "url": "https://www.soglasie.ru/individuals/avto/kasko/",
        "type": "html"
    },
    "Росгосстрах": {
        "url": "https://www.rgs.ru/auto/ekasko/",
        "type": "html"
    },
    "Т-Страхование": {
        "url": "https://www.tbank.ru/insurance/kasko/",
        "type": "html"
    },
    "СберСтрахование": {
        "url": "https://sberbankins.ru/products/kasko/",
        "type": "html"
    },
    "Югория": {
        "url": "https://ugsk.ru/auto/kasko/",
        "type": "html"
    },
    "Совкомбанк Страхование": {
        "url": "https://sovcomins.ru/about/rules-and-tariffs/",
        "type": "html"
    }
}


# ============================================================
# ПОЛЯ КАСКО
# ============================================================

KASKO_FIELDS = [
    "franchise",
    "without_certificates",
    "gap",
    "total_loss",
    "self_ignition",
    "terrorism",
    "drone",
    "tow_truck",
    "repair_type",
    "payment_terms"
]

FIELD_LABELS = {
    "franchise": "Франшиза",
    "without_certificates": "Ремонт без справок",
    "gap": "GAP-страхование",
    "total_loss": "Порог тотала",
    "self_ignition": "Самовозгорание",
    "terrorism": "Терроризм",
    "drone": "БПЛА / Дроны",
    "tow_truck": "Эвакуатор",
    "repair_type": "Тип ремонта",
    "payment_terms": "Сроки выплаты / направления"
}

FIELD_SEARCH_QUERIES = {
    "franchise": "Какая франшиза у КАСКО {company}",
    "without_certificates": "Выплата без справок по КАСКО {company}",
    "gap": "GAP страхование КАСКО {company}",
    "total_loss": "Порог тотала КАСКО {company}",
    "self_ignition": "Самовозгорание КАСКО {company}",
    "terrorism": "Терроризм КАСКО {company}",
    "drone": "БПЛА КАСКО {company}",
    "tow_truck": "Эвакуатор КАСКО {company}",
    "repair_type": "Тип ремонта КАСКО {company}",
    "payment_terms": "Срок выплаты КАСКО {company}"
}

FIELD_GROQ_PROMPTS = {
    "franchise": "Найди в тексте информацию о франшизе по КАСКО. Напиши кратко: какой тип франшизы (безусловная, условно-безусловная), как применяется. Если информации нет — напиши 'Не найдено'.",
    "without_certificates": "Найди информацию об условиях выплаты без справок по КАСКО. Что покрывается, сколько раз. Если нет — 'Не найдено'.",
    "gap": "Есть ли GAP страхование? Как включается? Если нет — 'Не найдено'.",
    "total_loss": "Какой порог тотала (полной гибели) в процентах от страховой суммы? Если нет — 'Не найдено'.",
    "self_ignition": "Покрывается ли самовозгорание / пожар? Если нет — 'Не найдено'.",
    "terrorism": "Покрывается ли терроризм? Есть ли ограничения (только МСК и МО)? Если нет — 'Не найдено'.",
    "drone": "Покрывается ли ущерб от БПЛА / дронов? Есть ли лимит? Если нет — 'Не найдено'.",
    "tow_truck": "Какие лимиты по эвакуатору (суммы)? Если нет — 'Не найдено'.",
    "repair_type": "Где делают ремонт (дилер, СТОА, выплата)? Если нет — 'Не найдено'.",
    "payment_terms": "Срок выплаты в рабочих днях? Если нет — 'Не найдено'."
}


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Connection": "close",
        "Cache-Control": "no-cache",
    }


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def fetch_url(url: str, retries: int = HTTP_RETRIES, timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
    last_error = None

    if timeout is not None:
        connect_timeout = min(timeout, HTTP_CONNECT_TIMEOUT)
        read_timeout = timeout
    else:
        connect_timeout = HTTP_CONNECT_TIMEOUT
        read_timeout = HTTP_READ_TIMEOUT

    for attempt in range(1, retries + 1):
        try:
            logger.info("🌐 Запрос: %s (попытка %s/%s)", url[:80], attempt, retries)

            response = requests.get(
                url,
                headers=get_headers(),
                timeout=(connect_timeout, read_timeout),
                verify=False,
                allow_redirects=True
            )

            status = response.status_code
            content_type = response.headers.get("Content-Type", "").lower()

            logger.info("📡 HTTP %s: %s", status, url[:80])

            if status == 200:
                return {
                    "success": True,
                    "status": status,
                    "content": response.content,
                    "text": response.text,
                    "url": response.url,
                    "content_type": content_type
                }

            if status == 403:
                logger.warning("⚠️ HTTP 403 для %s", url[:80])
                if attempt < retries:
                    time.sleep(2 * attempt)
                continue

            if status == 429:
                logger.warning("⏳ Rate limit, ждём %s сек.", 5 * attempt)
                time.sleep(5 * attempt)
                continue

            if status in (500, 502, 503, 504):
                logger.warning("⚠️ Серверная ошибка %s, ждём", status)
                time.sleep(3 * attempt)
                continue

            return {
                "success": False,
                "status": status,
                "error": f"HTTP {status}"
            }

        except Exception as exc:
            last_error = exc
            logger.warning("⚠️ Ошибка: %s (попытка %s/%s)", str(exc)[:50], attempt, retries)
            if attempt < retries:
                time.sleep(2 * attempt)

    logger.error("❌ Не удалось загрузить: %s", url[:80])
    return None


# ============================================================
# ПОИСК PDF НА СТРАНИЦЕ
# ============================================================

def find_pdf_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    pdf_links = []

    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()
        if not href:
            continue

        full_url = urljoin(base_url, href)
        if not full_url.startswith(("http://", "https://")):
            continue

        text = tag.get_text(" ", strip=True).lower()
        href_lower = href.lower()

        is_pdf = ".pdf" in href_lower or ".pdf" in text
        is_rules = any(kw in text for kw in ["правила", "условия", "каско", "kasko", "полис"])

        if is_pdf or is_rules:
            if full_url not in pdf_links:
                pdf_links.append(full_url)

    # Фильтруем мусор
    filtered = []
    for url in pdf_links:
        if any(x in url.lower() for x in ["cookie", "privacy", "policy", "soglasie_pd", "politika"]):
            continue
        filtered.append(url)

    logger.info("📚 Найдено PDF/документов: %s", len(filtered))
    for i, url in enumerate(filtered[:5], 1):
        logger.info("   %s. %s", i, url)

    return filtered[:5]


# ============================================================
# ИЗВЛЕЧЕНИЕ ТЕКСТА ИЗ PDF
# ============================================================

def extract_text_from_pdf(content: bytes) -> str:
    if not content or content[:4] != b"%PDF":
        return ""

    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        pages = []

        for page in reader.pages:
            try:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text)
            except:
                continue

        result = clean_text("\n\n".join(pages))
        logger.info("📄 PDF: страниц=%s, символов=%s", len(reader.pages), len(result))
        return result
    except Exception as exc:
        logger.warning("⚠️ Ошибка PDF: %s", str(exc)[:50])
        return ""


# ============================================================
# ПОИСК В ИНТЕРНЕТЕ (DuckDuckGo)
# ============================================================

def search_duckduckgo(query: str) -> List[str]:
    """Поиск через DuckDuckGo, возвращает список URL"""
    encoded = quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    response = fetch_url(url, retries=2)
    if not response or not response.get("success"):
        logger.warning("⚠️ DuckDuckGo не отвечает")
        return []

    html = response.get("text", "")
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for result in soup.find_all("a", class_="result__a"):
        href = result.get("href")
        if href and href.startswith("http"):
            links.append(href)

    # Альтернативный способ
    for tag in soup.find_all("a", href=True):
        href = tag.get("href")
        if href and "//duckduckgo.com/l/" in href:
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                import urllib.parse
                real_url = urllib.parse.unquote(match.group(1))
                if real_url.startswith("http") and "duckduckgo.com" not in real_url:
                    links.append(real_url)

    # Убираем дубли
    unique = []
    seen = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    logger.info("🔍 DuckDuckGo: '%s' → %s результатов", query[:50], len(unique))
    return unique[:3]


# ============================================================
# GROQ-ЗАПРОС (ОДИН)
# ============================================================

def groq_ask(system_prompt: str, user_prompt: str, max_tokens: int = 800) -> Optional[str]:
    if not GROQ_API_KEY:
        logger.error("❌ GROQ_API_KEY не задан")
        return None

    for attempt in range(1, GROQ_RETRIES + 1):
        try:
            response = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": max_tokens
                },
                timeout=(GROQ_CONNECT_TIMEOUT, GROQ_READ_TIMEOUT)
            )

            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    return content.strip()

            if response.status_code == 429:
                logger.warning("⏳ Rate limit, ждём %s сек.", 5 * attempt)
                time.sleep(5 * attempt)
                continue

            if response.status_code == 413:
                logger.warning("⚠️ Слишком большой запрос, пробуем меньше")
                return None

            logger.warning("⚠️ Groq HTTP %s: %s", response.status_code, response.text[:100])

        except Exception as exc:
            logger.warning("⚠️ Groq ошибка: %s", str(exc)[:50])
            if attempt < GROQ_RETRIES:
                time.sleep(3 * attempt)

    return None


# ============================================================
# ИЗВЛЕЧЕНИЕ ПОЛЯ ИЗ ТЕКСТА (ЧЕРЕЗ GROQ)
# ============================================================

def extract_field_from_text(text: str, company: str, field: str) -> Optional[str]:
    """Groq извлекает одно поле из текста"""
    if len(text) > MAX_GROQ_TEXT_LENGTH:
        text = text[:MAX_GROQ_TEXT_LENGTH]

    system_prompt = """Ты — эксперт по страхованию. Извлекай информацию ТОЛЬКО из текста. 
Если информации нет — отвечай "Не найдено". Отвечай кратко, только по существу."""

    user_prompt = f"""Компания: {company}
Поле: {FIELD_LABELS.get(field, field)}
Вопрос: {FIELD_GROQ_PROMPTS.get(field, "Найди информацию по полю")}

Текст:
{text}

Ответ:"""

    result = groq_ask(system_prompt, user_prompt, max_tokens=300)
    if result and len(result) > 3 and "не найдено" not in result.lower():
        return result
    return None


# ============================================================
# ПОИСК ПОЛЯ В ИНТЕРНЕТЕ (DuckDuckGo + Groq)
# ============================================================

def search_field_in_internet(company: str, field: str) -> Optional[Dict[str, Any]]:
    """Ищет поле через интернет"""
    query = FIELD_SEARCH_QUERIES.get(field, "").format(company=company)
    logger.info("🔍 Интернет-поиск: %s", query)

    urls = search_duckduckgo(query)
    if not urls:
        logger.warning("❌ Нет результатов для: %s", query)
        return None

    for url in urls:
        logger.info("📖 Читаем: %s", url[:60])
        response = fetch_url(url, retries=1, timeout=15)

        if not response or not response.get("success"):
            continue

        html = response.get("text", "")
        if not html:
            continue

        # Извлекаем текст из HTML
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()
        text = clean_text(soup.get_text())

        if len(text) < 100:
            continue

        # Отправляем в Groq
        answer = extract_field_from_text(text, company, field)
        if answer:
            logger.info("✅ Найдено: %s", answer[:80])
            return {
                "value": answer,
                "url": url,
                "source": "internet"
            }

    logger.warning("❌ Не найдено в интернете: %s", FIELD_LABELS.get(field, field))
    return None


# ============================================================
# СБОР ДАННЫХ ДЛЯ ОДНОЙ КОМПАНИИ
# ============================================================

def collect_company_data(company: str) -> Dict[str, Any]:
    logger.info("")
    logger.info("=" * 70)
    logger.info("🏢 НАЧИНАЕМ: %s", company)
    logger.info("=" * 70)

    source = COMPANY_SOURCES.get(company)
    if not source:
        logger.error("❌ Источник не найден")
        return {}

    url = source.get("url")
    result = {}

    # --- ШАГ 1: Загружаем страницу ---
    logger.info("🌐 Загрузка: %s", url)
    response = fetch_url(url)

    if not response or not response.get("success"):
        logger.error("❌ Не удалось загрузить страницу")
        return {}

    html = response.get("text", "")
    if not html:
        logger.error("❌ Нет HTML")
        return {}

    # --- ШАГ 2: Ищем PDF ---
    pdf_links = find_pdf_links(html, url)

    pdf_text = None
    if pdf_links:
        for pdf_url in pdf_links:
            logger.info("📥 PDF: %s", pdf_url[:60])
            pdf_response = fetch_url(pdf_url, retries=2, timeout=30)
            if pdf_response and pdf_response.get("success"):
                content = pdf_response.get("content", b"")
                if content:
                    extracted = extract_text_from_pdf(content)
                    if extracted and len(extracted) > 200:
                        pdf_text = extracted
                        logger.info("✅ PDF загружен, %s символов", len(pdf_text))
                        break

    # --- ШАГ 3: Если есть PDF — ищем поля в нём ---
    found_fields = set()

    if pdf_text:
        logger.info("📄 Анализируем PDF через Groq")
        for field in KASKO_FIELDS:
            answer = extract_field_from_text(pdf_text, company, field)
            if answer:
                result[field] = {
                    "value": answer,
                    "source": "pdf",
                    "url": pdf_links[0] if pdf_links else None
                }
                found_fields.add(field)
                logger.info("  ✅ %s: %s", FIELD_LABELS.get(field, field), answer[:60])

    # --- ШАГ 4: Если поля не найдены — ищем в интернете ---
    for field in KASKO_FIELDS:
        if field in found_fields:
            continue

        logger.info("🔍 Ищем в интернете: %s", FIELD_LABELS.get(field, field))
        search_result = search_field_in_internet(company, field)

        if search_result:
            result[field] = {
                "value": search_result["value"],
                "source": "internet",
                "url": search_result["url"]
            }
            found_fields.add(field)
        else:
            result[field] = {
                "value": "Не найдено",
                "source": "none",
                "url": None
            }

    # --- ШАГ 5: Итог ---
    logger.info("")
    logger.info("📊 %s: собрано %s/%s полей", company, len(found_fields), len(KASKO_FIELDS))
    return result


# ============================================================
# СОХРАНЕНИЕ / ЗАГРУЗКА
# ============================================================

def save_data(data: Dict[str, Any]) -> bool:
    # The normalized JSON is the read-only source of truth.
    if os.path.basename(DATA_FILE) == "casco-comparison-master.json":
        logger.warning("Эталонный JSON нельзя перезаписывать автоматическим сбором")
        return False
    try:
        with open(DATA_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(DATA_FILE + ".tmp", DATA_FILE)
        return True
    except Exception as exc:
        logger.exception("Ошибка сохранения: %s", exc)
        return False


def load_data() -> Dict[str, Any]:
    """Read normalized official-PDF facts; do not scrape at startup."""
    if not os.path.exists(DATA_FILE):
        logger.error("Не найден эталонный JSON: %s", DATA_FILE)
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            master = json.load(f)
        if not isinstance(master, dict) or not isinstance(master.get("companies"), list):
            logger.error("Неверная структура JSON: нужен массив companies")
            return {}
        result: Dict[str, Any] = {
            "_last_updated": master.get("created_date", "Дата не указана"),
            "_fields": KASKO_FIELDS,
            "_structured": master,
        }
        for company in master["companies"]:
            name = company.get("name")
            if not name:
                continue
            row: Dict[str, Any] = {}
            source_url = company.get("source_url") or COMPANY_SOURCES.get(name, {}).get("url")
            for item in company.get("fields", []):
                key = item.get("key")
                if key not in KASKO_FIELDS:
                    continue
                answer = (item.get("direct_answer") or "").strip() or "Не найдено"
                notes = []
                for label, prop in (("Подробные условия", "key_conditions"),
                                    ("Числовые параметры", "numeric_parameters"),
                                    ("Ограничения", "limitations"),
                                    ("Пункты Правил", "source_clause_refs")):
                    if item.get(prop):
                        notes.append(label + ": " + str(item[prop]))
                pages = item.get("text_search_pages") or item.get("page_number")
                if pages:
                    if not isinstance(pages, list):
                        pages = [pages]
                    notes.append("Страницы PDF: " + ", ".join(str(p) for p in pages))
                if item.get("evidence_quote"):
                    notes.append("Цитата / доказательство: " + str(item["evidence_quote"]))
                if item.get("audit_status"):
                    notes.append("Статус проверки источника: " + str(item["audit_status"]))
                row[key] = {"value": answer, "source": "pdf" if source_url else "none",
                            "url": source_url, "source_level": 1 if source_url else 4,
                            "review_note": " ".join(notes), "raw_field": item}
            result[name] = row
        return result
    except Exception as exc:
        logger.exception("Ошибка загрузки эталонного JSON: %s", exc)
        return {}


# ============================================================
# СБОР ВСЕХ КОМПАНИЙ
# ============================================================

def collect_all_data() -> Dict[str, Any]:
    global UPDATE_RUNNING

    if not UPDATE_LOCK.acquire(blocking=False):
        logger.warning("⚠️ Обновление уже выполняется")
        return load_data()

    UPDATE_RUNNING = True

    try:
        logger.info("")
        logger.info("#" * 70)
        logger.info("🚀 НАЧИНАЕМ ПОЛНОЕ ОБНОВЛЕНИЕ")
        logger.info("#" * 70)

        companies = list(COMPANY_SOURCES.keys())
        result = {}
        successful = 0

        for index, company in enumerate(companies, 1):
            logger.info("")
            logger.info("🏁 Компания %s/%s: %s", index, len(companies), company)

            try:
                company_data = collect_company_data(company)
                result[company] = company_data

                has_data = any(
                    isinstance(v, dict) and v.get("value") and v.get("value") != "Не найдено"
                    for v in company_data.values()
                )

                if has_data:
                    successful += 1
                    logger.info("✅ Компания обработана: %s", company)
                else:
                    logger.warning("⚠️ Нет данных для: %s", company)

            except Exception as exc:
                logger.exception("🔥 Ошибка: %s", exc)
                result[company] = {
                    field: {"value": "Не найдено", "source": "error", "url": None}
                    for field in KASKO_FIELDS
                }

            # Промежуточное сохранение
            partial = dict(result)
            partial["_last_updated"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            partial["_fields"] = KASKO_FIELDS
            save_data(partial)

            if index < len(companies):
                time.sleep(2 + random.uniform(0.5, 1.5))

        final_updated = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        result["_last_updated"] = final_updated
        result["_fields"] = KASKO_FIELDS
        save_data(result)

        logger.info("")
        logger.info("#" * 70)
        logger.info("🏁 ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
        logger.info("Успешно: %s/%s", successful, len(companies))
        logger.info("Дата: %s", final_updated)
        logger.info("#" * 70)

        return result

    finally:
        UPDATE_RUNNING = False
        try:
            UPDATE_LOCK.release()
        except:
            pass


# ============================================================
# FLASK ROUTES
# ============================================================

app = Flask(__name__)


def _master_company_map(data):
    return {c.get("name"): c for c in data.get("_structured", {}).get("companies", [])}


def _structured_field(data, company_name, key):
    c = _master_company_map(data).get(company_name, {})
    return next((f for f in c.get("fields", []) if f.get("key") == key), {})


def _answer_unknown(answer):
    t = (answer or "").casefold()
    return any(x in t for x in ("прямо не упомянут", "не подтверждён", "не подтвержден",
        "не найден", "не установлено", "не установлен", "не установлена",
        "не установлены", "не подтверждено", "не подтверждена", "нет прямого упоминания", "нет отдельного понятия", "прямо не обозначен"))


def _risk_signal(field, key):
    answer = (field.get("direct_answer") or "").casefold()
    text = answer + " " + (field.get("key_conditions") or "").casefold()
    unknown = _answer_unknown(answer)
    if key == "gap":
        positive = not unknown and any(x in text for x in ("предусмотрен как отдельный риск",
            "предусмотрен отдельным приложением", "указан как отдельный риск",
            "предусмотрен отдельными правилами", "gap оформляется как отдельный риск",
            "gap предусмотрен как отдельный риск", "gap-страхование предусмотрено как отдельный риск"))
        negative = not unknown and any(x in answer for x in ("исключён", "исключен", "не покрывается"))
    elif key == "terrorism":
        positive = not unknown and any(x in text for x in ("предусмотрен как дополнительный риск",
            "может быть застрахован дополнительно", "терроризм описан как страховой риск",
            "покрытие терроризма предусмотрено"))
        negative = not unknown and any(x in answer for x in ("исключён по общему правилу",
            "исключен по общему правилу", "не покрывается по общему правилу",
            "исключён, если специально не предусмотрен", "исключен, если специально не предусмотрен",
            "не покрывается"))
    elif key == "self_ignition":
        positive = not unknown and any(x in text for x in ("включено в определение пожара",
            "предусмотрено как отдельный описанный риск", "самовозгорание включено", "риск «самовозгорание» определён", "риск самовозгорание определён", "самовозгорание тс прямо включено"))
        negative = not unknown and any(x in text for x in ("исключено из стандартного покрытия",
            "исключено по умолчанию", "внутренний пожар исключён", "внутренний пожар исключен",
            "ограничено исключением", "не отнесено самовозгорание", "не включено самовозгорание", "не относится к пожару"))
    else:
        return False, False, unknown
    return positive, negative, unknown


def compare_field(data, company1, company2, key):
    a = _structured_field(data, company1, key)
    b = _structured_field(data, company2, key)
    x = (a.get("direct_answer") or "").strip()
    y = (b.get("direct_answer") or "").strip()
    if not x or not y:
        return {"outcome": "incomparable", "title": "Недостаточно данных",
                "reason": "Нет двух сопоставимых ответов в эталонной базе."}
    pos1, neg1, unk1 = _risk_signal(a, key)
    pos2, neg2, unk2 = _risk_signal(b, key)
    # Any positive-vs-unknown/excluded signal remains conditional on the individual policy.
    if pos1 and (neg2 or unk2):
        return {"outcome": "conditional_first_advantage", "title": "Возможное преимущество " + company1,
                "reason": "В правилах первой компании риск описан явно; у конкурента покрытие не подтверждено либо ограничено. Это не доказывает отсутствие покрытия у конкурента — проверьте программу и полис."}
    if pos2 and (neg1 or unk1):
        return {"outcome": "conditional_competitor_advantage", "title": "Возможное преимущество " + company2,
                "reason": "В правилах конкурента риск описан явно; у первой компании покрытие не подтверждено либо ограничено. Проверьте включение риска в договор."}
    if " ".join(x.casefold().split()) == " ".join(y.casefold().split()):
        return {"outcome": "equal", "title": "Сопоставимые краткие ответы",
                "reason": "Краткие ответы совпадают; индивидуальные условия и исключения договора могут отличаться."}
    if unk1 or unk2:
        return {"outcome": "incomparable", "title": "Нельзя уверенно сравнить",
                "reason": "В одном из источников прямое покрытие не подтверждено или риск не упомянут. Отсутствие упоминания не считается исключением."}
    return {"outcome": "incomparable", "title": "Нужна проверка сопоставимых условий",
            "reason": "Формулировки различаются. Для вывода о преимуществе нужно сопоставить одинаковые лимиты, основания отсчёта и условия договора."}


def build_sales_summary(data, company1, company2, comparison_by_field):
    labels = {"gap": "GAP-страхование", "terrorism": "Терроризм", "self_ignition": "Самовозгорание"}
    why = {
        "gap": "GAP может компенсировать часть финансовой потери при тотальной гибели или хищении, но действует только при выполнении условий и включении риска в договор.",
        "terrorism": "Отдельное включение риска может расширить защиту, однако описание риска в Правилах не заменяет проверку выбранной программы и полиса.",
        "self_ignition": "Явное описание самовозгорания помогает понять рамки риска, но нужно учитывать исключения и обстоятельства возникновения пожара.",
    }
    cards = []
    for key, comp in comparison_by_field.items():
        if comp.get("outcome") not in ("first_advantage", "conditional_first_advantage"):
            continue
        a, b = _structured_field(data, company1, key), _structured_field(data, company2, key)
        cards.append({"kind": "conditional_advantage" if comp["outcome"] == "conditional_first_advantage" else "advantage",
            "title": labels.get(key, FIELD_LABELS.get(key, key)), "label": FIELD_LABELS.get(key, key),
            "own_value": a.get("direct_answer", "Не найдено"), "competitor_value": b.get("direct_answer", "Не найдено"),
            "why": why.get(key, "Отличие нужно проверить по индивидуальным условиям страхования.")})
    confirmed = [c for c in cards if c["kind"] == "advantage"]
    conditional = [c for c in cards if c["kind"] == "conditional_advantage"]
    if cards:
        client_message = " ".join(f'{c["label"]}: в правилах {company1} условие описано явно; у {company2} оно не подтверждено или требует отдельной проверки.' for c in cards[:3])
        client_message += " Перед оформлением сверим включение риска в выбранную программу и договор."
    else:
        client_message = f"По проверенным материалам пока нельзя доказательно заявить, что {company1} лучше {company2} по этим параметрам. Сначала сопоставим лимиты, исключения и условия конкретных договоров."
    return {"advantages": confirmed, "conditional_advantages": conditional, "cards": cards,
        "cautions": ["Отсутствие упоминания риска в Правилах не означает автоматического исключения.",
                     "Ответ по Правилам не заменяет проверку выбранной программы и индивидуального договора."],
        "client_message": client_message}


@app.route("/")
def index():
    data = load_data()
    companies = [c.get("name") for c in data.get("_structured", {}).get("companies", []) if c.get("name")]
    return render_template("index.html", companies=companies, data=data,
        last_updated=data.get("_last_updated", "Не загружено"), fields=KASKO_FIELDS, field_labels=FIELD_LABELS)


@app.route("/compare", methods=["GET", "POST"])
def compare():
    company1, company2 = request.values.get("company1"), request.values.get("company2")
    data = load_data()
    companies = [c.get("name") for c in data.get("_structured", {}).get("companies", []) if c.get("name")]
    if not company1 or company1 not in companies or not company2 or company2 not in companies or company1 == company2:
        return redirect("/")
    def prepare(company):
        raw, result = data.get(company, {}), {}
        for key in KASKO_FIELDS:
            item = raw.get(key, {})
            result[key] = item.get("value", "Не найдено") if isinstance(item, dict) else "Не найдено"
            result[key + "_source_level"] = item.get("source_level", 4) if isinstance(item, dict) else 4
            result[key + "_url"] = item.get("url") if isinstance(item, dict) else None
            result[key + "_review_note"] = item.get("review_note") if isinstance(item, dict) else None
        return result
    data1, data2 = prepare(company1), prepare(company2)
    comparison_by_field = {key: compare_field(data, company1, company2, key) for key in KASKO_FIELDS}
    sales = build_sales_summary(data, company1, company2, comparison_by_field)
    found1 = sum(data1.get(k) not in ("", None, "Не найдено") for k in KASKO_FIELDS)
    found2 = sum(data2.get(k) not in ("", None, "Не найдено") for k in KASKO_FIELDS)
    return render_template("result.html", company1=company1, company2=company2, data1=data1, data2=data2,
        fields=KASKO_FIELDS, field_labels=FIELD_LABELS, last_updated=data.get("_last_updated", "Не загружено"),
        comparison_by_field=comparison_by_field, comparison_ready=bool(sales["cards"]), sales=sales,
        found1=found1, found2=found2)


@app.route("/data-report")
def data_report():
    data, report_companies = load_data(), []
    master = data.get("_structured", {})
    total_found = total_confirmed = total_conditional = total_review = 0
    total_possible = len(master.get("companies", [])) * len(KASKO_FIELDS)
    for company in master.get("companies", []):
        fields, counts = [], {"confirmed": 0, "conditional": 0, "review": 0, "missing": 0}
        for f in company.get("fields", []):
            answer = (f.get("direct_answer") or "").strip()
            full = f.get("key_conditions") or answer
            limitation = f.get("limitations") or ""
            status = " ".join(str(f.get(k, "")) for k in ("audit_status", "source_review_status", "source_quote_check"))
            conditional = any(w in (answer + " " + limitation).casefold() for w in ("по договор", "если включ", "при услов", "дополнительн", "зависит"))
            confirmed = "полностью подтверждено" in status.casefold() or "без оговорок" in status.casefold()
            missing = not answer or answer == "Не найдено"
            if missing: counts["missing"] += 1
            elif confirmed: counts["confirmed"] += 1
            elif conditional: counts["conditional"] += 1
            else: counts["review"] += 1
            pages = f.get("text_search_pages") or []
            quote = f.get("evidence_quote") or ""
            fields.append({"label": f.get("parameter", f.get("key", "")), "raw_found": bool(answer), "value": full,
                "evidence_items": ([{"page": ", ".join(str(p) for p in pages), "section": f.get("source_clause_refs", ""), "quote": quote}] if quote or pages else []),
                "analysis_status": "available" if answer else "missing", "analysis_answer": answer,
                "analysis_explanation": limitation, "analysis_missing": "" if answer else "Ответ отсутствует в наборе данных.",
                "analysis_validation": status, "analysis_source_url": f.get("source_url") or company.get("source_url", ""),
                "source_level": 1 if company.get("source_url") else 4,
                "source_label": "Официальный PDF" if company.get("source_url") else "Источник требует уточнения",
                "page_number": ", ".join(str(p) for p in pages), "source_url": f.get("source_url") or company.get("source_url", ""),
                "quality_status": "confirmed" if confirmed else ("conditional" if conditional else "review"),
                "quality_label": "Подтверждено" if confirmed else ("Зависит от договора" if conditional else "Перепроверить"),
                "quality_reason": status + ((" " + limitation) if limitation else ""),
                "checked_at": master.get("created_date", ""), "quarantined": False})
        found = sum(bool(f["raw_found"]) for f in fields)
        total_found += found
        total_confirmed += counts["confirmed"]; total_conditional += counts["conditional"]; total_review += counts["review"]
        report_companies.append({"name": company.get("name", ""), "found_count": found, "missing_count": counts["missing"],
            "confirmed_count": counts["confirmed"], "conditional_count": counts["conditional"], "review_count": counts["review"],
            "contextual_answer_count": 0, "official_pdf_count": len(fields), "official_count": 0, "web_count": 0,
            "fallback_count": 0, "quarantined_count": 0, "last_checked": master.get("created_date", ""),
            "latest_run": None, "fields": fields})
    report = {"total_found": total_found, "total_possible": total_possible,
        "coverage_percent": round(100 * total_found / total_possible) if total_possible else 0,
        "total_confirmed": total_confirmed, "total_conditional": total_conditional,
        "total_contextual_answers": 0, "total_review": total_review, "companies": report_companies}
    return render_template("data_report.html", report=report)


@app.route("/update")
def update():
    return "Автоматический сбор отключён: сайт использует эталонный JSON. Обновите JSON после проверки изменений официальных документов.", 200


# ============================================================
# ЗАПУСК
# ============================================================

def startup_update_worker():
    global INSURANCE_DATA
    logger.info("🔄 Автоматический сбор данных при старте...")
    try:
        new_data = collect_all_data()
        if isinstance(new_data, dict):
            logger.info("✅ Автоматический сбор завершён")
    except Exception as exc:
        logger.exception("🔥 Ошибка автоматического обновления: %s", exc)


def start_startup_update():
    if not UPDATE_ON_START:
        return
    logger.info("🚀 Планируем автоматическое обновление...")
    thread = threading.Thread(target=startup_update_worker, name="startup-update", daemon=True)
    thread.start()


start_startup_update()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
