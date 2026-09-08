# app.py — ИСПРАВЛЕННАЯ ВЕРСИЯ С ОБРЕЗКОЙ ТЕКСТА ДО 3000 СИМВОЛОВ

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
from urllib.parse import urljoin, urlparse
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

GROQ_MODELS = [
    os.environ.get(
        "GROQ_MODEL",
        "openai/gpt-oss-120b"
    ),
    "openai/gpt-oss-20b"
]

GROQ_URL = (
    "https://api.groq.com/openai/v1/chat/completions"
)

GROQ_RETRIES = 3

# Таймаут Groq
GROQ_CONNECT_TIMEOUT = 10
GROQ_READ_TIMEOUT = 90

# МАКСИМАЛЬНЫЙ РАЗМЕР ТЕКСТА ДЛЯ GROQ
MAX_GROQ_TEXT_LENGTH = 3000


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

HTTP_RETRIES = 3

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
# ПРОМПТЫ
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
        "Connection": "close",
        "Cache-Control": "no-cache",
    }


def clean_text(text: str) -> str:

    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(
        r"\n\s*\n\s*\n+",
        "\n\n",
        text
    )

    return text.strip()


def fetch_url(
    url: str,
    retries: int = HTTP_RETRIES,
    timeout: Optional[int] = None
) -> Optional[Dict[str, Any]]:

    last_error = None

    if timeout is not None:
        connect_timeout = min(timeout, HTTP_CONNECT_TIMEOUT)
        read_timeout = timeout
    else:
        connect_timeout = HTTP_CONNECT_TIMEOUT
        read_timeout = HTTP_READ_TIMEOUT

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
                timeout=(
                    connect_timeout,
                    read_timeout
                ),
                verify=False,
                allow_redirects=True
            )

            status = response.status_code

            logger.info(
                "📡 HTTP %s: %s",
                status,
                url
            )

            content_type = (
                response.headers
                .get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

            if status == 200:

                return {
                    "success": True,
                    "status": status,
                    "content": response.content,
                    "text": response.text,
                    "url": response.url,
                    "content_type": content_type
                }

            if status in (
                401,
                403,
                408,
                429,
                500,
                502,
                503,
                504
            ):

                logger.warning(
                    "⚠️ HTTP %s для %s",
                    status,
                    url
                )

                if attempt < retries:

                    if status == 429:
                        wait_time = 5 * attempt
                    elif status in (
                        500,
                        502,
                        503,
                        504
                    ):
                        wait_time = 3 * attempt
                    else:
                        wait_time = 2 * attempt

                    wait_time += random.uniform(
                        0.5,
                        1.5
                    )

                    logger.info(
                        "⏳ Ждём %.1f сек.",
                        wait_time
                    )

                    time.sleep(
                        wait_time
                    )

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
                "content_type": content_type
            }

        except requests.exceptions.ConnectTimeout as exc:

            last_error = exc

            logger.warning(
                "⏱️ Connect timeout: %s",
                url
            )

        except requests.exceptions.ReadTimeout as exc:

            last_error = exc

            logger.warning(
                "⏱️ Read timeout: %s",
                url
            )

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

            wait_time = (
                2 * attempt +
                random.uniform(
                    0.5,
                    1.5
                )
            )

            time.sleep(
                wait_time
            )

    logger.error(
        "❌ Не удалось получить URL: %s | %s",
        url,
        last_error
    )

    return None


# ============================================================
# ПРОВЕРКА PDF
# ============================================================

PDF_BAD_WORDS = [
    "cookie",
    "cookies",
    "privacy",
    "политика конфиденциальности",
    "политика обработки",
    "персональных данных",
    "согласие на обработку",
    "согласие_pd",
    "consent",
    "реквизиты",
    "пользовательское соглашение",
    "лицензия",
    "лицензии"
]


PDF_GOOD_WORDS = [
    "каско",
    "kasko",
    "правила страхования",
    "правила",
    "условия страхования",
    "автотранспорт",
    "транспортных средств",
    "транспортное средство",
    "страхование транспортных средств",
    "страхования транспортных средств"
]


def score_pdf_link(
    url: str,
    text: str
) -> int:

    combined = (
        f"{url} {text}"
    ).lower()

    score = 0

    for word in PDF_GOOD_WORDS:

        if word in combined:
            score += 10

    for word in PDF_BAD_WORDS:

        if word in combined:
            score -= 100

    if ".pdf" in url.lower():
        score += 5

    if "kasko" in url.lower():
        score += 20

    if "каско" in combined:
        score += 20

    if "правил" in combined:
        score += 15

    return score


