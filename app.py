# app.py — ФИНАЛЬНАЯ ВЕРСИЯ С ПРЯМЫМИ ССЫЛКАМИ НА PDF

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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "mixtral-8x7b-32768"  # вместо llama-3.1-70b-versatile

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/120.0.0.0 Safari/537.36",
]

# ==================== ПРЯМЫЕ ССЫЛКИ НА PDF И СТРАНИЦЫ С ДОКУМЕНТАМИ ====================

# Для каждой компании — либо прямая ссылка на PDF, либо страница с документами
COMPANY_SOURCES = {
    "РЕСО-Гарантия": {
        "type": "page",
        "url": "https://reso.ru/individual/auto/kasko/",
        "note": "На странице есть ссылка на PDF 'Правила страхования средств автотранспорта'"
    },
    "ВСК": {
        "type": "page",
        "url": "https://www.vsk.ru/klientam/avto/kasko/",
        "note": "Внизу страницы 'Документы' — Правила № 125.4"
    },
    "Ингосстрах": {
        "type": "page",
        "url": "https://www.ingos.ru/auto/kasko/",
        "note": "Внизу страницы 'Правила страхования автотранспортных средств'"
    },
    "Ренессанс": {
        "type": "page",
        "url": "https://www.renins.ru/auto/kasko/",
        "note": "Кнопка 'Документы' — Правила комбинированного страхования ТС"
    },
    "АльфаСтрахование": {
        "type": "page",
        "url": "https://www.alfastrah.ru/individuals/auto/kasko/",
        "note": "Внизу страницы документы с PDF"
    },
    "Согласие": {
        "type": "direct",
        "url": "https://www.soglasie.ru/individuals/avto/kasko/pravila-strakhovaniya-transportnykh-sredstv/",
        "note": "Прямая страница с правилами страхования ТС"
    },
    "РГС": {
        "type": "page",
        "url": "https://www.rgs.ru/auto/ekasko/",
        "note": "Внизу страницы 'Ключевой информационный документ (КИД)'"
    },
    "Т-Страхование": {
        "type": "page",
        "url": "https://www.tbank.ru/insurance/kasko/",
        "note": "На странице есть ссылки на PDF с правилами"
    },
    "СберСтрахование": {
        "type": "page",
        "url": "https://sberbankins.ru/products/kasko/",
        "note": "На странице есть раздел с документами"
    },
    "Югория": {
        "type": "html",
        "url": "https://ugsk.ru/auto/kasko/",
        "note": "Нет PDF, но вся информация на странице"
    },
    "Совкомбанк Страхование": {
        "type": "direct",
        "url": "https://sovcomins.ru/about/rules-and-tariffs/",
        "note": "Страница с правилами и тарифами"
    }
}

# ==================== ПОЛЯ КАСКО ====================

