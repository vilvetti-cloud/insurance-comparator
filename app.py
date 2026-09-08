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

DATA_FILE = "insurance_data.json"

# Автоматический сбор при запуске
UPDATE_ON_START = True

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
    "Ренессанс": {
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
    "РГС": {
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
    "fire",
    "terrorism",
    "drone",
    "tow_truck",
    "repair_type",
    "payment_terms"
]

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
    "payment_terms": "Срок выплат"
}

FIELD_SEARCH_QUERIES = {
    "franchise": "Какая франшиза у КАСКО {company}",
    "without_certificates": "Выплата без справок по КАСКО {company}",
    "gap": "GAP страхование КАСКО {company}",
    "total_loss": "Порог тотала КАСКО {company}",
    "fire": "Самовозгорание КАСКО {company}",
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
    "fire": "Покрывается ли самовозгорание / пожар? Если нет — 'Не найдено'.",
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
    try:
        with open(DATA_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(DATA_FILE + ".tmp", DATA_FILE)
        return True
    except Exception as exc:
        logger.exception("❌ Ошибка сохранения: %s", exc)
        return False


def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        logger.info("ℹ️ Файл данных отсутствует")
        return {}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.exception("❌ Ошибка загрузки: %s", exc)
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

@app.route("/")
def index():
    data = load_data()
    companies = list(COMPANY_SOURCES.keys())
    return render_template(
        "index.html",
        companies=companies,
        data=data,
        last_updated=data.get("_last_updated", "Не обновлялось"),
        fields=KASKO_FIELDS,
        field_labels=FIELD_LABELS
    )


@app.route("/compare", methods=["GET", "POST"])
def compare():
    c1 = request.values.get("company1")
    c2 = request.values.get("company2")
    companies = list(COMPANY_SOURCES.keys())

    if not c1 or c1 not in companies or not c2 or c2 not in companies or c1 == c2:
        return redirect("/")

    data = load_data()

    def prepare_company_data(company):
        raw = data.get(company, {})
        result = {}
        for field in KASKO_FIELDS:
            field_data = raw.get(field, {})
            if isinstance(field_data, dict):
                result[field] = field_data.get("value", "Не найдено")
                result[f"{field}_source"] = field_data.get("source", "none")
                result[f"{field}_url"] = field_data.get("url")
            else:
                result[field] = "Не найдено"
                result[f"{field}_source"] = "none"
                result[f"{field}_url"] = None
        return result

    data1 = prepare_company_data(c1)
    data2 = prepare_company_data(c2)

    return render_template(
        "result.html",
        company1=c1,
        company2=c2,
        data1=data1,
        data2=data2,
        fields=KASKO_FIELDS,
        field_labels=FIELD_LABELS,
        last_updated=data.get("_last_updated", "Не обновлялось")
    )


@app.route("/update")
def update():
    global UPDATE_RUNNING
    if UPDATE_RUNNING:
        return "⏳ Обновление уже выполняется. Попробуйте позже."

    import threading
    threading.Thread(target=lambda: collect_all_data()).start()
    return "🔄 Обновление запущено! Страница обновится через несколько минут."


# ============================================================
# ШАБЛОНЫ
# ============================================================

os.makedirs("templates", exist_ok=True)

with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write('''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Сравнение КАСКО</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #f0f2f5; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .container { background: #fff; padding: 40px; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); max-width: 520px; width: 100%; }
        h1 { font-size: 24px; color: #1a1a2e; text-align: center; margin-bottom: 8px; }
        .subtitle { text-align: center; color: #6b7280; font-size: 14px; margin-bottom: 30px; }
        .update-info { text-align: center; font-size: 12px; color: #9ca3af; margin-bottom: 24px; padding: 8px; background: #f9fafb; border-radius: 8px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; font-weight: 600; font-size: 14px; color: #374151; margin-bottom: 6px; }
        select { width: 100%; padding: 12px 14px; border: 1.5px solid #e5e7eb; border-radius: 10px; font-size: 15px; background: #fff; transition: border-color 0.2s; appearance: none; }
        select:focus { outline: none; border-color: #2563eb; }
        .vs { text-align: center; font-size: 20px; color: #9ca3af; margin: 8px 0; }
        .btn { width: 100%; padding: 14px; background: #2563eb; color: #fff; border: none; border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer; transition: background 0.2s; margin-top: 8px; }
        .btn:hover { background: #1d4ed8; }
        .btn-update { background: #6b7280; margin-top: 12px; }
        .btn-update:hover { background: #4b5563; }
        .footer { margin-top: 24px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #f3f4f6; padding-top: 16px; }
        .badge { display: inline-block; font-size: 11px; padding: 2px 10px; border-radius: 12px; background: #e5e7eb; color: #4b5563; margin-top: 8px; }
    </style>
</head>
<body>
<div class="container">
    <h1>🚗 Сравнение КАСКО</h1>
    <p class="subtitle">Выберите две компании для сравнения</p>
    <div class="update-info">📅 Данные обновлены: {{ last_updated }}</div>
    
    <form action="/compare" method="POST">
        <div class="form-group">
            <label>🏢 Первая компания</label>
            <select name="company1" required>
                <option value="">— Выберите —</option>
                {% for c in companies %}
                <option value="{{ c }}">{{ c }}</option>
                {% endfor %}
            </select>
        </div>
        
        <div class="vs">⚔️</div>
        
        <div class="form-group">
            <label>🏢 Вторая компания</label>
            <select name="company2" required>
                <option value="">— Выберите —</option>
                {% for c in companies %}
                <option value="{{ c }}">{{ c }}</option>
                {% endfor %}
            </select>
        </div>
        
        <button type="submit" class="btn">📊 Сравнить</button>
    </form>
    
    <a href="/update"><button class="btn btn-update">🔄 Обновить данные сейчас</button></a>
    
    <div class="footer">
        <span class="badge">11 компаний</span>
        <span class="badge">10 параметров</span>
        <span class="badge">🤖 Groq + Интернет</span>
    </div>
</div>
</body>
</html>
''')


with open("templates/result.html", "w", encoding="utf-8") as f:
    f.write('''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Сравнение КАСКО</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #f0f2f5; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }
        h1 { font-size: 22px; color: #1a1a2e; text-align: center; margin-bottom: 6px; }
        .subtitle { text-align: center; color: #6b7280; font-size: 14px; margin-bottom: 24px; }
        .vs-title { text-align: center; font-size: 16px; padding: 12px; background: #f8fafc; border-radius: 10px; margin-bottom: 24px; }
        .main-badge { background: #2563eb; color: #fff; padding: 2px 14px; border-radius: 12px; font-size: 12px; margin-left: 8px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { background: #1a1a2e; color: #fff; padding: 10px 12px; text-align: left; }
        td { padding: 10px 12px; border-bottom: 1px solid #f0f2f5; vertical-align: top; }
        .param { font-weight: 600; color: #374151; background: #f8fafc; width: 16%; }
        .value { word-break: break-word; }
        .source-icon { font-size: 14px; margin-right: 4px; }
        .legend { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0 16px; padding: 14px; background: #f8fafc; border-radius: 10px; font-size: 13px; }
        .legend-item { display: flex; align-items: center; gap: 4px; }
        .btn { display: inline-block; padding: 10px 24px; background: #2563eb; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px; transition: background 0.2s; }
        .btn:hover { background: #1d4ed8; }
        .btn-secondary { background: #6b7280; }
        .btn-secondary:hover { background: #4b5563; }
        .actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
        .footer { margin-top: 20px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #f3f4f6; padding-top: 16px; }
        .not-found { color: #e74c3c; font-style: italic; }
        .source-url { font-size: 11px; color: #6b7280; word-break: break-all; }
        .source-url a { color: #2563eb; text-decoration: none; }
        .source-url a:hover { text-decoration: underline; }
        @media (max-width: 768px) {
            .container { padding: 16px; }
            table { font-size: 12px; }
            td, th { padding: 6px 8px; }
            .param { width: 20%; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>📊 Сравнение КАСКО</h1>
    <div class="subtitle">Сравнительный анализ условий страхования</div>
    
    <div class="vs-title">
        🏆 {{ company1 }} <span class="main-badge">ОСНОВНАЯ</span>
        &nbsp;⚔️&nbsp; {{ company2 }}
    </div>
    
    <div class="legend">
        <span class="legend-item">📄 PDF правила</span>
        <span class="legend-item">🌐 Интернет-поиск</span>
        <span class="legend-item">❌ Не найдено</span>
    </div>
    
    <table>
        <thead>
            <tr>
                <th class="param">Параметр</th>
                <th>{{ company1 }}</th>
                <th>{{ company2 }}</th>
            </tr>
        </thead>
        <tbody>
            {% for field in fields %}
            <tr>
                <td class="param">{{ field_labels.get(field, field) }}</td>
                <td class="value">
                    {% set val = data1.get(field, 'Не найдено') %}
                    {% set src = data1.get(field + '_source', 'none') %}
                    {% set url = data1.get(field + '_url') %}
                    {% if val == 'Не найдено' or not val %}
                        <span class="not-found">Не найдено</span>
                    {% else %}
                        {% if src == 'pdf' %}📄{% elif src == 'internet' %}🌐{% else %}❌{% endif %}
                        {{ val }}
                        {% if url %}
                            <div class="source-url"><a href="{{ url }}" target="_blank">🔗 источник</a></div>
                        {% endif %}
                    {% endif %}
                </td>
                <td class="value">
                    {% set val = data2.get(field, 'Не найдено') %}
                    {% set src = data2.get(field + '_source', 'none') %}
                    {% set url = data2.get(field + '_url') %}
                    {% if val == 'Не найдено' or not val %}
                        <span class="not-found">Не найдено</span>
                    {% else %}
                        {% if src == 'pdf' %}📄{% elif src == 'internet' %}🌐{% else %}❌{% endif %}
                        {{ val }}
                        {% if url %}
                            <div class="source-url"><a href="{{ url }}" target="_blank">🔗 источник</a></div>
                        {% endif %}
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    
    <div class="actions">
        <a href="/" class="btn">← Новое сравнение</a>
        <a href="/update" class="btn btn-secondary">🔄 Обновить данные</a>
    </div>
    
    <div class="footer">
        Обновлено: {{ last_updated }}
    </div>
</div>
</body>
</html>
''')


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