def find_pdf_links(
    html: str,
    base_url: str
) -> List[str]:

    scored_links = []

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        for tag in soup.find_all(
            "a",
            href=True
        ):

            href = tag.get(
                "href",
                ""
            ).strip()

            if not href:
                continue

            full_url = urljoin(
                base_url,
                href
            )

            if not full_url.startswith(
                (
                    "http://",
                    "https://"
                )
            ):
                continue

            text = tag.get_text(
                " ",
                strip=True
            )

            href_lower = href.lower()
            text_lower = text.lower()

            is_candidate = (
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

            if not is_candidate:
                continue

            score = score_pdf_link(
                full_url,
                text
            )

            # Полностью мусорные документы сразу отбрасываем.
            if score <= -50:
                logger.info(
                    "🚫 Отброшен нерелевантный документ: %s",
                    full_url
                )
                continue

            scored_links.append(
                (
                    score,
                    full_url
                )
            )

        # Убираем дубли
        unique = {}

        for score, url in scored_links:

            if url not in unique:
                unique[url] = score
            else:
                unique[url] = max(
                    unique[url],
                    score
                )

        result = sorted(
            unique.keys(),
            key=lambda x: unique[x],
            reverse=True
        )

        logger.info(
            "📚 Найдено релевантных PDF/документов: %s",
            len(result)
        )

        for index, url in enumerate(
            result[:10],
            start=1
        ):

            logger.info(
                "   %s. [%s] %s",
                index,
                unique[url],
                url
            )

        return result

    except Exception as exc:

        logger.exception(
            "❌ Ошибка поиска PDF: %s",
            exc
        )

        return []


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_text_from_pdf(
    content: bytes
) -> str:

    if not content:
        return ""

    if content[:4] != b"%PDF":

        logger.warning(
            "⚠️ Переданный файл не похож на PDF."
        )

        return ""

    try:

        import PyPDF2

        reader = PyPDF2.PdfReader(
            io.BytesIO(content)
        )

        pages = []

        for index, page in enumerate(
            reader.pages
        ):

            try:

                text = (
                    page.extract_text()
                    or ""
                )

                if text.strip():

                    pages.append(
                        text
                    )

            except Exception as exc:

                logger.warning(
                    "⚠️ Ошибка чтения страницы PDF %s: %s",
                    index + 1,
                    exc
                )

        result = clean_text(
            "\n\n".join(
                pages
            )
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
# РЕЛЕВАНТНЫЕ ФРАГМЕНТЫ (ОБРЕЗКА ДО 3000 СИМВОЛОВ)
# ============================================================

def extract_relevant_sections(text: str, max_chars: int = MAX_GROQ_TEXT_LENGTH) -> str:
    """
    Извлекает релевантные фрагменты текста, не превышая max_chars.
    Жёсткое ограничение — 3000 символов для Groq.
    """
    if not text:
        return ""

    text = clean_text(text)

    if len(text) <= max_chars:
        return text

    logger.info(f"📚 Документ большой: {len(text)} символов. Ищем ключевые фрагменты...")

    # Ключевые слова для поиска
    keywords = [
        "франшиз", "справк", "gap", "gар", "тотал", "гибел",
        "пожар", "возгора", "самовозгора", "террор", "дрон", "бпла",
        "беспилот", "эвакуатор", "эвакуац", "ремонт", "стоа",
        "дилер", "выплат", "урегулирован", "страховой случай",
        "полис", "каско", "авто"
    ]

    lines = text.splitlines()
    chunks = []
    window = 10  # строк до и после ключевого слова

    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(kw in line_lower for kw in keywords):
            start = max(0, i - window)
            end = min(len(lines), i + window + 1)
            chunk = "\n".join(lines[start:end])
            chunks.append(chunk)

    if not chunks:
        # Если не нашли ключевых слов — берём начало документа
        logger.info("⚠️ Ключевые слова не найдены, берём начало документа")
        return text[:max_chars]

    # Объединяем уникальные фрагменты
    seen = set()
    unique_chunks = []
    for chunk in chunks:
        normalized = re.sub(r"\s+", " ", chunk).strip()
        if not normalized:
            continue
        key = normalized[:300]
        if key in seen:
            continue
        seen.add(key)
        unique_chunks.append(chunk)

    result = "\n\n".join(unique_chunks)

    # Жёсткая обрезка до max_chars
    if len(result) > max_chars:
        result = result[:max_chars]
        # Обрезаем до последнего целого предложения
        last_period = result.rfind('.')
        if last_period > max_chars * 0.8:
            result = result[:last_period + 1]

    logger.info(f"📊 Извлечено {len(result)} символов (лимит {max_chars})")
    return result


# ============================================================
# NORMALIZE
# ============================================================

def normalize_llm_result(
    data: Any
) -> Dict[str, str]:

    if not isinstance(
        data,
        dict
    ):
        data = {}

    result = {}

    for field in KASKO_FIELDS:

        value = data.get(
            field
        )

        if value is None:
            value = "Не найдено"

        if isinstance(
            value,
            (dict, list)
        ):

            try:

                value = json.dumps(
                    value,
                    ensure_ascii=False
                )

            except Exception:

                value = str(
                    value
                )

        value = str(
            value
        ).strip()

        if not value:
            value = "Не найдено"

        result[field] = value

    return result


def count_found_fields(
    data: Dict[str, str]
) -> int:

    if not isinstance(
        data,
        dict
    ):
        return 0

    count = 0

    for field in KASKO_FIELDS:

        value = data.get(
            field,
            ""
        )

        if value is None:
            continue

        value = str(
            value
        ).strip()

        if not value:
            continue

        if value.lower() in (
            "не найдено",
            "не указано",
            "нет информации",
            "информация отсутствует"
        ):
            continue

        count += 1

    return count


def try_parse_json(
    content: str
) -> Dict[str, Any]:

    if not content:
        return {}

    content = content.strip()

    try:

        data = json.loads(
            content
        )

        if isinstance(
            data,
            dict
        ):
            return data

    except Exception:
        pass

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

            if isinstance(
                data,
                dict
            ):
                return data

        except Exception:
            pass

    start = content.find(
        "{"
    )

    end = content.rfind(
        "}"
    )

    if start >= 0 and end > start:

        candidate = content[
            start:end + 1
        ]

        try:

            data = json.loads(
                candidate
            )

            if isinstance(
                data,
                dict
            ):
                return data

        except Exception:
            pass

    return {}


# ============================================================
# GROQ (С ОБРЕЗКОЙ ТЕКСТА)
# ============================================================

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

    # ЖЁСТКАЯ ОБРЕЗКА ДО 3000 СИМВОЛОВ
    relevant_text = extract_relevant_sections(
        text,
        max_chars=MAX_GROQ_TEXT_LENGTH
    )

    if len(
        clean_text(relevant_text)
    ) < 100:

        logger.warning(
            "⚠️ Слишком мало текста для анализа: "
            "%s | %s символов",
            company,
            len(relevant_text)
        )

        return {}

    logger.info(
        "🤖 Отправляем в Groq: %s символов (обрезано до %s)",
        len(relevant_text),
        MAX_GROQ_TEXT_LENGTH
    )

    fields_description = "\n\n".join(
        [
            f"{field}: "
            f"{FIELD_ANALYSIS_PROMPTS[field]}"
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

Верни строго JSON:

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
        "Authorization": (
            f"Bearer {GROQ_API_KEY}"
        ),
        "Content-Type": "application/json"
    }

    models = []

    for model in GROQ_MODELS:

        if model and model not in models:
            models.append(model)

    if not models:

        models = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b"
        ]

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
                    timeout=(
                        GROQ_CONNECT_TIMEOUT,
                        GROQ_READ_TIMEOUT
                    )
                )

                status = response.status_code

                logger.info(
                    "🤖 Groq HTTP %s | %s | попытка %s/%s",
                    status,
                    company,
                    attempt,
                    GROQ_RETRIES
                )

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

                        message = choices[0].get(
                            "message",
                            {}
                        )

                        content = message.get(
                            "content",
                            ""
                        )

                        parsed = try_parse_json(
                            content
                        )

                        if not parsed:

                            logger.error(
                                "❌ Groq вернул "
                                "невалидный JSON: %s",
                                content[:1000]
                            )

                            continue

                        result = normalize_llm_result(
                            parsed
                        )

                        found = count_found_fields(
                            result
                        )

                        logger.info(
                            "🔎 Groq: %s | найдено полей: %s/%s",
                            company,
                            found,
                            len(KASKO_FIELDS)
                        )

                        if found == 0:

                            logger.warning(
                                "⚠️ Groq ответил 200, "
                                "но не нашёл ни одного поля: %s",
                                company
                            )

                            continue

                        logger.info(
                            "✅ Groq успешно обработал: %s",
                            company
                        )

                        return result

                    except Exception as exc:

                        logger.exception(
                            "❌ Ошибка разбора ответа Groq: %s",
                            exc
                        )

                        continue

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

                    break

                if status in (
                    401,
                    403
                ):

                    logger.error(
                        "❌ Groq авторизация "
                        "не прошла: HTTP %s",
                        status
                    )

                    return {}

                if status == 429:

                    if attempt < GROQ_RETRIES:

                        wait_time = (
                            10 * attempt
                        )

                        logger.warning(
                            "⏳ Groq rate limit. "
                            "Ждём %s сек.",
                            wait_time
                        )

                        time.sleep(
                            wait_time
                        )

                        continue

                    break

                if status in (
                    413
                ):

                    logger.error(
                        "❌ Groq 413: запрос слишком большой. "
                        "Уменьшаем текст до 2000 символов."
                    )

                    # Пробуем с ещё меньшим текстом
                    if len(relevant_text) > 2000:
                        relevant_text = relevant_text[:2000]
                        # Обновляем user_prompt с новым текстом
                        user_prompt = user_prompt.replace(
                            relevant_text,
                            relevant_text[:2000]
                        )
                        continue

                    break

                if status in (
                    500,
                    502,
                    503,
                    504
                ):

                    if attempt < GROQ_RETRIES:

                        wait_time = (
                            5 * attempt
                        )

                        logger.warning(
                            "⏳ Groq серверная ошибка. "
                            "Ждём %s сек.",
                            wait_time
                        )

                        time.sleep(
                            wait_time
                        )

                        continue

                    break

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

        logger.warning(
            "⚠️ Модель %s не обработала %s. "
            "Пробуем следующую.",
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

    if not html:
        return ""

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
            "svg",
            "form"
        ]):

            tag.decompose()

        text = soup.get_text(
            "\n",
            strip=True
        )

        return clean_text(
            text
        )

    except Exception as exc:

        logger.exception(
            "❌ Ошибка парсинга HTML: %s",
            exc
        )

        return ""


