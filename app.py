# app.py — ФИНАЛЬНАЯ ВЕРСИЯ С ЛОГИРОВАНИЕМ И АНАЛИЗОМ

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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]

# ==================== УРЛЫ СТРАНИЦ КАСКО ====================

KASKO_PAGES = {
    "РЕСО-Гарантия": "https://reso.ru/individual/auto/kasko/",
    "ВСК": "https://www.vsk.ru/klientam/avto/kasko/",
    "Ингосстрах": "https://www.ingos.ru/auto/kasko/",
    "Ренессанс": "https://www.renins.ru/auto/kasko/",
    "АльфаСтрахование": "https://www.alfastrah.ru/individuals/auto/kasko/",
    "Согласие": "https://www.soglasie.ru/individuals/avto/kasko/",
    "РГС": "https://www.rgs.ru/auto/ekasko/",
    "Т-Страхование": "https://www.tbank.ru/insurance/kasko/",
    "СберСтрахование": "https://sberbankins.ru/products/kasko/",
    "Югория": "https://ugsk.ru/auto/kasko/",
    "Совкомбанк Страхование": "https://sovcomins.ru/product/kasko/"
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

# ==================== КОНФИГУРАЦИЯ ПОЛЕЙ ДЛЯ АНАЛИЗА ====================

FIELD_CONFIG = {
    "franchise": {
        "keywords": ["франшиз", "франшиза", "безусловн", "условн"],
        "exclude": ["отзыв", "рейтинг", "звезд"],
        "format": "text",
        "max_length": 300
    },
    "without_certificates": {
        "keywords": ["без справок", "без документ", "без предоставления", "лкп"],
        "exclude": ["отзыв", "рейтинг"],
        "format": "text",
        "max_length": 350
    },
    "gap": {
        "keywords": ["gap", "гэп", "сохранение стоимости", "дополнительные расходы"],
        "exclude": [],
        "format": "status",
        "statuses": {
            "present": "Есть",
            "absent": "ИСКЛЮЧЕНИЕ из страхового покрытия",
            "paid": "За доп. плату",
            "unknown": "Не указан"
        }
    },
    "total_loss": {
        "keywords": ["тотал", "полная гибель", "гибель", "конструктивн"],
        "exclude": [],
        "format": "percent",
        "pattern": r'(\d{2,3})\s*%'
    },
    "fire": {
        "keywords": ["самовозгоран", "возгоран", "пожар"],
        "exclude": ["отзыв", "рейтинг"],
        "format": "status",
        "statuses": {
            "present": "Входит",
            "absent": "ИСКЛЮЧЕНИЕ из страхового покрытия",
            "paid": "За доп. плату",
            "unknown": "Не указан"
        }
    },
    "terrorism": {
        "keywords": ["терроризм", "терр. акт", "теракт"],
        "exclude": [],
        "format": "status",
        "statuses": {
            "present": "Входит",
            "absent": "ИСКЛЮЧЕНИЕ из страхового покрытия",
            "paid": "За доп. плату",
            "regional": "За доп. плату, только для МСК и МО",
            "unknown": "Не указан"
        }
    },
    "drone": {
        "keywords": ["бпла", "беспилот", "дрон"],
        "exclude": [],
        "format": "status_with_limit",
        "statuses": {
            "present": "Входит",
            "absent": "ИСКЛЮЧЕНИЕ из страхового покрытия",
            "paid": "За доп. плату",
            "limit": "Лимит {value}",
            "unknown": "Не указан"
        }
    },
    "tow_truck": {
        "keywords": ["эвакуа", "эвакуатор"],
        "exclude": [],
        "format": "list",
        "patterns": [
            r'(петков.*?)\s*[-–]\s*(\d{1,3}\s*[\d\s]*руб)',
            r'(легков.*?)\s*[-–]\s*(\d{1,3}\s*[\d\s]*руб)',
            r'(грузов.*?)\s*[-–]\s*(\d{1,3}\s*[\d\s]*руб)',
            r'(\d{1,3}\s*[\d\s]*руб)'
        ]
    },
    "repair_type": {
        "keywords": ["ремонт", "стоа", "дилер", "сто"],
        "exclude": ["отзыв", "рейтинг"],
        "format": "text",
        "max_length": 150
    },
    "payment_terms": {
        "keywords": ["срок выплат", "рабочих дней", "дней"],
        "exclude": [],
        "format": "text",
        "max_length": 100
    }
}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_headers() -> Dict:
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

def fetch_url(url: str, timeout: int = 30, max_retries: int = 3) -> Optional[Dict]:
    """
    Загрузить URL с обходом блокировок.
    Возвращает словарь с результатом и метаданными.
    """
    logger.info(f"  🔗 Загрузка: {url[:80]}...")
    
    for attempt in range(max_retries):
        try:
            headers = get_headers()
            response = requests.get(
                url, 
                headers=headers, 
                timeout=timeout, 
                verify=False, 
                allow_redirects=True,
                stream=True
            )
            
            # Проверяем статус
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                content_length = len(response.content)
                logger.info(f"    ✅ Успешно загружено: {content_length} байт, тип: {content_type[:50]}")
                return {
                    "success": True,
                    "content": response.content,
                    "text": response.text if 'text' in content_type else None,
                    "headers": dict(response.headers),
                    "status_code": response.status_code,
                    "url": url,
                    "attempts": attempt + 1
                }
            elif response.status_code == 403:
                logger.warning(f"    ⚠️ 403 Forbidden (попытка {attempt+1}/{max_retries})")
                time.sleep(2 * (attempt + 1))
            elif response.status_code in [301, 302, 303, 307, 308]:
                new_url = response.headers.get('Location')
                if new_url:
                    if not new_url.startswith('http'):
                        new_url = urljoin(url, new_url)
                    logger.info(f"    🔄 Редирект: {new_url[:80]}")
                    return fetch_url(new_url, timeout, max_retries)
                else:
                    logger.warning(f"    ⚠️ Редирект без Location")
                    return {"success": False, "error": "Редирект без Location", "status_code": response.status_code}
            elif response.status_code == 404:
                logger.warning(f"    ❌ 404 Not Found")
                return {"success": False, "error": "404 Not Found", "status_code": 404}
            elif response.status_code == 503:
                logger.warning(f"    ⚠️ 503 Service Unavailable (попытка {attempt+1}/{max_retries})")
                time.sleep(3 * (attempt + 1))
            else:
                logger.warning(f"    ⚠️ Статус {response.status_code} (попытка {attempt+1}/{max_retries})")
                time.sleep(1)
                
        except requests.exceptions.SSLError as e:
            logger.warning(f"    ⚠️ SSL ошибка (попытка {attempt+1}/{max_retries}): {str(e)[:50]}")
            time.sleep(1)
            
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"    ⚠️ Ошибка соединения (попытка {attempt+1}/{max_retries}): {str(e)[:50]}")
            time.sleep(2 * (attempt + 1))
            
        except requests.exceptions.Timeout as e:
            logger.warning(f"    ⚠️ Таймаут (попытка {attempt+1}/{max_retries}): {str(e)[:30]}")
            time.sleep(2 * (attempt + 1))
            
        except Exception as e:
            logger.warning(f"    ⚠️ Ошибка (попытка {attempt+1}/{max_retries}): {type(e).__name__}: {str(e)[:50]}")
            time.sleep(1)
    
    return {"success": False, "error": "Не удалось загрузить после всех попыток"}

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_source_info(level: int) -> Dict:
    levels = {
        1: {"emoji": "📄", "label": "PDF правила", "type": "pdf"},
        2: {"emoji": "🟡", "label": "Интернет-поиск", "type": "search"},
        3: {"emoji": "🔍", "label": "HTML страница", "type": "html"},
        4: {"emoji": "⚪", "label": "Внутренняя база", "type": "memory"},
    }
    return levels.get(level, {"emoji": "⬜", "label": "Неизвестно", "type": "unknown"})

