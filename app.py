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
from urllib.parse import urljoin, quote_plus
import io
import logging


# ============================================================
# НАСТРОЙКИ
# ============================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Актуальная production-модель Groq
GROQ_MODEL = "openai/gpt-oss-120b"

DATA_FILE = "insurance_data.json"


# ============================================================
# USER AGENTS
# ============================================================

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
]


# ============================================================
# ИСТОЧНИКИ КОМПАНИЙ
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
# ПАРАМЕТРЫ КАСКО
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
    "gap": "GAP",
    "total_loss": "Тотал",
    "fire": "Самовозгорание",
    "terrorism": "Терроризм",
    "drone": "БПЛА",
    "tow_truck": "Эвакуатор",
    "repair_type": "Тип ремонта",
    "payment_terms": "Срок выплаты"
}


# ============================================================
# ПРОМПТЫ
# ============================================================

FIELD_ANALYSIS_PROMPTS = {

    "franchise": """
Определи условия франшизы по КАСКО.

Укажи:
- предусмотрена ли франшиза;
- размер или возможные размеры франшизы;
- от чего зависит размер, если это указано.

Если информации нет — напиши "Не указано".
""",

    "without_certificates": """
Определи, в каких случаях страховая компания производит
выплату или ремонт без предоставления справок из полиции
или других компетентных органов.

Укажи ограничения, количество обращений и лимиты,
если они указаны.

Если информации нет — напиши "Не указано".
""",

    "gap": """
Определи наличие GAP в КАСКО.

Укажи:
- есть ли GAP;
- что именно покрывает;
- является ли опцией;
- есть ли ограничения.

Если информации нет — напиши "Не указано".
""",

    "total_loss": """
Определи условия страхового случая "Тотал"
(полная гибель транспортного средства).

Укажи:
- когда признаётся полная гибель;
- какой процент повреждения используется,
  если он указан;
- какие выплаты предусмотрены.

Если информации нет — напиши "Не указано".
""",

    "fire": """
Определи, покрывается ли самовозгорание автомобиля.

Отдельно обрати внимание на:
- пожар;
- самовозгорание;
- короткое замыкание;
- условия и исключения.

Если информации нет — напиши "Не указано".
""",

    "terrorism": """
Определи, покрываются ли ущерб или утрата автомобиля
в результате террористического акта.

Укажи условия и ограничения, если они есть.

Если информации нет — напиши "Не указано".
""",

    "drone": """
Определи, покрывается ли ущерб автомобилю в результате
падения, атаки или воздействия беспилотного летательного
аппарата (БПЛА/дрона).

Укажи:
- покрывается ли такой риск;
- при каких условиях;
- есть ли ограничения или исключения.

Если информация отсутствует — напиши "Не указано".
""",

    "tow_truck": """
Определи условия предоставления эвакуатора для легкового
автомобиля.

Укажи:
- предусмотрен ли эвакуатор;
- в каких случаях;
- количество обращений или лимиты;
- входит ли услуга в КАСКО или является дополнительной.

Если информации нет — напиши "Не указано".
""",

    "repair_type": """
Определи тип ремонта по КАСКО.

Укажи:
- ремонт у официального дилера;
- ремонт на станции технического обслуживания;
- направление на ремонт;
- денежную выплату;
- возможность выбора между вариантами;
- ограничения по возрасту автомобиля, если они есть.

Если информации нет — напиши "Не указано".
""",

    "payment_terms": """
Определи срок выплаты страхового возмещения.

Укажи:
- срок рассмотрения заявления;
- срок принятия решения;
- срок выплаты после принятия решения;
- общий срок, если он указан.

Не смешивай срок ремонта со сроком денежной выплаты.

Если информации нет — напиши "Не указано".
"""
}


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# HTTP HEADERS
# ============================================================

def get_headers(referer=None):

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive"
    }

    if referer:
        headers["Referer"] = referer

    return headers