# ============================================================
# SOURCE
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

    value = str(
        value
    ).strip()

    if not value:
        value = "Не найдено"

    return {
        "value": value,
        "source": source_level,
        "url": source_url
    }


def empty_company_data(
    source_url: Optional[str] = None
) -> Dict[str, Any]:

    return {
        field: make_field_result(
            "Не найдено",
            0,
            source_url
        )
        for field in KASKO_FIELDS
    }


def company_has_data(
    company_data: Dict[str, Any]
) -> bool:

    if not isinstance(
        company_data,
        dict
    ):
        return False

    for field in KASKO_FIELDS:

        field_data = company_data.get(
            field,
            {}
        )

        if not isinstance(
            field_data,
            dict
        ):
            continue

        value = field_data.get(
            "value"
        )

        if value is None:
            continue

        value = str(
            value
        ).strip()

        if value and value != "Не найдено":
            return True

    return False


# ============================================================
# СБОР ОДНОЙ КОМПАНИИ
# ============================================================

def collect_company_data(
    company: str
) -> Dict[str, Any]:

    logger.info("")
    logger.info(
        "=" * 70
    )
    logger.info(
        "🏢 НАЧИНАЕМ: %s",
        company
    )
    logger.info(
        "=" * 70
    )

    source = COMPANY_SOURCES.get(
        company
    )

    if not source:

        logger.error(
            "❌ Источник не найден: %s",
            company
        )

        return empty_company_data()

    source_url = source.get(
        "url"
    )

    response = fetch_url(
        source_url
    )

    if not response:

        logger.error(
            "❌ Не удалось получить источник: %s",
            company
        )

        return empty_company_data(
            source_url
        )

    if not response.get(
        "success"
    ):

        logger.error(
            "❌ Источник вернул ошибку: "
            "%s | HTTP %s",
            company,
            response.get("status")
        )

        return empty_company_data(
            source_url
        )

    content = response.get(
        "content",
        b""
    )

    html = response.get(
        "text",
        ""
    )

    content_type = (
        response.get(
            "content_type",
            ""
        ).lower()
    )

    final_url = response.get(
        "url",
        source_url
    )

    # ========================================================
    # 1. ПРЯМОЙ PDF
    # ========================================================

    is_pdf = (
        "application/pdf" in content_type
        or final_url.lower().endswith(".pdf")
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

        if pdf_text and len(pdf_text) > 100:

            llm_data = analyze_company_with_groq(
                pdf_text,
                company,
                "PDF / Правила страхования"
            )

            if llm_data:

                result = {}

                for field in KASKO_FIELDS:

                    result[field] = make_field_result(
                        llm_data.get(
                            field,
                            "Не найдено"
                        ),
                        2,
                        final_url
                    )

                if company_has_data(
                    result
                ):

                    logger.info(
                        "✅ Данные получены из PDF: %s",
                        company
                    )

                    return result

    # ========================================================
    # 2. HTML → PDF
    # ========================================================

    if html:

        logger.info(
            "🌐 Анализируем HTML: %s",
            company
        )

        pdf_links = find_pdf_links(
            html,
            final_url
        )

        # Не ограничиваемся тупо первыми 5.
        # Но и не скачиваем десятки документов.
        pdf_links = pdf_links[:8]

        for index, pdf_url in enumerate(
            pdf_links,
            start=1
        ):

            logger.info(
                "📥 PDF %s/%s: %s",
                index,
                len(pdf_links),
                pdf_url
            )

            try:

                pdf_response = fetch_url(
                    pdf_url,
                    retries=2
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
                    pdf_response
                    .get(
                        "content_type",
                        ""
                    )
                    .lower()
                )

                if not (
                    "application/pdf"
                    in pdf_content_type
                    or pdf_content[:4] == b"%PDF"
                ):

                    logger.info(
                        "⚠️ Это не PDF: %s",
                        pdf_url
                    )

                    continue

                pdf_text = extract_text_from_pdf(
                    pdf_content
                )

                if len(
                    pdf_text
                ) < 100:

                    logger.warning(
                        "⚠️ PDF слишком пустой: %s",
                        pdf_url
                    )

                    continue

                llm_data = analyze_company_with_groq(
                    pdf_text,
                    company,
                    "PDF / Правила страхования"
                )

                if not llm_data:

                    logger.warning(
                        "⚠️ Этот PDF не дал данных. "
                        "Пробуем следующий."
                    )

                    continue

                result = {}

                for field in KASKO_FIELDS:

                    result[field] = make_field_result(
                        llm_data.get(
                            field,
                            "Не найдено"
                        ),
                        2,
                        pdf_url
                    )

                if company_has_data(
                    result
                ):

                    logger.info(
                        "✅ Использован PDF: %s",
                        pdf_url
                    )

                    return result

            except Exception as exc:

                logger.exception(
                    "❌ Ошибка обработки PDF %s: %s",
                    pdf_url,
                    exc
                )

                continue

    # ========================================================
    # 3. HTML → GROQ
    # ========================================================

    html_text = parse_html_page(
        html
    )

    # Критически важно:
    # не отправляем "3 символа" в Groq.
    if len(
        html_text
    ) >= 100:

        logger.info(
            "🤖 Передаём HTML в Groq: "
            "%s | %s символов",
            company,
            len(html_text)
        )

        llm_data = analyze_company_with_groq(
            html_text,
            company,
            "Сайт страховой"
        )

        if llm_data:

            result = {}

            for field in KASKO_FIELDS:

                result[field] = make_field_result(
                    llm_data.get(
                        field,
                        "Не найдено"
                    ),
                    3,
                    final_url
                )

            if company_has_data(
                result
            ):

                logger.info(
                    "✅ Данные получены с сайта: %s",
                    company
                )

                return result

    else:

        logger.warning(
            "⚠️ HTML слишком короткий: %s | %s символов",
            company,
            len(html_text)
        )

    # ========================================================
    # 4. ПРОВАЛ ТОЛЬКО ЭТОЙ КОМПАНИИ
    # ========================================================

    logger.error(
        "❌ НЕ УДАЛОСЬ СОБРАТЬ ДАННЫЕ: %s",
        company
    )

    return empty_company_data(
        source_url
    )


# ============================================================
# СОХРАНЕНИЕ / ЗАГРУЗКА
# ============================================================

def save_data(
    data: Dict[str, Any]
) -> bool:

    try:

        temp_file = (
            DATA_FILE + ".tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_file,
            DATA_FILE
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

        return data

    except Exception as exc:

        logger.exception(
            "❌ Ошибка загрузки данных: %s",
            exc
        )

        return {}


# ============================================================
# СБОР ВСЕХ КОМПАНИЙ
# ============================================================

def collect_all_data() -> Dict[str, Any]:

    global UPDATE_RUNNING

    if not UPDATE_LOCK.acquire(
        blocking=False
    ):

        logger.warning(
            "⚠️ Обновление уже выполняется."
        )

        return load_data()

    UPDATE_RUNNING = True

    try:

        logger.info("")
        logger.info(
            "#" * 70
        )
        logger.info(
            "🚀 НАЧИНАЕМ ПОЛНОЕ ОБНОВЛЕНИЕ"
        )
        logger.info(
            "#" * 70
        )

        companies = list(
            COMPANY_SOURCES.keys()
        )

        # ----------------------------------------------------
        # СТАРАЯ БАЗА
        # ----------------------------------------------------

        old_data = load_data()

        # ----------------------------------------------------
        # РЕЗУЛЬТАТ НАЧИНАЕМ СО СТАРОЙ БАЗЫ
        #
        # Это принципиально важно.
        #
        # Если уже есть данные по ВСК,
        # а РГС зависнет, ВСК НЕ ПРОПАДЁТ.
        # ----------------------------------------------------

        result = {}

        for key, value in old_data.items():

            if not key.startswith("_"):
                result[key] = value

        old_last_updated = old_data.get(
            "_last_updated",
            "Не обновлялось"
        )

        successful = 0
        failed = 0

        update_started = datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )

        logger.info(
            "🕐 Начало обновления: %s",
            update_started
        )

        # ----------------------------------------------------
        # ОБРАБАТЫВАЕМ КОМПАНИИ ПО ОДНОЙ
        # ----------------------------------------------------

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

                if not isinstance(
                    company_data,
                    dict
                ):

                    raise ValueError(
                        "collect_company_data "
                        "вернул не словарь"
                    )

                result[company] = company_data

                has_data = company_has_data(
                    company_data
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
                        "но новых данных не найдено: %s",
                        company
                    )

            except Exception as exc:

                failed += 1

                logger.exception(
                    "🔥 ОШИБКА КОМПАНИИ %s: %s",
                    company,
                    exc
                )

                # Если старая база существовала,
                # оставляем старые данные.
                #
                # Если не существовала —
                # создаём пустую запись.

                if company not in result:

                    result[company] = empty_company_data(
                        COMPANY_SOURCES.get(
                            company,
                            {}
                        ).get(
                            "url"
                        )
                    )

            # ------------------------------------------------
            # ПРОМЕЖУТОЧНОЕ СОХРАНЕНИЕ
            # ------------------------------------------------

            partial_result = dict(
                result
            )

            # Дата НЕ меняется до полного завершения.
            partial_result[
                "_last_updated"
            ] = old_last_updated

            partial_result[
                "_fields"
            ] = KASKO_FIELDS

            partial_result[
                "_update_status"
            ] = {
                "running": True,
                "started_at": update_started,
                "processed": index,
                "total": len(companies),
                "successful": successful,
                "failed": failed
            }

            save_data(
                partial_result
            )

            logger.info(
                "💾 Промежуточные данные сохранены: "
                "%s/%s",
                index,
                len(companies)
            )

            # ------------------------------------------------
            # Небольшая пауза между сайтами
            # ------------------------------------------------

            if index < len(companies):

                wait_time = (
                    2 +
                    random.uniform(
                        0.5,
                        1.5
                    )
                )

                logger.info(
                    "⏳ Пауза %.1f сек.",
                    wait_time
                )

                time.sleep(
                    wait_time
                )

        # ====================================================
        # ПОЛНОЕ ЗАВЕРШЕНИЕ
        # ====================================================

        final_updated = datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )

        result[
            "_last_updated"
        ] = final_updated

        result[
            "_fields"
        ] = KASKO_FIELDS

        result[
            "_update_status"
        ] = {
            "running": False,
            "started_at": update_started,
            "finished_at": final_updated,
            "processed": len(companies),
            "total": len(companies),
            "successful": successful,
            "failed": failed
        }

        save_data(
            result
        )

        logger.info("")
        logger.info(
            "#" * 70
        )
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
            "Без новых данных: %s",
            failed
        )
        logger.info(
            "Дата актуальности: %s",
            final_updated
        )
        logger.info(
            "#" * 70
        )

        return result

    except Exception as exc:

        logger.exception(
            "🔥 КРИТИЧЕСКАЯ ОШИБКА "
            "ПОЛНОГО ОБНОВЛЕНИЯ: %s",
            exc
        )

        return load_data()

    finally:

        UPDATE_RUNNING = False

        try:
            UPDATE_LOCK.release()
        except Exception:
            pass