# ==================== ПОИСК PDF НА СТРАНИЦЕ ====================

def find_pdf_links(html: str, base_url: str) -> List[str]:
    """Найти все ссылки на PDF на странице"""
    soup = BeautifulSoup(html, 'html.parser')
    pdf_links = []
    found_by = []
    
    # 1. Обычные ссылки
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if href and '.pdf' in href.lower():
            full_url = urljoin(base_url, href)
            if full_url not in pdf_links:
                pdf_links.append(full_url)
                found_by.append("href")
    
    # 2. data-атрибуты
    for tag in soup.find_all():
        for attr in ['data-href', 'data-url', 'data-file', 'data-pdf', 'data-src']:
            val = tag.get(attr)
            if val and '.pdf' in val.lower():
                full_url = urljoin(base_url, val)
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
                    found_by.append("data-attr")
    
    # 3. onclick
    for tag in soup.find_all(attrs={'onclick': True}):
        onclick = tag.get('onclick', '')
        match = re.search(r"['\"]([^'\"]+\.pdf)['\"]", onclick)
        if match:
            full_url = urljoin(base_url, match.group(1))
            if full_url not in pdf_links:
                pdf_links.append(full_url)
                found_by.append("onclick")
    
    # 4. Текст внутри тегов
    for tag in soup.find_all(['p', 'div', 'li', 'td', 'span']):
        text = tag.get_text()
        if '.pdf' in text.lower():
            match = re.search(r'https?://[^\s<>"\']+\.pdf', text)
            if match:
                full_url = match.group(0)
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
                    found_by.append("text")
    
    # 5. Ссылки с текстом "правила", "условия"
    for link in soup.find_all('a', href=True):
        text = link.get_text().lower()
        href = link.get('href', '').lower()
        if any(kw in text for kw in ['правила', 'условия', 'полис', 'тарифы']):
            if href and ('.pdf' in href or '?download' in href or 'file=' in href):
                full_url = urljoin(base_url, link.get('href'))
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
                    found_by.append("rules_link")
    
    # Логируем результаты
    if pdf_links:
        logger.info(f"    📄 Найдено {len(pdf_links)} PDF (способы: {', '.join(set(found_by))})")
    else:
        logger.warning(f"    ⚠️ PDF не найдены")
    
    return pdf_links