KASKO_FIELDS = [
    "franchise", "without_certificates", "gap", "total_loss", "fire", "terrorism",
    "drone", "tow_truck", "repair_type", "payment_terms"
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

FIELD_ANALYSIS_PROMPTS = {
    "franchise": "Найди в тексте информацию о франшизе по КАСКО. Напиши КРАТКО (2-3 предложения): какой тип франшизы (безусловная, условно-безусловная, динамическая), как она применяется, есть ли особенности. Если информации нет — напиши 'Не указано'.",
    "without_certificates": "Найди в тексте информацию об условиях выплаты без справок (без предоставления документов из ГИБДД). Напиши КРАТКО (2-3 предложения): что покрывается (стекла, кузов, ЛКП), сколько раз в год, какие ограничения. Если информации нет — напиши 'Не указано'.",
    "gap": "Найди в тексте информацию о GAP (Guaranteed Asset Protection, страхование сохранения стоимости автомобиля). Напиши КРАТКО (2-3 предложения): есть ли GAP, как он включается (отдельный риск, входит в базовый полис, за доп. плату), какие условия. Если GAP нет — напиши 'Отсутствует'. Если информации нет — напиши 'Не указано'.",
    "total_loss": "Найди в тексте информацию о пороге тотала (полной гибели автомобиля). Напиши КРАТКО (одно предложение): какой процент от страховой суммы (например, 75% от СС). Если информации нет — напиши 'Не указан'.",
    "fire": "Найди в тексте информацию о покрытии риска 'самовозгорание' или 'пожар' по КАСКО. Напиши КРАТКО (одно предложение): входит ли в покрытие, исключён, за доп. плату. Если информации нет — напиши 'Не указано'.",
    "terrorism": "Найди в тексте информацию о покрытии риска 'терроризм' по КАСКО. Напиши КРАТКО (одно предложение): входит ли в покрытие, исключён, за доп. плату, есть ли региональные ограничения (только для МСК и МО). Если информации нет — напиши 'Не указано'.",
    "drone": "Найди в тексте информацию о покрытии ущерба от БПЛА (беспилотных летательных аппаратов, дронов) по КАСКО. Напиши КРАТКО (одно предложение): входит ли в покрытие, исключён, за доп. плату, есть ли лимит. Если информации нет — напиши 'Не указано'.",
    "tow_truck": "Найди в тексте информацию об эвакуаторе по КАСКО. Напиши КРАТКО: какие лимиты (суммы) для разных типов ТС (легковые, грузовые, петковые). Если информации нет — напиши 'Не указано'.",
    "repair_type": "Найди в тексте информацию о типе ремонта по КАСКО. Напиши КРАТКО (одно предложение): ремонт у официального дилера, на СТОА страховщика, ремонт или выплата. Если информации нет — напиши 'Не указано'.",
    "payment_terms": "Найди в тексте информацию о сроке выплаты по КАСКО. Напиши КРАТКО (одно предложение): сколько рабочих дней составляет срок выплаты. Если информации нет — напиши 'Не указан'."
}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_headers() -> Dict:
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    }

def fetch_url(url: str, timeout: int = 30) -> Optional[Dict]:
    """Загрузить URL с обходом блокировок"""
    logger.info(f"  🔗 Загрузка: {url[:80]}...")
    
    for attempt in range(3):
        try:
            response = requests.get(
                url, 
                headers=get_headers(), 
                timeout=timeout, 
                verify=False, 
                allow_redirects=True
            )
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                logger.info(f"    ✅ Успешно: {len(response.content)} байт, {content_type[:40]}")
                return {
                    "success": True,
                    "content": response.content,
                    "text": response.text if 'text' in content_type else None,
                    "status_code": response.status_code,
                    "url": url
                }
            elif response.status_code == 403:
                logger.warning(f"    ⚠️ 403 (попытка {attempt+1}/3)")
                time.sleep(2)
            elif response.status_code in [301, 302, 303, 307, 308]:
                new_url = response.headers.get('Location')
                if new_url:
                    if not new_url.startswith('http'):
                        new_url = urljoin(url, new_url)
                    logger.info(f"    🔄 Редирект: {new_url[:60]}")
                    return fetch_url(new_url, timeout)
            else:
                logger.warning(f"    ⚠️ Статус {response.status_code} (попытка {attempt+1}/3)")
                time.sleep(1)
        except Exception as e:
            logger.warning(f"    ⚠️ Ошибка: {type(e).__name__} (попытка {attempt+1}/3)")
            time.sleep(1)
    
    return {"success": False, "error": "Не удалось загрузить"}

def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def get_source_info(level: int) -> Dict:
    levels = {
        1: {"emoji": "📄", "label": "PDF правила", "type": "pdf"},
        2: {"emoji": "🤖", "label": "Groq-LLM анализ", "type": "llm"},
        3: {"emoji": "🔍", "label": "HTML страница", "type": "html"},
    }
    return levels.get(level, {"emoji": "⬜", "label": "Неизвестно", "type": "unknown"})

# ==================== ПОИСК PDF НА СТРАНИЦЕ ====================

