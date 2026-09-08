from flask import Flask, render_template, request, redirect
from datetime import datetime
import json
import os
import requests
import urllib3
import re
import time
import random
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
import logging

# ============================================================
# НАСТРОЙКИ
# ============================================================

app = Flask(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# Groq
# ------------------------------------------------------------

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Основная модель + запасная
GROQ_MODELS = [
    os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
    "openai/gpt-oss-20b"
]

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Сколько раз пробуем один запрос к конкретной модели
GROQ_RETRIES = 3

# Таймаут HTTP-запроса к Groq
GROQ_TIMEOUT = 90

# ------------------------------------------------------------
# Файл данных
# ------------------------------------------------------------

DATA_FILE = "insurance_data.json"


# ============================================================
# USER AGENTS
# ============================================================

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) "
        "Gecko/20100101 Firefox/142.0"
    )
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
        "url": (
            "https://www.soglasie.ru/individuals/avto/kasko/"
            "pravila-strakhovaniya-transportnykh-sredstv/"
        ),
        "type": "direct"
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
        "type": "direct"
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


# ============================================================
# ПРОМПТЫ ДЛЯ АНАЛИЗА
# ============================================================

FIELD_ANALYSIS_PROMPTS = {

    "franchise": """
Определи условия франшизы по КАСКО.

Нужно установить:
- есть ли франшиза;
- какие размеры франшизы предусмотрены;
- зависит ли размер от условий договора;
- является ли франшиза обязательной или опциональной.

Не придумывай значения.
Если информации недостаточно, напиши "Не найдено".
""",

    "without_certificates": """
Определи, можно ли получить страховое возмещение по КАСКО
без предоставления справок из полиции / ГИБДД / МВД.

Укажи:
- допускается ли обращение без справок;
- в каких случаях;
- какие есть ограничения;
- количество таких обращений, если оно указано;
- лимиты ущерба, если они указаны.

Не путай отсутствие справок с отсутствием документов вообще.
""",

    "gap": """
Определи наличие GAP-страхования.

Укажи:
- есть ли GAP;
- что именно покрывает;
- является ли отдельной опцией;
- для каких автомобилей доступно;
- есть ли возрастные или иные ограничения;
- какие выплаты предусмотрены.

Не делай предположений.
""",

    "total_loss": """
Определи условия полной гибели автомобиля / конструктивной гибели
(тотала).

Укажи:
- какой процент стоимости автомобиля используется как порог;
- как определяется тотальная гибель;
- какие выплаты производятся;
- учитывается ли стоимость годных остатков;
- другие существенные условия.

Если конкретного процента нет, не придумывай его.
""",

    "fire": """
Определи, покрывает ли КАСКО пожар.

Проверь:
- пожар;
- возгорание;
- самовозгорание;
- короткое замыкание;
- другие связанные случаи.

Укажи ограничения и исключения, если они есть.
""",

    "terrorism": """
Определи, покрываются ли ущерб или гибель автомобиля
в результате террористического акта.

Укажи:
- покрытие;
- условия;
- ограничения;
- исключения;
- требуется ли отдельное включение риска.

Не делай предположений.
""",

    "drone": """
Определи, покрываются ли повреждения автомобиля,
возникшие в результате БПЛА / дронов.

Укажи:
- есть ли такое покрытие;
- распространяется ли на падение дрона;
- на обломки;
- на взрыв / воздействие;
- есть ли ограничения и исключения;
- является ли риск стандартным или дополнительным.

Если прямого упоминания нет, напиши "Не найдено".
""",

    "tow_truck": """
Определи условия предоставления эвакуатора.

Укажи:
- предоставляется ли эвакуатор;
- в каких случаях;
- есть ли ограничение по количеству;
- есть ли ограничение по стоимости;
- входит ли услуга в КАСКО;
- является ли дополнительной услугой;
- распространяется ли на легковой автомобиль.

Не путай эвакуатор с технической помощью на дороге.
""",

    "repair_type": """
Определи варианты ремонта автомобиля.

Проверь:
- ремонт у официального дилера;
- ремонт на СТОА;
- направление страховщика;
- денежную выплату;
- возможность выбора СТО;
- ограничения по возрасту автомобиля;
- другие существенные условия.

Не смешивай ремонт и денежную выплату.
""",

    "payment_terms": """
Определи сроки урегулирования и выплаты.

Укажи:
- срок рассмотрения заявления;
- срок принятия решения;
- срок страховой выплаты;
- общий срок, если он указан;
- отдельно отметь сроки ремонта, если они есть, но НЕ называй их сроком денежной выплаты.

Не путай срок ремонта автомобиля со сроком страховой выплаты.
"""
}