# ==================== ЧТЕНИЕ PDF ====================

def extract_text_from_pdf(pdf_data: bytes) -> Optional[str]:
    """Извлечь текст из PDF (пробуем разные библиотеки)"""
    logger.info(f"      📖 Извлечение текста из PDF ({len(pdf_data)} байт)")
    
    # Пробуем PyPDF2
    try:
        import PyPDF2
        logger.info(f"      🔧 Пробуем PyPDF2...")
        pdf_bytes = io.BytesIO(pdf_data)
        reader = PyPDF2.PdfReader(pdf_bytes)
        
        if len(reader.pages) == 0:
            logger.warning(f"      ⚠️ PDF пустой (0 страниц)")
            return None
        
        text = ""
        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            except Exception as e:
                logger.warning(f"      ⚠️ Ошибка на странице {i+1}: {str(e)[:50]}")
        
        if text.strip():
            logger.info(f"      ✅ PyPDF2: извлечено {len(text)} символов")
            return text
        else:
            logger.warning(f"      ⚠️ PyPDF2: текст не извлечён")
    except ImportError:
        logger.warning(f"      ⚠️ PyPDF2 не установлен")
    except Exception as e:
        logger.warning(f"      ⚠️ PyPDF2 ошибка: {str(e)[:80]}")
    
    # Пробуем pypdf
    try:
        import pypdf
        logger.info(f"      🔧 Пробуем pypdf...")
        pdf_bytes = io.BytesIO(pdf_data)
        reader = pypdf.PdfReader(pdf_bytes)
        
        if len(reader.pages) == 0:
            logger.warning(f"      ⚠️ PDF пустой (0 страниц)")
            return None
        
        text = ""
        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            except Exception as e:
                logger.warning(f"      ⚠️ Ошибка на странице {i+1}: {str(e)[:50]}")
        
        if text.strip():
            logger.info(f"      ✅ pypdf: извлечено {len(text)} символов")
            return text
        else:
            logger.warning(f"      ⚠️ pypdf: текст не извлечён")
    except ImportError:
        logger.warning(f"      ⚠️ pypdf не установлен")
    except Exception as e:
        logger.warning(f"      ⚠️ pypdf ошибка: {str(e)[:80]}")
    
    logger.error(f"      ❌ Не удалось извлечь текст из PDF (попробованы все библиотеки)")
    return None