def find_pdf_links(html: str, base_url: str) -> List[str]:
    """Найти все ссылки на PDF на странице"""
    soup = BeautifulSoup(html, 'html.parser')
    pdf_links = []
    
    # 1. Обычные ссылки
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if href and '.pdf' in href.lower():
            full_url = urljoin(base_url, href)
            if full_url not in pdf_links:
                pdf_links.append(full_url)
    
    # 2. data-атрибуты
    for tag in soup.find_all():
        for attr in ['data-href', 'data-url', 'data-file', 'data-pdf']:
            val = tag.get(attr)
            if val and '.pdf' in val.lower():
                full_url = urljoin(base_url, val)
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
    
    # 3. Ссылки с текстом "правила", "условия", "документы"
    for link in soup.find_all('a', href=True):
        text = link.get_text().lower()
        if any(kw in text for kw in ['правила', 'условия', 'полис', 'тарифы', 'документ']):
            href = link.get('href', '')
            if href and ('.pdf' in href or '?download' in href or 'file=' in href):
                full_url = urljoin(base_url, href)
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
    
    if pdf_links:
        logger.info(f"    📄 Найдено PDF: {len(pdf_links)}")
    else:
        logger.warning(f"    ⚠️ PDF не найдены")
    
    return pdf_links

# ==================== ИЗВЛЕЧЕНИЕ ТЕКСТА ИЗ PDF ====================

def extract_text_from_pdf(pdf_data: bytes) -> Optional[str]:
    """Извлечь текст из PDF"""
    try:
        import PyPDF2
        logger.info(f"      📖 Извлечение текста из PDF ({len(pdf_data)} байт)")
        
        pdf_bytes = io.BytesIO(pdf_data)
        reader = PyPDF2.PdfReader(pdf_bytes)
        
        if len(reader.pages) == 0:
            logger.warning(f"      ⚠️ PDF пустой")
            return None
        
        text = ""
        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            except Exception as e:
                logger.warning(f"      ⚠️ Страница {i+1}: {str(e)[:40]}")
        
        if text.strip():
            logger.info(f"      ✅ Извлечено {len(text)} символов")
            return text
        else:
            logger.warning(f"      ⚠️ Текст не извлечён")
            return None
            
    except ImportError:
        logger.error(f"      ❌ PyPDF2 не установлен")
        return None
    except Exception as e:
        logger.error(f"      ❌ Ошибка PDF: {str(e)[:80]}")
        return None

# ==================== АНАЛИЗ PDF ЧЕРЕЗ GROQ ====================