# ============================================================
# ОЧИСТКА ТЕКСТА
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = str(text)

    # Неразрывные пробелы
    text = text.replace("\xa0", " ")

    # Много пробелов
    text = re.sub(r"[ \t]+", " ", text)

    # Слишком много переводов строк
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


# ============================================================
# ЗАГРУЗКА URL
# ============================================================

def fetch_url(url, timeout=30, referer=None):

    for attempt in range(3):

        try:

            headers = get_headers(referer)

            logger.info(
                f"🌐 Загружаем: {url} "
                f"(попытка {attempt + 1}/3)"
            )

            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                verify=False,
                allow_redirects=True
            )

            status = response.status_code
            final_url = response.url

            logger.info(
                f"HTTP {status}: {final_url}"
            )

            if status == 200:

                content_type = (
                    response.headers.get("Content-Type", "")
                    .lower()
                )

                return {
                    "success": True,
                    "status_code": status,
                    "content": response.content,
                    "text": response.text,
                    "url": final_url,
                    "content_type": content_type
                }

            # 401 — сайт требует авторизацию
            if status == 401:

                logger.error(
                    f"🔒 HTTP 401 Unauthorized: {url}"
                )

                # Повторяем один раз, но не бесконечно
                if attempt < 2:
                    time.sleep(2)
                    continue

                return {
                    "success": False,
                    "status_code": 401,
                    "error": "HTTP 401 Unauthorized",
                    "url": final_url
                }

            # 403 — пробуем ещё раз с другим User-Agent
            if status == 403:

                logger.warning(
                    f"🚫 HTTP 403 Forbidden: {url}"
                )

                if attempt < 2:
                    time.sleep(2 + attempt)
                    continue

                return {
                    "success": False,
                    "status_code": 403,
                    "error": "HTTP 403 Forbidden",
                    "url": final_url
                }

            # Временные ошибки
            if status in (429, 500, 502, 503, 504):

                logger.warning(
                    f"⚠️ HTTP {status}: {url}"
                )

                if attempt < 2:
                    time.sleep(2 + attempt)
                    continue

            logger.warning(
                f"⚠️ Неожиданный HTTP {status}: {url}"
            )

            if attempt < 2:
                time.sleep(2)

        except requests.exceptions.Timeout:

            logger.warning(
                f"⏱ Timeout: {url}, "
                f"попытка {attempt + 1}/3"
            )

            if attempt < 2:
                time.sleep(2)

        except requests.exceptions.RequestException as e:

            logger.error(
                f"❌ Ошибка загрузки {url}: {e}"
            )

            if attempt < 2:
                time.sleep(2)

        except Exception as e:

            logger.exception(
                f"❌ Неожиданная ошибка загрузки {url}: {e}"
            )

            if attempt < 2:
                time.sleep(2)

    return {
        "success": False,
        "error": "Не удалось загрузить",
        "url": url
    }


# ============================================================
# ИНФОРМАЦИЯ ОБ ИСТОЧНИКЕ
# ============================================================

def get_source_info(level):

    sources = {
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
    }

    return sources.get(
        level,
        sources[0]
    )


# ============================================================
# ПОИСК PDF
# ============================================================

def find_pdf_links(html, base_url):

    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    pdf_links = []

    keywords = [
        "правила",
        "условия",
        "полис",
        "тариф",
        "документ",
        "страхован"
    ]

    for a in soup.find_all("a"):

        href = (
            a.get("href")
            or a.get("data-href")
            or a.get("data-url")
            or a.get("data-file")
            or a.get("data-pdf")
        )

        if not href:
            continue

        href = href.strip()

        full_url = urljoin(
            base_url,
            href
        )

        text = clean_text(
            a.get_text(" ", strip=True)
        ).lower()

        href_lower = full_url.lower()

        is_pdf = (
            ".pdf" in href_lower
            or "download" in href_lower
            or "document" in href_lower
            or "file" in href_lower
        )

        has_keyword = any(
            keyword in text
            for keyword in keywords
        )

        if is_pdf or has_keyword:

            if full_url not in pdf_links:
                pdf_links.append(full_url)

    logger.info(
        f"📄 Найдено PDF/документов: {len(pdf_links)}"
    )

    return pdf_links