# ============================================================
# HTTP
# ============================================================

def get_headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,application/pdf;q=0.8,*/*;q=0.7"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def fetch_url(
    url: str,
    retries: int = 3,
    timeout: int = 30
) -> Optional[Dict[str, Any]]:

    last_error = None

    for attempt in range(1, retries + 1):

        try:
            logger.info(
                "🌐 Запрос: %s (попытка %s/%s)",
                url,
                attempt,
                retries
            )

            response = requests.get(
                url,
                headers=get_headers(),
                timeout=timeout,
                verify=False,
                allow_redirects=True
            )

            status = response.status_code

            logger.info(
                "📡 HTTP %s: %s",
                status,
                url
            )

            if status == 200:

                content_type = (
                    response.headers.get("Content-Type", "")
                    .lower()
                )

                return {
                    "success": True,
                    "status": status,
                    "content": response.content,
                    "text": response.text,
                    "url": response.url,
                    "content_type": content_type
                }

            if status in [401, 403, 429, 500, 502, 503, 504]:

                logger.warning(
                    "⚠️ HTTP %s для %s",
                    status,
                    url
                )

                if attempt < retries:

                    if status == 429:
                        wait_time = 5 * attempt
                    elif status in [500, 502, 503, 504]:
                        wait_time = 3 * attempt
                    else:
                        wait_time = 2 * attempt

                    wait_time += random.uniform(0.5, 1.5)

                    logger.info(
                        "⏳ Ждём %.1f сек.",
                        wait_time
                    )

                    time.sleep(wait_time)

                continue

            logger.error(
                "❌ Неожиданный HTTP %s для %s",
                status,
                url
            )

            return {
                "success": False,
                "status": status,
                "content": response.content,
                "text": response.text,
                "url": response.url,
                "content_type": response.headers.get(
                    "Content-Type",
                    ""
                )
            }

        except requests.exceptions.Timeout as exc:

            last_error = exc

            logger.warning(
                "⏱️ Timeout: %s",
                url
            )

        except requests.exceptions.RequestException as exc:

            last_error = exc

            logger.warning(
                "⚠️ Ошибка запроса %s: %s",
                url,
                exc
            )

        except Exception as exc:

            last_error = exc

            logger.exception(
                "❌ Неожиданная ошибка fetch_url: %s",
                exc
            )

        if attempt < retries:
            time.sleep(2 * attempt)

    logger.error(
        "❌ Не удалось получить URL: %s | %s",
        url,
        last_error
    )

    return None


# ============================================================
# PDF
# ============================================================

def find_pdf_links(
    html: str,
    base_url: str
) -> List[str]:

    links = []

    try:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all("a", href=True):

            href = tag.get("href", "").strip()

            if not href:
                continue

            full_url = href

            if not href.startswith(("http://", "https://")):
                from urllib.parse import urljoin
                full_url = urljoin(base_url, href)

            href_lower = href.lower()
            text_lower = tag.get_text(
                " ",
                strip=True
            ).lower()

            is_pdf = (
                ".pdf" in href_lower
                or ".pdf" in text_lower
                or "правил" in text_lower
                or "правила" in text_lower
                or "условия страхования" in text_lower
                or "документ" in text_lower
                or "документы" in text_lower
                or "download" in href_lower
                or "document" in href_lower
            )

            if is_pdf:
                if full_url not in links:
                    links.append(full_url)

    except Exception as exc:

        logger.exception(
            "❌ Ошибка поиска PDF: %s",
            exc
        )

    return links


def extract_text_from_pdf(
    content: bytes
) -> str:

    try:
        import PyPDF2

        reader = PyPDF2.PdfReader(
            io.BytesIO(content)
        )

        pages = []

        for index, page in enumerate(reader.pages):

            try:
                text = page.extract_text() or ""

                if text.strip():
                    pages.append(text)

            except Exception as exc:

                logger.warning(
                    "⚠️ Ошибка чтения страницы PDF %s: %s",
                    index + 1,
                    exc
                )

        result = clean_text(
            "\n\n".join(pages)
        )

        logger.info(
            "📄 PDF: страниц=%s, символов=%s",
            len(reader.pages),
            len(result)
        )

        return result

    except Exception as exc:

        logger.exception(
            "❌ Ошибка извлечения PDF: %s",
            exc
        )

        return ""


# ============================================================
# ВЫДЕЛЕНИЕ РЕЛЕВАНТНЫХ ФРАГМЕНТОВ
# ============================================================

def extract_relevant_sections(
    text: str,
    max_chars: int = 100000
) -> str:

    text = clean_text(text)

    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    logger.info(
        "📚 Документ большой: %s символов. "
        "Ищем релевантные разделы.",
        len(text)
    )

    keywords = [
        "франшиз",
        "справк",
        "GAP",
        "gap",
        "полной гибел",
        "тотал",
        "пожар",
        "возгора",
        "самовозгора",
        "террор",
        "террорист",
        "дрон",
        "бпла",
        "беспилот",
        "эвакуатор",
        "эвакуац",
        "ремонт",
        "СТОА",
        "дилер",
        "выплат",
        "урегулирован"
    ]

    lines = text.splitlines()

    chunks = []

    window_before = 8
    window_after = 18

    for index, line in enumerate(lines):

        line_lower = line.lower()

        if not any(
            keyword.lower() in line_lower
            for keyword in keywords
        ):
            continue

        start = max(
            0,
            index - window_before
        )

        end = min(
            len(lines),
            index + window_after + 1
        )

        chunk = "\n".join(
            lines[start:end]
        )

        chunks.append(chunk)

    # Удаляем дубликаты
    unique_chunks = []
    seen = set()

    for chunk in chunks:

        normalized = re.sub(
            r"\s+",
            " ",
            chunk
        ).strip()

        if not normalized:
            continue

        key = normalized[:500]

        if key not in seen:
            seen.add(key)
            unique_chunks.append(chunk)

    result = clean_text(
        "\n\n--- РЕЛЕВАНТНЫЙ ФРАГМЕНТ ---\n\n".join(
            unique_chunks
        )
    )

    if not result:
        result = text[:max_chars]

    return result[:max_chars]


# ============================================================
# GROQ
# ============================================================

def normalize_llm_result(
    data: Any
) -> Dict[str, str]:

    if not isinstance(data, dict):
        data = {}

    result = {}

    for field in KASKO_FIELDS:

        value = data.get(field)

        if value is None:
            value = "Не найдено"

        if isinstance(value, (dict, list)):
            try:
                value = json.dumps(
                    value,
                    ensure_ascii=False
                )
            except Exception:
                value = str(value)

        value = str(value).strip()

        if not value:
            value = "Не найдено"

        result[field] = value

    return result


def try_parse_json(
    content: str
) -> Dict[str, Any]:

    if not content:
        return {}

    content = content.strip()

    # Обычный JSON
    try:
        data = json.loads(content)

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    # JSON внутри ```json ... ```
    match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        content,
        re.DOTALL | re.IGNORECASE
    )

    if match:

        try:
            data = json.loads(
                match.group(1)
            )

            if isinstance(data, dict):
                return data

        except Exception:
            pass

    # Попытка найти первый объект JSON
    start = content.find("{")
    end = content.rfind("}")

    if start >= 0 and end > start:

        candidate = content[start:end + 1]

        try:
            data = json.loads(candidate)

            if isinstance(data, dict):
                return data

        except Exception:
            pass

    return {}


def analyze_company_with_groq(
    text: str,
    company: str,
    source_type: str = "PDF"
) -> Dict[str, str]:

    if not GROQ_API_KEY:

        logger.error(
            "❌ GROQ_API_KEY не задан"
        )

        return {}

    if not text:

        logger.warning(
            "⚠️ Нет текста для анализа: %s",
            company
        )

        return {}

    relevant_text = extract_relevant_sections(
        text
    )

    fields_description = "\n\n".join(
        [
            f"{field}: {FIELD_ANALYSIS_PROMPTS[field]}"
            for field in KASKO_FIELDS
        ]
    )

    system_prompt = f"""
Ты — эксперт по анализу условий КАСКО российских страховых компаний.

Твоя задача — извлечь факты ТОЛЬКО из предоставленного документа.

СТРОГИЕ ПРАВИЛА:

1. Не используй свои знания о страховой компании.
2. Не используй интернет.
3. Не додумывай отсутствующую информацию.
4. Если информация не найдена — пиши "Не найдено".
5. Не подменяй конкретные условия общими рассуждениями.
6. Если указано несколько вариантов — перечисли их.
7. Сохраняй важные ограничения, проценты, лимиты и условия.
8. Ответ должен быть ТОЛЬКО валидным JSON.
9. Все значения должны быть строками.
10. Не добавляй никакие поля кроме перечисленных.

СТРАХОВАЯ КОМПАНИЯ:
{company}

ТИП ИСТОЧНИКА:
{source_type}

ПОЛЯ:

{fields_description}
"""

    user_prompt = f"""
Проанализируй следующий текст документа страховой компании.

Верни строго JSON следующего вида:

{{
  "franchise": "...",
  "without_certificates": "...",
  "gap": "...",
  "total_loss": "...",
  "fire": "...",
  "terrorism": "...",
  "drone": "...",
  "tow_truck": "...",
  "repair_type": "...",
  "payment_terms": "..."
}}

Если информации по конкретному полю нет,
используй значение "Не найдено".

ТЕКСТ ДОКУМЕНТА:

{relevant_text}
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # Убираем дубликаты моделей
    models = []

    for model in GROQ_MODELS:

        if model and model not in models:
            models.append(model)

    if not models:
        models = ["openai/gpt-oss-120b"]

    # --------------------------------------------------------
    # Пробуем модели по очереди
    # --------------------------------------------------------

    for model in models:

        logger.info(
            "🤖 Groq: %s | компания: %s",
            model,
            company
        )

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2500,
            "response_format": {
                "type": "json_object"
            }
        }

        for attempt in range(
            1,
            GROQ_RETRIES + 1
        ):

            try:

                response = requests.post(
                    GROQ_URL,
                    headers=headers,
                    json=payload,
                    timeout=GROQ_TIMEOUT
                )

                status = response.status_code

                logger.info(
                    "🤖 Groq HTTP %s | %s | попытка %s/%s",
                    status,
                    company,
                    attempt,
                    GROQ_RETRIES
                )

                # ------------------------------------------------
                # УСПЕХ
                # ------------------------------------------------

                if status == 200:

                    try:

                        response_json = response.json()

                        choices = response_json.get(
                            "choices",
                            []
                        )

                        if not choices:

                            logger.error(
                                "❌ Groq не вернул choices: %s",
                                response_json
                            )

                            continue

                        content = (
                            choices[0]
                            .get("message", {})
                            .get("content", "")
                        )

                        parsed = try_parse_json(
                            content
                        )

                        if parsed:

                            result = normalize_llm_result(
                                parsed
                            )

                            logger.info(
                                "✅ Groq успешно обработал: %s",
                                company
                            )

                            return result

                        logger.error(
                            "❌ Groq вернул невалидный JSON: %s",
                            content[:1000]
                        )

                    except Exception as exc:

                        logger.exception(
                            "❌ Ошибка разбора ответа Groq: %s",
                            exc
                        )

                    continue

                # ------------------------------------------------
                # 400 — проблема запроса / модели
                # ------------------------------------------------

                if status == 400:

                    try:
                        error_json = response.json()
                    except Exception:
                        error_json = response.text[:1000]

                    logger.error(
                        "❌ Groq 400 | модель=%s | %s",
                        model,
                        error_json
                    )

                    # Нет смысла трижды повторять
                    # заведомо плохой запрос.
                    break

                # ------------------------------------------------
                # 401 / 403 — API KEY
                # ------------------------------------------------

                if status in [401, 403]:

                    logger.error(
                        "❌ Groq авторизация не прошла: HTTP %s",
                        status
                    )

                    # Это не проблема конкретной страховой.
                    # Нет смысла продолжать запросы.
                    return {}

                # ------------------------------------------------
                # 429 — лимит
                # ------------------------------------------------

                if status == 429:

                    if attempt < GROQ_RETRIES:

                        wait_time = (
                            10 * attempt
                        )

                        logger.warning(
                            "⏳ Groq rate limit. Ждём %s сек.",
                            wait_time
                        )

                        time.sleep(wait_time)

                        continue

                    logger.warning(
                        "⚠️ Groq rate limit после всех попыток: %s",
                        company
                    )

                    break

                # ------------------------------------------------
                # 5xx — временная ошибка
                # ------------------------------------------------

                if status in [
                    500,
                    502,
                    503,
                    504
                ]:

                    if attempt < GROQ_RETRIES:

                        wait_time = (
                            5 * attempt
                        )

                        logger.warning(
                            "⏳ Groq серверная ошибка. "
                            "Ждём %s сек.",
                            wait_time
                        )

                        time.sleep(wait_time)

                        continue

                    break

                # ------------------------------------------------
                # Другой HTTP
                # ------------------------------------------------

                logger.error(
                    "❌ Groq неожиданный HTTP %s: %s",
                    status,
                    response.text[:1000]
                )

                break

            except requests.exceptions.Timeout:

                logger.warning(
                    "⏱️ Таймаут Groq: %s",
                    company
                )

                if attempt < GROQ_RETRIES:

                    time.sleep(
                        5 * attempt
                    )

            except requests.exceptions.RequestException as exc:

                logger.warning(
                    "⚠️ Ошибка запроса Groq: %s",
                    exc
                )

                if attempt < GROQ_RETRIES:

                    time.sleep(
                        5 * attempt
                    )

            except Exception as exc:

                logger.exception(
                    "❌ Неожиданная ошибка Groq: %s",
                    exc
                )

                break

        # --------------------------------------------------------
        # Если модель не справилась — пробуем следующую
        # --------------------------------------------------------

        logger.warning(
            "⚠️ Модель %s не обработала компанию %s. "
            "Пробуем следующую модель.",
            model,
            company
        )

    logger.error(
        "❌ Все модели Groq не смогли обработать: %s",
        company
    )

    return {}


# ============================================================
# HTML
# ============================================================

def parse_html_page(
    html: str
) -> str:

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        for tag in soup([
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
            "svg"
        ]):
            tag.decompose()

        text = soup.get_text(
            "\n",
            strip=True
        )

        return clean_text(text)

    except Exception as exc:

        logger.exception(
            "❌ Ошибка парсинга HTML: %s",
            exc
        )

        return ""


# ============================================================
# ИНФОРМАЦИЯ ОБ ИСТОЧНИКЕ
# ============================================================

def get_source_info(
    level: int
) -> Dict[str, str]:

    return {
        0: {
            "name": "Не найдено",
            "icon": "❌"
        },
        1: {
            "name": "Правила страхования",
            "icon": "📄"
        },
        2: {
            "name": "Groq-LLM",
            "icon": "🤖"
        },
        3: {
            "name": "Сайт страховой",
            "icon": "🌐"
        }
    }.get(
        level,
        {
            "name": "Неизвестный источник",
            "icon": "❓"
        }
    )


def make_field_result(
    value: Any,
    source_level: int,
    source_url: Optional[str] = None
) -> Dict[str, Any]:

    if value is None:
        value = "Не найдено"

    value = str(value).strip()

    if not value:
        value = "Не найдено"

    return {
        "value": value,
        "source": source_level,
        "url": source_url
    }


# ============================================================
# СБОР ДАННЫХ ОДНОЙ СТРАХОВОЙ
# ============================================================

def collect_company_data(
    company: str
) -> Dict[str, Any]:

    logger.info("")
    logger.info("=" * 70)
    logger.info(
        "🏢 НАЧИНАЕМ: %s",
        company
    )
    logger.info("=" * 70)

    source = COMPANY_SOURCES.get(company)

    if not source:

        logger.error(
            "❌ Источник не найден: %s",
            company
        )

        return {
            field: make_field_result(
                "Не найдено",
                0
            )
            for field in KASKO_FIELDS
        }

    source_url = source.get(
        "url"
    )

    # --------------------------------------------------------
    # Скачиваем основной источник
    # --------------------------------------------------------

    response = fetch_url(
        source_url
    )

    if not response:

        logger.error(
            "❌ Не удалось получить источник: %s",
            company
        )

        return {
            field: make_field_result(
                "Не найдено",
                0,
                source_url
            )
            for field in KASKO_FIELDS
        }

    if not response.get("success"):

        logger.error(
            "❌ Источник вернул ошибку: %s | HTTP %s",
            company,
            response.get("status")
        )

        return {
            field: make_field_result(
                "Не найдено",
                0,
                source_url
            )
            for field in KASKO_FIELDS
        }

    content = response.get(
        "content",
        b""
    )

    html = response.get(
        "text",
        ""
    )

    content_type = response.get(
        "content_type",
        ""
    ).lower()

    final_data = {}

    # --------------------------------------------------------
    # 1. Проверяем, не PDF ли это
    # --------------------------------------------------------

    is_pdf = (
        "application/pdf" in content_type
        or source_url.lower().endswith(".pdf")
        or content[:4] == b"%PDF"
    )

    if is_pdf:

        logger.info(
            "📄 Получен PDF напрямую: %s",
            company
        )

        pdf_text = extract_text_from_pdf(
            content
        )

        if pdf_text:

            llm_data = analyze_company_with_groq(
                pdf_text,
                company,
                "PDF / Правила страхования"
            )

            for field in KASKO_FIELDS:

                value = llm_data.get(
                    field,
                    "Не найдено"
                )

                final_data[field] = make_field_result(
                    value,
                    2,
                    source_url
                )

            if llm_data:

                logger.info(
                    "✅ Данные получены из PDF: %s",
                    company
                )

                return final_data

            logger.warning(
                "⚠️ Groq не смог обработать PDF: %s",
                company
            )

    # --------------------------------------------------------
    # 2. Если это HTML — ищем PDF с правилами
    # --------------------------------------------------------

    if html:

        logger.info(
            "🌐 Анализируем HTML: %s",
            company
        )

        pdf_links = find_pdf_links(
            html,
            response.get(
                "url",
                source_url
            )
        )

        logger.info(
            "📚 Найдено потенциальных PDF/документов: %s",
            len(pdf_links)
        )

        # Ограничиваем количество попыток
        # чтобы одна компания не могла зависнуть
        # на десятках документов.
        for pdf_url in pdf_links[:5]:

            try:

                logger.info(
                    "📥 Пробуем PDF: %s",
                    pdf_url
                )

                pdf_response = fetch_url(
                    pdf_url,
                    retries=2,
                    timeout=30
                )

                if not pdf_response:
                    continue

                if not pdf_response.get(
                    "success"
                ):
                    continue

                pdf_content = pdf_response.get(
                    "content",
                    b""
                )

                pdf_content_type = (
                    pdf_response.get(
                        "content_type",
                        ""
                    ).lower()
                )

                if not (
                    "application/pdf" in pdf_content_type
                    or pdf_content[:4] == b"%PDF"
                ):
                    continue

                pdf_text = extract_text_from_pdf(
                    pdf_content
                )

                if not pdf_text:
                    continue

                logger.info(
                    "📄 PDF извлечён: %s символов",
                    len(pdf_text)
                )

                llm_data = analyze_company_with_groq(
                    pdf_text,
                    company,
                    "PDF / Правила страхования"
                )

                if llm_data:

                    for field in KASKO_FIELDS:

                        final_data[field] = make_field_result(
                            llm_data.get(
                                field,
                                "Не найдено"
                            ),
                            2,
                            pdf_url
                        )

                    logger.info(
                        "✅ Использован PDF: %s",
                        pdf_url
                    )

                    return final_data

            except Exception as exc:

                # КЛЮЧЕВОЙ МОМЕНТ:
                # ошибка одного PDF не ломает компанию
                logger.exception(
                    "❌ Ошибка при обработке PDF %s: %s",
                    pdf_url,
                    exc
                )

                continue

    # --------------------------------------------------------
    # 3. Если PDF не сработал — анализируем HTML
    # --------------------------------------------------------

    html_text = parse_html_page(
        html
    )

    if html_text:

        logger.info(
            "🤖 Передаём HTML в Groq: %s | %s символов",
            company,
            len(html_text)
        )

        llm_data = analyze_company_with_groq(
            html_text,
            company,
            "Сайт страховой"
        )

        if llm_data:

            for field in KASKO_FIELDS:

                final_data[field] = make_field_result(
                    llm_data.get(
                        field,
                        "Не найдено"
                    ),
                    3,
                    response.get(
                        "url",
                        source_url
                    )
                )

            logger.info(
                "✅ Данные получены с сайта: %s",
                company
            )

            return final_data

    # --------------------------------------------------------
    # 4. Полный провал только этой компании
    # --------------------------------------------------------

    logger.error(
        "❌ НЕ УДАЛОСЬ СОБРАТЬ ДАННЫЕ: %s",
        company
    )

    return {
        field: make_field_result(
            "Не найдено",
            0,
            source_url
        )
        for field in KASKO_FIELDS
    }


# ============================================================
# СБОР ВСЕХ КОМПАНИЙ
# ============================================================

def collect_all_data() -> Dict[str, Any]:

    logger.info("")
    logger.info("#" * 70)
    logger.info(
        "🚀 НАЧИНАЕМ ПОЛНОЕ ОБНОВЛЕНИЕ"
    )
    logger.info("#" * 70)

    companies = list(
        COMPANY_SOURCES.keys()
    )

    result = {}

    successful = 0
    failed = 0

    # --------------------------------------------------------
    # Обрабатываем компании ПО ОДНОЙ
    # --------------------------------------------------------

    for index, company in enumerate(
        companies,
        start=1
    ):

        logger.info("")
        logger.info(
            "🏁 Компания %s из %s: %s",
            index,
            len(companies),
            company
        )

        try:

            company_data = collect_company_data(
                company
            )

            # Проверяем, что вернулся словарь
            if not isinstance(
                company_data,
                dict
            ):
                raise ValueError(
                    "collect_company_data вернул "
                    "не словарь"
                )

            result[company] = company_data

            # Проверяем наличие хотя бы одного
            # реально найденного поля
            has_data = any(
                isinstance(
                    company_data.get(field),
                    dict
                )
                and company_data[field].get(
                    "value"
                ) not in [
                    None,
                    "",
                    "Не найдено"
                ]
                for field in KASKO_FIELDS
            )

            if has_data:
                successful += 1
                logger.info(
                    "✅ Компания обработана: %s",
                    company
                )
            else:
                failed += 1
                logger.warning(
                    "⚠️ Компания обработана, "
                    "но данных не найдено: %s",
                    company
                )

        except Exception as exc:

            # =================================================
            # САМАЯ ВАЖНАЯ ЗАЩИТА
            #
            # Даже если внутри компании произойдёт
            # непредвиденная ошибка, цикл НЕ остановится.
            # =================================================

            failed += 1

            logger.exception(
                "🔥 КРИТИЧЕСКАЯ ОШИБКА КОМПАНИИ %s: %s",
                company,
                exc
            )

            result[company] = {
                field: make_field_result(
                    "Не найдено",
                    0,
                    COMPANY_SOURCES.get(
                        company,
                        {}
                    ).get(
                        "url"
                    )
                )
                for field in KASKO_FIELDS
            }

        # ----------------------------------------------------
        # СОХРАНЯЕМ ПОСЛЕ КАЖДОЙ КОМПАНИИ
        # ----------------------------------------------------

        partial_result = dict(result)

        partial_result["_last_updated"] = (
            datetime.now().strftime(
                "%d.%m.%Y %H:%M:%S"
            )
        )

        partial_result["_update_progress"] = {
            "processed": index,
            "total": len(companies),
            "successful": successful,
            "failed": failed
        }

        try:

            save_data(
                partial_result
            )

            logger.info(
                "💾 Промежуточные данные сохранены: "
                "%s/%s",
                index,
                len(companies)
            )

        except Exception as exc:

            logger.exception(
                "⚠️ Не удалось сохранить промежуточные данные: %s",
                exc
            )

        # Небольшая пауза между компаниями
        # для снижения нагрузки и вероятности rate limit.
        if index < len(companies):

            wait_time = 2 + random.uniform(
                0.5,
                1.5
            )

            logger.info(
                "⏳ Пауза %.1f сек. перед следующей компанией",
                wait_time
            )

            time.sleep(
                wait_time
            )

    # --------------------------------------------------------
    # Финальная информация
    # --------------------------------------------------------

    result["_last_updated"] = (
        datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )
    )

    result["_fields"] = KASKO_FIELDS

    result["_update_progress"] = {
        "processed": len(companies),
        "total": len(companies),
        "successful": successful,
        "failed": failed
    }

    logger.info("")
    logger.info("#" * 70)
    logger.info(
        "🏁 ОБНОВЛЕНИЕ ЗАВЕРШЕНО"
    )
    logger.info(
        "Всего компаний: %s",
        len(companies)
    )
    logger.info(
        "Успешно: %s",
        successful
    )
    logger.info(
        "Без данных: %s",
        failed
    )
    logger.info("#" * 70)

    return result


# ============================================================
# СОХРАНЕНИЕ / ЗАГРУЗКА
# ============================================================

def save_data(
    data: Dict[str, Any]
) -> bool:

    try:

        with open(
            DATA_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        return True

    except Exception as exc:

        logger.exception(
            "❌ Ошибка сохранения данных: %s",
            exc
        )

        return False


def load_data() -> Dict[str, Any]:

    if not os.path.exists(
        DATA_FILE
    ):

        logger.info(
            "ℹ️ Файл данных отсутствует: %s",
            DATA_FILE
        )

        return {}

    try:

        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            dict
        ):
            return {}

        logger.info(
            "📂 Загружены сохранённые данные"
        )

        return data

    except Exception as exc:

        logger.exception(
            "❌ Ошибка загрузки данных: %s",
            exc
        )

        return {}


# ============================================================
# ГЛОБАЛЬНЫЕ ДАННЫЕ
# ============================================================

INSURANCE_DATA = load_data()


# ============================================================
# ROUTE: ГЛАВНАЯ
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    companies = list(
        COMPANY_SOURCES.keys()
    )

    return render_template(
        "index.html",
        companies=companies,
        fields=KASKO_FIELDS,
        field_labels=FIELD_LABELS,
        data=INSURANCE_DATA,
        last_updated=INSURANCE_DATA.get(
            "_last_updated",
            "Не обновлялось"
        ),
        source_info=get_source_info
    )


# ============================================================
# ROUTE: СРАВНЕНИЕ
# ============================================================

@app.route(
    "/compare",
    methods=["GET", "POST"]
)
def compare():

    company1 = request.values.get(
        "company1"
    )

    company2 = request.values.get(
        "company2"
    )

    companies = list(
        COMPANY_SOURCES.keys()
    )

    # Проверяем компании
    if not company1 or company1 not in companies:
        return redirect("/")

    if not company2 or company2 not in companies:
        return redirect("/")

    if company1 == company2:
        return redirect("/")

    raw_data1 = INSURANCE_DATA.get(
        company1,
        {}
    )

    raw_data2 = INSURANCE_DATA.get(
        company2,
        {}
    )

    data1 = {}
    data2 = {}

    sources_detail1 = {}
    sources_detail2 = {}

    # --------------------------------------------------------
    # Компания 1
    # --------------------------------------------------------

    for field in KASKO_FIELDS:

        field_data = raw_data1.get(
            field,
            {}
        )

        if isinstance(
            field_data,
            dict
        ):

            value = field_data.get(
                "value",
                "Не найдено"
            )

            source_level = field_data.get(
                "source",
                0
            )

            source_url = field_data.get(
                "url"
            )

        else:

            value = field_data
            source_level = 0
            source_url = None

        data1[field] = value

        source_info = get_source_info(
            source_level
        )

        source_name = source_info.get(
            "name",
            "Не найдено"
        )

        source_icon = source_info.get(
            "icon",
            ""
        )

        if source_url:

            sources_detail1[field] = (
                f"{source_icon} "
                f"{source_name} — "
                f"{source_url}"
            )

        else:

            sources_detail1[field] = (
                f"{source_icon} "
                f"{source_name}"
            )

    # --------------------------------------------------------
    # Компания 2
    # --------------------------------------------------------

    for field in KASKO_FIELDS:

        field_data = raw_data2.get(
            field,
            {}
        )

        if isinstance(
            field_data,
            dict
        ):

            value = field_data.get(
                "value",
                "Не найдено"
            )

            source_level = field_data.get(
                "source",
                0
            )

            source_url = field_data.get(
                "url"
            )

        else:

            value = field_data
            source_level = 0
            source_url = None

        data2[field] = value

        source_info = get_source_info(
            source_level
        )

        source_name = source_info.get(
            "name",
            "Не найдено"
        )

        source_icon = source_info.get(
            "icon",
            ""
        )

        if source_url:

            sources_detail2[field] = (
                f"{source_icon} "
                f"{source_name} — "
                f"{source_url}"
            )

        else:

            sources_detail2[field] = (
                f"{source_icon} "
                f"{source_name}"
            )

    # Эти поля пока не собираются LLM.
    # Оставляем их, чтобы текущий result.html
    # не ломался.
    for data in [data1, data2]:

        data.setdefault(
            "advantages",
            "Не указано"
        )

        data.setdefault(
            "weak_points",
            "Не указано"
        )

        data.setdefault(
            "rating",
            "Не указано"
        )

        data.setdefault(
            "offices",
            "Не указано"
        )

    data1["_sources_detail"] = (
        sources_detail1
    )

    data2["_sources_detail"] = (
        sources_detail2
    )

    source1_url = COMPANY_SOURCES.get(
        company1,
        {}
    ).get(
        "url",
        "#"
    )

    source2_url = COMPANY_SOURCES.get(
        company2,
        {}
    ).get(
        "url",
        "#"
    )

    sources1 = [
        source1_url
    ]

    sources2 = [
        source2_url
    ]

    return render_template(
        "result.html",
        company1=company1,
        company2=company2,
        data1=data1,
        data2=data2,
        sources1=sources1,
        sources2=sources2,
        fields=KASKO_FIELDS,
        field_labels=FIELD_LABELS,
        last_updated=INSURANCE_DATA.get(
            "_last_updated",
            "Не обновлялось"
        ),
        source_info=get_source_info
    )


# ============================================================
# ROUTE: ОБНОВЛЕНИЕ ДАННЫХ
# ============================================================

@app.route(
    "/update",
    methods=["GET", "POST"]
)
def update():

    global INSURANCE_DATA

    try:

        new_data = collect_all_data()

        # Даже если часть компаний не обработалась,
        # сохраняем весь полученный результат.
        if isinstance(
            new_data,
            dict
        ):

            INSURANCE_DATA = new_data

            save_data(
                INSURANCE_DATA
            )

        else:

            logger.error(
                "❌ collect_all_data вернул "
                "неверный результат"
            )

    except Exception as exc:

        # Дополнительная защита всего /update.
        logger.exception(
            "🔥 КРИТИЧЕСКАЯ ОШИБКА /update: %s",
            exc
        )

    return redirect("/")


# ============================================================
# СОВМЕСТИМОСТЬ СО СТАРЫМИ URL
# ============================================================

@app.route(
    "/kasko"
)
def kasko():

    return redirect("/")


@app.route(
    "/casco"
)
def casco():

    return redirect("/")


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