def analyze_with_groq(text: str, field: str, company: str, source_type: str = "PDF") -> Optional[str]:
    """Отправить текст в Groq для анализа"""
    if not GROQ_API_KEY:
        logger.error(f"    ❌ GROQ_API_KEY не задан")
        return None
    
    prompt = FIELD_ANALYSIS_PROMPTS.get(field, "")
    if not prompt:
        logger.error(f"    ❌ Нет промпта для поля {field}")
        return None
    
    # Обрезаем текст
    if len(text) > 4000:
        text = text[:4000]
    
    logger.info(f"    🤖 Groq анализирует: {FIELD_LABELS.get(field, field)}")
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {
                        "role": "system", 
                        "content": "Ты — эксперт по страхованию. Анализируй текст и давай точные, краткие ответы. Если информация не найдена — пиши 'Не указано'. Отвечай только по существу, без лишней воды."
                    },
                    {
                        "role": "user",
                        "content": f"Текст ({source_type}): \n\n{text}\n\nВопрос: {prompt}\n\nОтвет:"
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 150
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            answer = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            if answer:
                logger.info(f"      ✅ Получен ответ от Groq")
                return clean_text(answer)
            else:
                logger.warning(f"      ⚠️ Пустой ответ от Groq")
                return None
        else:
            logger.error(f"      ❌ Groq ошибка {response.status_code}: {response.text[:100]}")
            return None
            
    except Exception as e:
        logger.error(f"      ❌ Ошибка Groq: {str(e)[:80]}")
        return None

# ==================== ПАРСИНГ HTML ДЛЯ ЮГОРИИ ====================

def parse_html_page(html: str, url: str) -> Dict[str, str]:
    """Парсинг HTML страницы (для Югории и других без PDF)"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Удаляем мусор
    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    
    text = clean_text(soup.get_text())
    
    # Возвращаем весь текст для анализа Groq
    return {"full_text": text}

# ==================== СБОР ДАННЫХ ДЛЯ ОДНОЙ КОМПАНИИ ====================

def collect_company_data(company: str) -> Dict:
    """Сбор данных для одной компании"""
    logger.info(f"\n🔍 {company}")
    logger.info("━" * 50)
    
    result = {}
    
    source = COMPANY_SOURCES.get(company)
    if not source:
        logger.error(f"  ❌ Нет источника для {company}")
        return {}
    
    source_type = source.get("type")
    url = source.get("url")
    
    logger.info(f"  📂 Источник: {source_type} — {url}")
    
    # ==================== ЗАГРУЖАЕМ СТРАНИЦУ ====================
    response = fetch_url(url)
    
    if not response or not response.get("success"):
        logger.error(f"  ❌ Не удалось загрузить страницу: {response.get('error') if response else 'Нет ответа'}")
        return {}
    
    html = response.get("text")
    if not html:
        logger.error(f"  ❌ Нет HTML")
        return {}
    
    # ==================== ЕСЛИ ИСТОЧНИК — HTML (Югория) ====================
    if source_type == "html":
        logger.info(f"  🔍 Парсим HTML страницу (без PDF)")
        parsed = parse_html_page(html, url)
        text = parsed.get("full_text", "")
        
        if not text:
            logger.error(f"  ❌ Не удалось извлечь текст из HTML")
            return {}
        
        # Анализируем через Groq
        for field in KASKO_FIELDS:
            answer = analyze_with_groq(text, field, company, "HTML страница")
            if answer:
                result[field] = {
                    "value": answer,
                    "source": {
                        "level": 3,
                        "name": f"HTML страница {company}",
                        "url": url,
                        "found_at": datetime.now().isoformat()
                    }
                }
                logger.info(f"    ✅ {FIELD_LABELS.get(field, field)}: {answer[:80]}...")
            else:
                result[field] = {
                    "value": "Не найдено",
                    "source": {
                        "level": 0,
                        "name": "Информация не найдена",
                        "url": None,
                        "found_at": datetime.now().isoformat()
                    }
                }
                logger.warning(f"    ❌ Не найдено: {FIELD_LABELS.get(field, field)}")
        
        return result
    
    # ==================== ЕСЛИ ИСТОЧНИК — СТРАНИЦА С ДОКУМЕНТАМИ ====================
    # Ищем PDF на странице
    pdf_links = find_pdf_links(html, url)
    
    if not pdf_links:
        logger.error(f"  ❌ PDF не найдены на странице")
        return {}
    
    # Пробуем каждый PDF
    pdf_text = None
    for pdf_url in pdf_links[:5]:
        if any(x in pdf_url.lower() for x in ['cookie', 'privacy', 'policy', 'logo']):
            continue
        
        logger.info(f"  📥 Загрузка PDF: {pdf_url[:80]}...")
        pdf_response = fetch_url(pdf_url, timeout=45)
        
        if not pdf_response or not pdf_response.get("success"):
            continue
        
        pdf_data = pdf_response.get("content")
        if not pdf_data:
            continue
        
        extracted = extract_text_from_pdf(pdf_data)
        if extracted:
            pdf_text = extracted
            logger.info(f"  ✅ PDF загружен и прочитан")
            break
    
    if not pdf_text:
        logger.error(f"  ❌ Не удалось прочитать ни один PDF")
        return {}
    
    # ==================== АНАЛИЗ PDF ЧЕРЕЗ GROQ ====================
    logger.info(f"  🤖 Анализ PDF через Groq-LLM")
    
    for field in KASKO_FIELDS:
        answer = analyze_with_groq(pdf_text, field, company, "PDF")
        if answer:
            result[field] = {
                "value": answer,
                "source": {
                    "level": 2,
                    "name": f"Groq-LLM (PDF {company})",
                    "url": pdf_links[0] if pdf_links else None,
                    "found_at": datetime.now().isoformat()
                }
            }
            logger.info(f"    ✅ {FIELD_LABELS.get(field, field)}: {answer[:80]}...")
        else:
            result[field] = {
                "value": "Не найдено",
                "source": {
                    "level": 0,
                    "name": "Информация не найдена",
                    "url": None,
                    "found_at": datetime.now().isoformat()
                }
            }
            logger.warning(f"    ❌ Не найдено: {FIELD_LABELS.get(field, field)}")
    
    return result

def collect_all_data() -> Dict:
    """Сбор данных для всех компаний"""
    logger.info("\n" + "=" * 60)
    logger.info("📊 СБОР ДАННЫХ: КАСКО (PDF + Groq-LLM)")
    logger.info("=" * 60)
    logger.info(f"Компаний: {len(COMPANY_SOURCES)}")
    logger.info(f"Поля: {len(KASKO_FIELDS)}")
    logger.info(f"Модель: {GROQ_MODEL}")
    if GROQ_API_KEY:
        logger.info(f"✅ Groq API Key: задан")
    else:
        logger.error(f"❌ Groq API Key: НЕ ЗАДАН!")
    logger.info("=" * 60)
    
    all_data = {}
    for company in COMPANY_SOURCES.keys():
        all_data[company] = collect_company_data(company)
        time.sleep(1)
    
    all_data["_last_updated"] = datetime.now().isoformat()
    all_data["_fields"] = KASKO_FIELDS
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ СБОР ЗАВЕРШЁН")
    logger.info("=" * 60)
    
    return all_data

# ==================== ЗАГРУЗКА/СОХРАНЕНИЕ ====================

DATA_FILE = "insurance_data.json"

def load_data() -> Dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"📦 Загружено из кэша: {len(data) - 1} компаний")
                return data
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки кэша: {e}")
    
    logger.info("🔄 Кэша нет, запускаем сбор...")
    data = collect_all_data()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ==================== FLASK ====================

logger.info("🚀 Загрузка приложения...")
INSURANCE_DATA = load_data()
ALL_COMPANIES = [c for c in INSURANCE_DATA.keys() if not c.startswith("_")]

@app.route('/')
def index():
    last_updated = INSURANCE_DATA.get("_last_updated", "неизвестно")
    return render_template('index.html',
                         companies=ALL_COMPANIES,
                         last_updated=last_updated[:16] if last_updated != "неизвестно" else "неизвестно")

@app.route('/compare', methods=['POST'])
def compare():
    c1 = request.form.get('company1')
    c2 = request.form.get('company2')
    
    if not c1 or not c2:
        return "❌ Выберите обе компании! <a href='/'>Назад</a>"
    
    if c1 == c2:
        return "❌ Выберите разные компании! <a href='/'>Назад</a>"
    
    data1 = INSURANCE_DATA.get(c1, {})
    data2 = INSURANCE_DATA.get(c2, {})
    
    return render_template('result.html',
                         company1=c1,
                         company2=c2,
                         data1=data1,
                         data2=data2,
                         fields=KASKO_FIELDS,
                         field_labels=FIELD_LABELS,
                         timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

@app.route('/update')
def update():
    global INSURANCE_DATA, ALL_COMPANIES
    logger.info("🔄 Ручное обновление...")
    INSURANCE_DATA = collect_all_data()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(INSURANCE_DATA, f, ensure_ascii=False, indent=2)
    ALL_COMPANIES = [c for c in INSURANCE_DATA.keys() if not c.startswith("_")]
    return "✅ Данные обновлены! <a href='/'>На главную</a>"

@app.route('/login')
@app.route('/register')
@app.route('/logout')
@app.route('/payment')
def old_routes():
    return redirect('/')

# ==================== ШАБЛОНЫ ====================

os.makedirs('templates', exist_ok=True)

with open('templates/index.html', 'w', encoding='utf-8') as f:
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
        <span class="badge">🤖 Groq-LLM</span>
    </div>
</div>
</body>
</html>
''')

with open('templates/result.html', 'w', encoding='utf-8') as f:
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
        .source-icon { display: inline-block; font-size: 14px; margin-right: 4px; cursor: help; }
        .source-tooltip { display: none; font-size: 11px; color: #6b7280; margin-top: 2px; }
        .value:hover .source-tooltip { display: block; }
        .legend { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0 16px; padding: 14px; background: #f8fafc; border-radius: 10px; font-size: 13px; }
        .legend-item { display: flex; align-items: center; gap: 4px; }
        .btn { display: inline-block; padding: 10px 24px; background: #2563eb; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px; transition: background 0.2s; }
        .btn:hover { background: #1d4ed8; }
        .btn-secondary { background: #6b7280; }
        .btn-secondary:hover { background: #4b5563; }
        .actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
        .footer { margin-top: 20px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #f3f4f6; padding-top: 16px; }
        .missing { color: #9ca3af; font-style: italic; }
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
        <span class="legend-item">📄 Уровень 1 — PDF правила</span>
        <span class="legend-item">🤖 Уровень 2 — Groq-LLM анализ</span>
        <span class="legend-item">🔍 Уровень 3 — HTML страница</span>
        <span class="legend-item">⬜ Информация не найдена</span>
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
                    {% if field in data1 and data1[field] %}
                        {% if data1[field] is mapping and 'value' in data1[field] %}
                            {% if data1[field].value == 'Не найдено' %}
                                <span class="not-found">{{ data1[field].value }}</span>
                            {% else %}
                                {{ data1[field].value }}
                            {% endif %}
                        {% else %}
                            {{ data1[field] }}
                        {% endif %}
                        {% if data1[field] is mapping and 'source' in data1[field] %}
                            {% set s = data1[field].source %}
                            <span class="source-icon" title="Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})">{% if s.level == 1 %}📄{% elif s.level == 2 %}🤖{% elif s.level == 3 %}🔍{% else %}⬜{% endif %}</span>
                            <div class="source-tooltip">
                                Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})
                                {% if s.url %}<br><span class="source-url"><a href="{{ s.url }}" target="_blank">{{ s.url }}</a></span>{% endif %}
                            </div>
                        {% endif %}
                    {% else %}
                        <span class="missing">—</span>
                    {% endif %}
                </td>
                <td class="value">
                    {% if field in data2 and data2[field] %}
                        {% if data2[field] is mapping and 'value' in data2[field] %}
                            {% if data2[field].value == 'Не найдено' %}
                                <span class="not-found">{{ data2[field].value }}</span>
                            {% else %}
                                {{ data2[field].value }}
                            {% endif %}
                        {% else %}
                            {{ data2[field] }}
                        {% endif %}
                        {% if data2[field] is mapping and 'source' in data2[field] %}
                            {% set s = data2[field].source %}
                            <span class="source-icon" title="Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})">{% if s.level == 1 %}📄{% elif s.level == 2 %}🤖{% elif s.level == 3 %}🔍{% else %}⬜{% endif %}</span>
                            <div class="source-tooltip">
                                Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})
                                {% if s.url %}<br><span class="source-url"><a href="{{ s.url }}" target="_blank">{{ s.url }}</a></span>{% endif %}
                            </div>
                        {% endif %}
                    {% else %}
                        <span class="missing">—</span>
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
        Обновлено: {{ timestamp }}
    </div>
</div>
</body>
</html>
''')

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