# ============================================================
# ИЗВЛЕЧЕНИЕ ТЕКСТА ИЗ PDF
# ============================================================

def extract_text_from_pdf(pdf_data):

    try:

        import PyPDF2

        pdf_file = io.BytesIO(pdf_data)

        reader = PyPDF2.PdfReader(
            pdf_file
        )

        pages = []

        logger.info(
            f"📑 PDF содержит {len(reader.pages)} страниц"
        )

        for index, page in enumerate(reader.pages):

            try:

                page_text = page.extract_text()

                if page_text:
                    pages.append(page_text)

            except Exception as e:

                logger.warning(
                    f"⚠️ Ошибка чтения страницы "
                    f"{index + 1}: {e}"
                )

        text = "\n\n".join(pages)

        text = clean_text(text)

        logger.info(
            f"✅ Из PDF извлечено "
            f"{len(text)} символов"
        )

        return text

    except ImportError:

        logger.error(
            "❌ PyPDF2 не установлен"
        )

        return ""

    except Exception as e:

        logger.exception(
            f"❌ Ошибка обработки PDF: {e}"
        )

        return ""


# ============================================================
# ПОДГОТОВКА РЕЛЕВАНТНЫХ ФРАГМЕНТОВ
# ============================================================

def extract_relevant_sections(text):

    """
    Для больших документов пытаемся выделить фрагменты,
    относящиеся к КАСКО и нужным параметрам.

    При этом для небольших документов возвращаем весь текст.
    """

    if not text:
        return ""

    # Небольшой документ отправляем целиком
    if len(text) <= 100000:
        return text

    logger.warning(
        f"Документ очень большой: {len(text)} символов"
    )

    keywords = [
        "франшиз",
        "без справ",
        "справк",
        "GAP",
        "ГЭП",
        "полная гибель",
        "тотал",
        "самовозгора",
        "пожар",
        "террорист",
        "терроризм",
        "беспилот",
        "БПЛА",
        "дрон",
        "эвакуатор",
        "ремонт",
        "станция технического обслуживания",
        "СТО",
        "дилер",
        "выплат",
        "срок"
    ]

    lines = text.splitlines()

    relevant = []

    radius = 8

    for i, line in enumerate(lines):

        line_lower = line.lower()

        if any(
            keyword.lower() in line_lower
            for keyword in keywords
        ):

            start = max(
                0,
                i - radius
            )

            end = min(
                len(lines),
                i + radius + 1
            )

            relevant.extend(
                lines[start:end]
            )

    # Убираем дубли
    result = []

    seen = set()

    for line in relevant:

        normalized = clean_text(line)

        if not normalized:
            continue

        if normalized not in seen:

            seen.add(normalized)
            result.append(normalized)

    result_text = "\n".join(result)

    # Если ничего полезного не нашли,
    # берём начало документа.
    if not result_text:

        result_text = text[:100000]

    if len(result_text) > 100000:

        result_text = result_text[:100000]

    logger.info(
        f"🔎 Для анализа отобрано "
        f"{len(result_text)} символов"
    )

    return result_text


# ============================================================
# ЕДИНЫЙ АНАЛИЗ КОМПАНИИ ЧЕРЕЗ GROQ
# ============================================================