# ==================== АНАЛИЗ ТЕКСТА ДЛЯ ПОЛЯ ====================

def analyze_field(text: str, field: str) -> Dict:
    """
    Анализирует текст и возвращает структурированный ответ для поля
    """
    if not text:
        return {"value": "Не найдено", "status": "unknown", "details": "Информация не найдена"}
    
    text_lower = text.lower()
    config = FIELD_CONFIG.get(field, {})
    keywords = config.get("keywords", [])
    exclude = config.get("exclude", [])
    
    # Проверяем, есть ли ключевые слова
    found_keyword = None
    for kw in keywords:
        if kw in text_lower:
            found_keyword = kw
            break
    
    if not found_keyword:
        return {"value": "Не найдено", "status": "unknown", "details": "Ключевые слова не найдены"}
    
    # Ищем предложение с ключевым словом
    sentences = re.split(r'[.!?]', text)
    best_sentence = None
    for sentence in sentences:
        if found_keyword in sentence.lower():
            # Проверяем на исключения
            if exclude:
                if any(x in sentence.lower() for x in exclude):
                    continue
            best_sentence = clean_text(sentence)
            break
    
    if not best_sentence:
        return {"value": "Не найдено", "status": "unknown", "details": "Подходящее предложение не найдено"}
    
    # Ограничиваем длину
    max_length = config.get("max_length", 300)
    if len(best_sentence) > max_length:
        best_sentence = best_sentence[:max_length] + "..."
    
    # Анализируем в зависимости от формата
    field_format = config.get("format", "text")
    
    if field_format == "text":
        return {
            "value": best_sentence,
            "status": "present",
            "details": "Найдено в тексте"
        }
    
    elif field_format == "status":
        statuses = config.get("statuses", {})
        
        # Определяем статус
        if "исключ" in text_lower or "не входит" in text_lower:
            status = "absent"
        elif "за доп. плату" in text_lower:
            status = "paid"
        elif "мск" in text_lower and "мо" in text_lower:
            status = "regional"
        else:
            status = "present"
        
        return {
            "value": statuses.get(status, best_sentence),
            "status": status,
            "details": f"Статус: {status}"
        }
    
    elif field_format == "percent":
        pattern = config.get("pattern", r'(\d{2,3})\s*%')
        match = re.search(pattern, best_sentence)
        if match:
            percent = match.group(1)
            return {
                "value": f"{percent}% от СС",
                "status": "present",
                "details": f"Порог тотала: {percent}%"
            }
        else:
            return {
                "value": best_sentence,
                "status": "unknown",
                "details": "Процент не найден"
            }
    
    elif field_format == "list":
        # Ищем суммы
        patterns = config.get("patterns", [])
        found_values = []
        for pattern in patterns:
            matches = re.findall(pattern, best_sentence, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    found_values.append(" ".join(match))
                else:
                    found_values.append(match)
        
        if found_values:
            return {
                "value": "; ".join(found_values[:3]),
                "status": "present",
                "details": f"Найдено {len(found_values)} значений"
            }
        else:
            return {
                "value": best_sentence,
                "status": "present",
                "details": "Суммы не найдены"
            }
    
    elif field_format == "status_with_limit":
        # Ищем лимит
        limit_pattern = r'(\d{1,3}\s*%)\s*от\s*СС'
        match = re.search(limit_pattern, text_lower)
        if match:
            limit = match.group(1)
            return {
                "value": f"Лимит {limit} от СС",
                "status": "limit",
                "details": f"Лимит: {limit} от СС"
            }
        
        # Ищем статус
        if "исключ" in text_lower:
            return {
                "value": "ИСКЛЮЧЕНИЕ из страхового покрытия",
                "status": "absent",
                "details": "Исключён из покрытия"
            }
        elif "за доп. плату" in text_lower:
            return {
                "value": "За доп. плату",
                "status": "paid",
                "details": "Добавляется за отдельную плату"
            }
        elif "входит" in text_lower:
            return {
                "value": "Входит",
                "status": "present",
                "details": "Включён в покрытие"
            }
        else:
            return {
                "value": best_sentence,
                "status": "unknown",
                "details": "Статус не определён"
            }
    
    # По умолчанию
    return {
        "value": best_sentence,
        "status": "present",
        "details": "Найдено в тексте"
    }

# ==================== СБОР ДАННЫХ ДЛЯ ОДНОЙ КОМПАНИИ ====================

def collect_company_data(company: str) -> Dict:
    """Сбор данных для одной компании"""
    logger.info(f"\n🔍 {company}")
    logger.info("━" * 50)
    
    result = {}
    found = set()
    source_stats = {}
    
    url = KASKO_PAGES.get(company)
    if not url:
        logger.error(f"  ❌ Нет URL для {company}")
        return {}
    
    # ==================== УРОВЕНЬ 1: PDF со страницы ====================
    logger.info(f"  📂 Уровень 1: Поиск PDF на странице КАСКО")
    logger.info(f"  🔗 {url}")
    
    response = fetch_url(url)
    
    if not response or not response.get("success"):
        error = response.get("error", "Неизвестная ошибка") if response else "Нет ответа"
        logger.error(f"  ❌ Не удалось загрузить страницу: {error}")
        # Переходим к следующему уровню
    else:
        html = response.get("text")
        if html:
            pdf_links = find_pdf_links(html, url)
            
            if pdf_links:
                logger.info(f"    📄 Найдено PDF: {len(pdf_links)}")
                
                for pdf_url in pdf_links[:10]:
                    # Фильтруем мусор
                    if any(x in pdf_url.lower() for x in ['cookie', 'privacy', 'policy', 'logo', 'icon']):
                        logger.info(f"      ⏭️ Пропускаем: {pdf_url[:60]} (мусор)")
                        continue
                    
                    logger.info(f"      📥 Загружаем PDF: {pdf_url[:80]}...")
                    pdf_response = fetch_url(pdf_url, timeout=45)
                    
                    if not pdf_response or not pdf_response.get("success"):
                        logger.warning(f"      ⚠️ Не удалось загрузить PDF: {pdf_response.get('error', 'Неизвестно') if pdf_response else 'Нет ответа'}")
                        continue
                    
                    pdf_data = pdf_response.get("content")
                    if not pdf_data:
                        logger.warning(f"      ⚠️ PDF пустой")
                        continue
                    
                    pdf_text = extract_text_from_pdf(pdf_data)
                    if not pdf_text:
                        logger.warning(f"      ⚠️ Не удалось извлечь текст из PDF")
                        continue
                    
                    # Анализируем каждое поле в этом PDF
                    pdf_fields_found = 0
                    for field in KASKO_FIELDS:
                        if field in found:
                            continue
                        
                        analysis = analyze_field(pdf_text, field)
                        if analysis.get("status") != "unknown" and analysis.get("value") != "Не найдено":
                            result[field] = {
                                "value": analysis.get("value"),
                                "status": analysis.get("status"),
                                "details": analysis.get("details"),
                                "source": {
                                    "level": 1,
                                    "name": f"PDF {company}",
                                    "url": pdf_url,
                                    "found_at": datetime.now().isoformat()
                                }
                            }
                            found.add(field)
                            pdf_fields_found += 1
                            logger.info(f"      ✅ Из PDF: {FIELD_LABELS.get(field, field)} → {analysis.get('value')[:80]}...")
                    
                    if pdf_fields_found > 0:
                        source_stats[1] = source_stats.get(1, 0) + pdf_fields_found
                    
                    # Если нашли все поля — выходим
                    if len(found) >= len(KASKO_FIELDS):
                        logger.info(f"    ✅ Найдены все поля!")
                        break
            else:
                logger.warning(f"    ⚠️ PDF не найдены на странице")
        else:
            logger.warning(f"    ⚠️ Нет HTML для парсинга")
    
    # ==================== УРОВЕНЬ 2: Интернет-поиск ====================
    missing_fields = [f for f in KASKO_FIELDS if f not in found]
    if missing_fields:
        logger.info(f"  📂 Уровень 2: Интернет-поиск (не хватает {len(missing_fields)} полей)")
        for field in missing_fields:
            query = f"КАСКО {company} {FIELD_LABELS.get(field, field)}"
            logger.info(f"    🔍 Поиск: '{query}'")
            
            # Пробуем Яндекс
            search_url = f"https://yandex.ru/search/?text={quote_plus(query)}&lr=213"
            search_response = fetch_url(search_url, timeout=15)
            
            if not search_response or not search_response.get("success"):
                logger.warning(f"    ⚠️ Яндекс не отвечает: {search_response.get('error') if search_response else 'Нет ответа'}")
                continue
            
            search_html = search_response.get("text")
            if not search_html:
                continue
            
            # Ищем результаты
            soup = BeautifulSoup(search_html, 'html.parser')
            found_in_search = False
            
            for item in soup.find_all(['li', 'div'], class_=re.compile(r'result|serp-item|organic')):
                link_tag = item.find('a')
                if not link_tag:
                    continue
                
                href = link_tag.get('href', '')
                if href.startswith('/'):
                    href = f"https://yandex.ru{href}"
                
                if not href.startswith('http'):
                    continue
                
                # Загружаем страницу результата
                logger.info(f"      📖 Читаем: {href[:60]}...")
                page_response = fetch_url(href, timeout=15)
                
                if not page_response or not page_response.get("success"):
                    continue
                
                page_text = page_response.get("text")
                if not page_text:
                    continue
                
                # Анализируем поле
                analysis = analyze_field(page_text, field)
                if analysis.get("status") != "unknown" and analysis.get("value") != "Не найдено":
                    result[field] = {
                        "value": analysis.get("value"),
                        "status": analysis.get("status"),
                        "details": analysis.get("details"),
                        "source": {
                            "level": 2,
                            "name": "Интернет-поиск (Яндекс)",
                            "url": href,
                            "found_at": datetime.now().isoformat()
                        }
                    }
                    found.add(field)
                    source_stats[2] = source_stats.get(2, 0) + 1
                    logger.info(f"      ✅ Найдено: {FIELD_LABELS.get(field, field)} → {analysis.get('value')[:80]}...")
                    found_in_search = True
                    break
            
            if not found_in_search:
                logger.warning(f"    ❌ Не найдено: {FIELD_LABELS.get(field, field)}")
    
    # ==================== ИТОГ ====================
    logger.info(f"\n📊 {company}: собрано {len(found)}/{len(KASKO_FIELDS)} полей")
    for level, count in source_stats.items():
        info = get_source_info(level)
        logger.info(f"  {info['emoji']} {info['label']}: {count}")
    
    # Для полей, которые не найдены — ставим "Не найдено"
    for field in KASKO_FIELDS:
        if field not in result:
            result[field] = {
                "value": "Не найдено",
                "status": "unknown",
                "details": "Информация не найдена ни в одном источнике",
                "source": {
                    "level": 0,
                    "name": "Не найдено",
                    "url": None,
                    "found_at": datetime.now().isoformat()
                }
            }
    
    return result

def collect_all_data() -> Dict:
    """Сбор данных для всех компаний"""
    logger.info("\n" + "=" * 60)
    logger.info("📊 СБОР ДАННЫХ: КАСКО")
    logger.info("=" * 60)
    logger.info(f"Компаний: {len(KASKO_PAGES)}")
    logger.info(f"Поля: {len(KASKO_FIELDS)}")
    logger.info("=" * 60)
    
    all_data = {}
    for company in KASKO_PAGES.keys():
        all_data[company] = collect_company_data(company)
        time.sleep(2)
    
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
    
    logger.info("🔄 Данных нет, запускаем сбор...")
    data = collect_all_data()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ==================== FLASK ====================

print("🚀 Загрузка приложения...")
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

# index.html
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
        <span class="badge">PDF + Поиск</span>
    </div>
</div>
</body>
</html>
''')

# result.html
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
        <span class="legend-item">🟡 Уровень 2 — Интернет-поиск</span>
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
                            <span class="source-icon" title="Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})">{% if s.level == 1 %}📄{% elif s.level == 2 %}🟡{% else %}⬜{% endif %}</span>
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
                            <span class="source-icon" title="Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})">{% if s.level == 1 %}📄{% elif s.level == 2 %}🟡{% else %}⬜{% endif %}</span>
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