# ============================================================
# ГЛОБАЛЬНЫЕ ДАННЫЕ
# ============================================================

INSURANCE_DATA = load_data()


# ============================================================
# ФОНОВОЕ ОБНОВЛЕНИЕ
# ============================================================

def startup_update_worker():

    global INSURANCE_DATA

    logger.info("")
    logger.info(
        "🔄 Запущен автоматический сбор данных "
        "при старте сервера."
    )

    try:

        new_data = collect_all_data()

        if isinstance(
            new_data,
            dict
        ):

            INSURANCE_DATA = new_data

            logger.info(
                "✅ Автоматический сбор завершён."
            )

        else:

            logger.error(
                "❌ Автоматический сбор "
                "вернул некорректные данные."
            )

    except Exception as exc:

        logger.exception(
            "🔥 Ошибка автоматического обновления: %s",
            exc
        )


def start_startup_update():

    if not UPDATE_ON_START:

        logger.info(
            "ℹ️ Автоматическое обновление "
            "при старте отключено."
        )

        return

    logger.info(
        "🚀 Планируем автоматическое обновление..."
    )

    thread = threading.Thread(
        target=startup_update_worker,
        name="startup-data-update",
        daemon=True
    )

    thread.start()


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

    # ВСЕГДА читаем файл заново.
    #
    # Это позволяет увидеть промежуточно
    # сохранённые данные, даже если фоновый поток
    # ещё работает.

    current_data = load_data()

    last_updated = current_data.get(
        "_last_updated",
        "Не обновлялось"
    )

    update_status = current_data.get(
        "_update_status",
        {}
    )

    return render_template(
        "index.html",
        companies=companies,
        fields=KASKO_FIELDS,
        field_labels=FIELD_LABELS,
        data=current_data,
        last_updated=last_updated,
        update_status=update_status,
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

    if not company1 or company1 not in companies:
        return redirect("/")

    if not company2 or company2 not in companies:
        return redirect("/")

    if company1 == company2:
        return redirect("/")

    # --------------------------------------------------------
    # КРИТИЧЕСКИ ВАЖНО:
    #
    # НЕ используем старый INSURANCE_DATA.
    #
    # Берём последнюю сохранённую версию файла.
    # --------------------------------------------------------

    current_data = load_data()

    raw_data1 = current_data.get(
        company1,
        {}
    )

    raw_data2 = current_data.get(
        company2,
        {}
    )

    data1 = {}
    data2 = {}

    sources_detail1 = {}
    sources_detail2 = {}

    # ========================================================
    # COMPANY 1
    # ========================================================

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

    # ========================================================
    # COMPANY 2
    # ========================================================

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

    # ========================================================
    # ДОПОЛНИТЕЛЬНЫЕ ПОЛЯ
    # ========================================================

    for data in (
        data1,
        data2
    ):

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

    data1[
        "_sources_detail"
    ] = sources_detail1

    data2[
        "_sources_detail"
    ] = sources_detail2

    source1_url = (
        COMPANY_SOURCES
        .get(
            company1,
            {}
        )
        .get(
            "url",
            "#"
        )
    )

    source2_url = (
        COMPANY_SOURCES
        .get(
            company2,
            {}
        )
        .get(
            "url",
            "#"
        )
    )

    return render_template(
        "result.html",
        company1=company1,
        company2=company2,
        data1=data1,
        data2=data2,
        sources1=[source1_url],
        sources2=[source2_url],
        fields=KASKO_FIELDS,
        field_labels=FIELD_LABELS,
        last_updated=current_data.get(
            "_last_updated",
            "Не обновлялось"
        ),
        source_info=get_source_info
    )


# ============================================================
# СТАРЫЕ URL
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

start_startup_update()


# ============================================================
# ЛОКАЛЬНЫЙ ЗАПУСК
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