def analyze_company_with_groq(
    text,
    company,
    source_type="PDF"
):

    if not GROQ_API_KEY:

        logger.error(
            "❌ GROQ_API_KEY не задан"
        )

        return {}

    if not text:

        logger.warning(
            f"{company}: отсутствует текст"
        )

        return {}

    text = extract_relevant_sections(
        text
    )

    fields_description = "\n\n".join(
        [
            f'ПАРАМЕТР "{FIELD_LABELS[field]}" '
            f'(ключ JSON: {field}):\n'
            f'{FIELD_ANALYSIS_PROMPTS[field]}'
            for field in KASKO_FIELDS
        ]
    )

    system_prompt = """
Ты — эксперт по страхованию КАСКО.

Твоя задача — анализировать правила и условия страхования
и извлекать конкретные условия по заданным параметрам.

КРИТИЧЕСКИЕ ПРАВИЛА:

1. Используй только информацию из предоставленного текста.
2. Ничего не придумывай.
3. Не делай предположений.
4. Если информация отсутствует — напиши "Не указано".
5. Если условие зависит от обстоятельств — укажи это кратко.
6. Не смешивай разные параметры.
7. Не копируй длинные юридические фрагменты.
8. Ответ должен быть понятен человеку,
   который сравнивает страховые компании.
9. Каждый параметр должен получить отдельное значение.
10. Верни строго JSON.
"""

    user_prompt = f"""
Страховая компания: {company}

Источник:
{source_type}

================ ДОКУМЕНТ ================

{text}

================ КОНЕЦ ДОКУМЕНТА ================

Необходимо определить следующие параметры:

{fields_description}

Верни строго объект JSON следующего вида:

{{
    "franchise": "ответ",
    "without_certificates": "ответ",
    "gap": "ответ",
    "total_loss": "ответ",
    "fire": "ответ",
    "terrorism": "ответ",
    "drone": "ответ",
    "tow_truck": "ответ",
    "repair_type": "ответ",
    "payment_terms": "ответ"
}}

Не добавляй Markdown.
Не добавляй ```json.
Не добавляй комментарии.
Не добавляй текст до или после JSON.
"""

    payload = {
        "model": GROQ_MODEL,

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

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    groq_url = (
        "https://api.groq.com/openai/v1/"
        "chat/completions"
    )

    for attempt in range(3):

        try:

            logger.info(
                f"🤖 {company}: Groq — "
                f"анализ всех {len(KASKO_FIELDS)} параметров "
                f"(попытка {attempt + 1}/3)"
            )

            response = requests.post(
                groq_url,
                headers=headers,
                json=payload,
                timeout=90
            )

            # ------------------------------------------------
            # УСПЕШНЫЙ ОТВЕТ
            # ------------------------------------------------

            if response.status_code == 200:

                data = response.json()

                content = (
                    data
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

                content = content.strip()

                if not content:

                    logger.error(
                        f"{company}: Groq вернул пустой ответ"
                    )

                    continue

                logger.info(
                    f"✅ {company}: Groq ответил "
                    f"({len(content)} символов)"
                )

                # --------------------------------------------
                # Парсинг JSON
                # --------------------------------------------

                try:

                    result = json.loads(
                        content
                    )

                except json.JSONDecodeError:

                    logger.warning(
                        f"{company}: "
                        f"не удалось напрямую распарсить JSON"
                    )

                    # Ищем JSON внутри ответа
                    match = re.search(
                        r"\{.*\}",
                        content,
                        re.DOTALL
                    )

                    if not match:

                        logger.error(
                            f"{company}: JSON не найден"
                        )

                        continue

                    try:

                        result = json.loads(
                            match.group(0)
                        )

                    except json.JSONDecodeError as e:

                        logger.error(
                            f"{company}: "
                            f"ошибка JSON после извлечения: {e}"
                        )

                        continue

                if not isinstance(result, dict):

                    logger.error(
                        f"{company}: "
                        f"Groq вернул не объект JSON"
                    )

                    continue

                # --------------------------------------------
                # Нормализация результата
                # --------------------------------------------

                normalized = {}

                for field in KASKO_FIELDS:

                    value = result.get(
                        field,
                        "Не указано"
                    )

                    if value is None:

                        value = "Не указано"

                    if isinstance(value, (dict, list)):

                        value = json.dumps(
                            value,
                            ensure_ascii=False
                        )

                    value = clean_text(
                        str(value)
                    )

                    if not value:

                        value = "Не указано"

                    normalized[field] = value

                logger.info(
                    f"🎯 {company}: "
                    f"получены все параметры"
                )

                return normalized

            # ------------------------------------------------
            # ОШИБКА 429
            # ------------------------------------------------

            if response.status_code == 429:

                logger.warning(
                    f"⏳ {company}: Groq HTTP 429 "
                    f"(лимит запросов)"
                )

                if attempt < 2:

                    time.sleep(
                        5 * (attempt + 1)
                    )

                    continue

                return {}

            # ------------------------------------------------
            # ОШИБКИ СЕРВЕРА
            # ------------------------------------------------

            if response.status_code in (
                500,
                502,
                503,
                504
            ):

                logger.warning(
                    f"⚠️ {company}: Groq HTTP "
                    f"{response.status_code}"
                )

                if attempt < 2:

                    time.sleep(
                        3 * (attempt + 1)
                    )

                    continue

                return {}

            # ------------------------------------------------
            # ОСТАЛЬНЫЕ ОШИБКИ
            # ------------------------------------------------

            logger.error(
                f"❌ {company}: Groq HTTP "
                f"{response.status_code}: "
                f"{response.text[:1000]}"
            )

            return {}

        except requests.exceptions.Timeout:

            logger.warning(
                f"⏱ {company}: timeout Groq "
                f"(попытка {attempt + 1}/3)"
            )

            if attempt < 2:
                time.sleep(
                    3 * (attempt + 1)
                )

        except requests.exceptions.RequestException as e:

            logger.error(
                f"❌ {company}: ошибка запроса Groq: {e}"
            )

            if attempt < 2:
                time.sleep(
                    3 * (attempt + 1)
                )

        except Exception as e:

            logger.exception(
                f"❌ {company}: неожиданная ошибка Groq: {e}"
            )

            if attempt < 2:
                time.sleep(
                    3 * (attempt + 1)
                )

    logger.error(
        f"❌ {company}: Groq не смог обработать документ"
    )

    return {}


# ============================================================
# РЕЗЕРВНЫЙ АНАЛИЗ ОДНОГО ПОЛЯ
# ============================================================

def analyze_with_groq(
    text,
    field,
    company,
    source_type="PDF"
):

    if not GROQ_API_KEY:
        return None

    prompt = FIELD_ANALYSIS_PROMPTS.get(
        field
    )

    if not prompt:
        return None

    if len(text) > 100000:
        text = text[:100000]

    payload = {

        "model": GROQ_MODEL,

        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты — эксперт по страхованию КАСКО. "
                    "Используй только предоставленный текст. "
                    "Не придумывай информацию. "
                    "Если данных нет — напиши "
                    "'Не указано'."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Компания: {company}\n\n"
                    f"Текст:\n{text}\n\n"
                    f"Вопрос:\n{prompt}"
                )
            }
        ],

        "temperature": 0.1,

        "max_tokens": 300
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    try:

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:

            logger.error(
                f"{company}: Groq HTTP "
                f"{response.status_code}"
            )

            return None

        data = response.json()

        result = (
            data
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        return clean_text(result)

    except Exception as e:

        logger.error(
            f"{company}: ошибка Groq: {e}"
        )

        return None


# ============================================================
# РАЗБОР HTML
# ============================================================

def parse_html_page(
    html,
    url
):

    if not html:
        return ""

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # Удаляем мусор
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

    except Exception as e:

        logger.error(
            f"Ошибка разбора HTML {url}: {e}"
        )

        return ""


# ============================================================
# СОЗДАНИЕ РЕЗУЛЬТАТА ПОЛЯ
# ============================================================

def make_field_result(
    value,
    source_level,
    source_url=None
):

    return {
        "value": value or "Не найдено",
        "source": source_level,
        "url": source_url
    }


# ============================================================
# СБОР ДАННЫХ ПО ОДНОЙ КОМПАНИИ
# ============================================================

def collect_company_data(company):

    logger.info("")
    logger.info("=" * 70)
    logger.info(f"🏢 НАЧИНАЕМ: {company}")
    logger.info("=" * 70)

    source = COMPANY_SOURCES.get(
        company
    )

    if not source:

        logger.error(
            f"{company}: источник не найден"
        )

        return {
            field: make_field_result(
                "Не найдено",
                0
            )
            for field in KASKO_FIELDS
        }

    url = source["url"]
    source_type = source["type"]

    logger.info(
        f"🔗 Источник: {url}"
    )

    # --------------------------------------------------------
    # Загружаем страницу
    # --------------------------------------------------------

    response = fetch_url(
        url,
        timeout=30
    )

    if not response.get("success"):

        error = response.get(
            "error",
            "Неизвестная ошибка"
        )

        logger.error(
            f"❌ {company}: "
            f"не удалось загрузить источник: "
            f"{error}"
        )

        return {
            field: make_field_result(
                "Источник недоступен",
                0,
                url
            )
            for field in KASKO_FIELDS
        }

    html = response.get(
        "text",
        ""
    )

    final_url = response.get(
        "url",
        url
    )

    content_type = response.get(
        "content_type",
        ""
    )

    # ========================================================
    # ЕСЛИ СТРАНИЦА СОДЕРЖИТ PDF
    # ========================================================

    pdf_text = ""
    used_pdf_url = None

    # Если сам ответ является PDF
    if (
        "application/pdf" in content_type
        or final_url.lower().split("?")[0].endswith(".pdf")
    ):

        logger.info(
            f"📄 Получен прямой PDF: {final_url}"
        )

        pdf_text = extract_text_from_pdf(
            response.get("content", b"")
        )

        if pdf_text:
            used_pdf_url = final_url

    # --------------------------------------------------------
    # Если это HTML — ищем PDF
    # --------------------------------------------------------

    if not pdf_text and html:

        pdf_links = find_pdf_links(
            html,
            final_url
        )

        # Пытаемся скачать до 5 документов
        for index, pdf_url in enumerate(
            pdf_links[:5],
            start=1
        ):

            logger.info(
                f"📥 Пробуем PDF "
                f"{index}/{min(len(pdf_links), 5)}: "
                f"{pdf_url}"
            )

            pdf_response = fetch_url(
                pdf_url,
                timeout=45,
                referer=final_url
            )

            if not pdf_response.get(
                "success"
            ):

                logger.warning(
                    f"⚠️ PDF недоступен: "
                    f"{pdf_url}"
                )

                continue

            pdf_data = pdf_response.get(
                "content",
                b""
            )

            extracted = extract_text_from_pdf(
                pdf_data
            )

            if extracted and len(extracted) > 100:

                pdf_text = extracted

                used_pdf_url = pdf_response.get(
                    "url",
                    pdf_url
                )

                logger.info(
                    f"✅ Используем PDF: "
                    f"{used_pdf_url}"
                )

                break

    # ========================================================
    # АНАЛИЗ PDF
    # ========================================================

    if pdf_text:

        logger.info(
            f"📄 {company}: "
            f"анализируем PDF через Groq"
        )

        analysis = analyze_company_with_groq(
            pdf_text,
            company,
            "PDF / Правила страхования"
        )

        result = {}

        for field in KASKO_FIELDS:

            value = analysis.get(
                field,
                "Не указано"
            )

            result[field] = make_field_result(
                value,
                2,
                used_pdf_url
            )

        logger.info(
            f"✅ {company}: "
            f"PDF успешно обработан"
        )

        return result

    # ========================================================
    # ЕСЛИ PDF НЕ НАШЛИ — АНАЛИЗИРУЕМ HTML
    # ========================================================

    if html:

        logger.info(
            f"🌐 {company}: "
            f"PDF не найден, анализируем HTML"
        )

        html_text = parse_html_page(
            html,
            final_url
        )

        if html_text:

            analysis = analyze_company_with_groq(
                html_text,
                company,
                "HTML / Сайт страховой компании"
            )

            result = {}

            for field in KASKO_FIELDS:

                value = analysis.get(
                    field,
                    "Не указано"
                )

                result[field] = make_field_result(
                    value,
                    3,
                    final_url
                )

            return result

    # ========================================================
    # НИЧЕГО НЕ НАШЛИ
    # ========================================================

    logger.error(
        f"❌ {company}: "
        f"не найден ни PDF, ни пригодный HTML"
    )

    return {
        field: make_field_result(
            "Не найдено",
            0,
            final_url
        )
        for field in KASKO_FIELDS
    }


# ============================================================
# СБОР ДАННЫХ ПО ВСЕМ КОМПАНИЯМ
# ============================================================

def collect_all_data():

    logger.info("")
    logger.info("#" * 70)
    logger.info("🚀 НАЧИНАЕМ ОБНОВЛЕНИЕ ДАННЫХ")
    logger.info("#" * 70)

    data = {}

    companies = list(
        COMPANY_SOURCES.keys()
    )

    logger.info(
        f"Компаний к обработке: {len(companies)}"
    )

    for index, company in enumerate(
        companies,
        start=1
    ):

        logger.info("")
        logger.info(
            f"🔄 Компания {index}/{len(companies)}: "
            f"{company}"
        )

        try:

            data[company] = collect_company_data(
                company
            )

        except Exception as e:

            logger.exception(
                f"❌ Критическая ошибка "
                f"при обработке {company}: {e}"
            )

            data[company] = {
                field: make_field_result(
                    "Ошибка обработки",
                    0
                )
                for field in KASKO_FIELDS
            }

        # Пауза между компаниями
        if index < len(companies):

            time.sleep(1)

    # --------------------------------------------------------
    # Метаданные
    # --------------------------------------------------------

    data["_last_updated"] = datetime.now().strftime(
        "%d.%m.%Y %H:%M"
    )

    data["_fields"] = KASKO_FIELDS

    logger.info("")
    logger.info("#" * 70)
    logger.info("✅ ОБНОВЛЕНИЕ ЗАВЕРШЕНО")
    logger.info("#" * 70)

    return data


# ============================================================
# СОХРАНЕНИЕ ДАННЫХ
# ============================================================

def save_data(data):

    try:

        with open(
            DATA_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        logger.info(
            f"💾 Данные сохранены в {DATA_FILE}"
        )

        return True

    except Exception as e:

        logger.exception(
            f"❌ Ошибка сохранения данных: {e}"
        )

        return False


# ============================================================
# ЗАГРУЗКА КЭША
# ============================================================

def load_data():

    if os.path.exists(
        DATA_FILE
    ):

        try:

            with open(
                DATA_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            logger.info(
                f"💾 Загружен кэш "
                f"{DATA_FILE}"
            )

            return data

        except Exception as e:

            logger.error(
                f"❌ Ошибка чтения {DATA_FILE}: {e}"
            )

    logger.info(
        "📥 Кэш не найден. "
        "Запускаем первичный сбор данных."
    )

    data = collect_all_data()

    save_data(data)

    return data


# ============================================================
# ГЛОБАЛЬНЫЕ ДАННЫЕ
# ============================================================

INSURANCE_DATA = load_data()


# ============================================================
# ROUTE: ГЛАВНАЯ
# ============================================================

@app.route("/")
def index():

    companies = [
        company
        for company in COMPANY_SOURCES.keys()
    ]

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

    companies = [
        company
        for company in COMPANY_SOURCES.keys()
    ]

    selected_companies = request.values.getlist(
        "companies"
    )

    if not selected_companies:

        selected_companies = companies

    selected_companies = [
        company
        for company in selected_companies
        if company in companies
    ]

    return render_template(
        "result.html",
        companies=selected_companies,
        all_companies=companies,
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
# ROUTE: ОБНОВЛЕНИЕ
# ============================================================

@app.route(
    "/update",
    methods=["GET", "POST"]
)
def update():

    global INSURANCE_DATA

    logger.info(
        "🔄 Запущено ручное обновление данных"
    )

    INSURANCE_DATA = collect_all_data()

    save_data(
        INSURANCE_DATA
    )

    return redirect("/")


# ============================================================
# СТАРЫЕ ROUTES
# ============================================================

@app.route("/kasko")
def old_kasko():

    return redirect("/")


@app.route("/casco")
def old_casco():

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
