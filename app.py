# app.py — ПАРСИНГ СТРАНИЦ КАСКО + PDF + ПАМЯТЬ (УЛУЧШЕННАЯ ВЕРСИЯ)

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
from urllib.parse import quote_plus, urljoin
import io

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

# ==================== ДАННЫЕ ИЗ PDF (УРОВЕНЬ 6 — ПАМЯТЬ) ====================

KASKO_PDF_DATA = {
    "РЕСО-Гарантия": {
        "franchise": "Безусловная \\ Условно-безусловная (с 1-го или со 2-го случая). Не применяется к риску 'Хищение'.",
        "without_certificates": "Стекла без ограничений (включая стеклянную крышу и люк); 1 раз в год 1 кузовной элемент (для VIP 2 раза/год). Камеры входят в состав элемента: зеркала, крышки багажника, облицовки бампера.",
        "gap": "Отдельный риск",
        "total_loss": "75% от СС",
        "fire": "Входит",
        "terrorism": "Входит",
        "drone": "Лимит 1% СС по риску «Ущерб»",
        "tow_truck": "Лимит 1% СС",
        "repair_type": "Ремонт у официального дилера",
        "payment_terms": "5 рабочих дней",
        "advantages": "Ремонт у дилера, быстрая выплата, без учета износа, VIP-условия",
        "weak_points": "Требуется уточнение условий по телефону",
        "rating": "4.5",
        "offices": "1200+"
    },
    "ВСК": {
        "franchise": "Условно-безусловная. Может не применяться по отдельным рискам.",
        "without_certificates": "Стекла: 5% СС (неагрегатная). Прочие элементы: 3% СС (агрегатная). Панорамная крыша, стеклянная крыша и камеры не покрываются.",
        "gap": "Включен, если указан 1 период страхования (1 год). Если страховые суммы разбиты по кварталам – GAP отсутствует.",
        "total_loss": "75% от СС",
        "fire": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "terrorism": "Особые условия включения",
        "drone": "Включен при наличии в полисе GAP и отметки 'официальный дилер'",
        "tow_truck": "Петковые ТС - лимит 5 000 руб. Прочие - лимит 15 000 руб.",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия по справкам",
        "weak_points": "Камеры не оплачиваются без справок. Самовозгорание исключено.",
        "rating": "4.2",
        "offices": "800+"
    },
    "Ингосстрах": {
        "franchise": "Условная\\условно-безусловная. По каждому случаю или со 2-го случая (Авто-профи).",
        "without_certificates": "Базовый вариант: 1 раз в год – 1 из вариантов: ЛКП не более 1-й детали; остекление кузова (ИСКЛЮЧАЯ стеклянную крышу); внешние световые приборы; зеркала; антенна.",
        "gap": "Включен при отметке «Постоянная страховая сумма».",
        "total_loss": "75% от СС",
        "fire": "Входит",
        "terrorism": "За доп. плату, тариф 0,3%.",
        "drone": "Включен, но лимит 0,3%.",
        "tow_truck": "По запросу",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "10 рабочих дней",
        "advantages": "Широкая сеть офисов",
        "weak_points": "Без справок – только ЛКП 1 детали. Возможны ограничения по пробегу и СТОА.",
        "rating": "4.4",
        "offices": "900+"
    },
    "Ренессанс": {
        "franchise": "11 видов франшиз. Чаще всего: Франшиза виновника, Безусловная, Франшиза со 2-го случая.",
        "without_certificates": "Вариативно: стекла 1 раз в год \\ стекла без ограничений \\ до 5% СС 2 раза \\ до 3% СС 1 раз \\ не предусмотрено.",
        "gap": "Отдельный риск",
        "total_loss": "75% от СС",
        "fire": "Только для электромобилей",
        "terrorism": "За доп. плату, 0,5% от СС на легковые ТС",
        "drone": "За доп. плату, 0,5% от СС на легковые",
        "tow_truck": "Петковые ТС - лимит 10 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Франшиза по хищению. Эвакуация за доп. плату.",
        "rating": "4.3",
        "offices": "500+"
    },
    "АльфаСтрахование": {
        "franchise": "Условно-безусловная. Применяется к Хищению.",
        "without_certificates": "Базовый вариант: стекла без ограничений + 1 кузовной элемент 2 раза в год",
        "gap": "Включен по умолчанию",
        "total_loss": "75% от СС",
        "fire": "За доп. плату, 0,8% от СС",
        "terrorism": "За доп. плату, 0,2-0,3% от СС",
        "drone": "За доп. плату",
        "tow_truck": "Петковые ТС - лимит 5 000 руб. Прочие - лимит 10 000 руб.",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "7 рабочих дней",
        "advantages": "Без справок с бонусами",
        "weak_points": "Франшиза на Хищение, самовозгорание - за доп. плату",
        "rating": "4.6",
        "offices": "600+"
    },
    "Т-Страхование": {
        "franchise": "Условно-безусловная. Для ТС старше 5 лет - обязательные франшизы",
        "without_certificates": "Стекла: неогранич. кол-во раз – ИСКЛЮЧАЯ стеклянную крышу. Кузовные элементы: 1 раз в год - до 3% от СС",
        "gap": "Отдельный риск",
        "total_loss": "65% от СС",
        "fire": "Нет инф.",
        "terrorism": "Нет инф.",
        "drone": "Нет инф.",
        "tow_truck": "Лимит 10 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "5 рабочих дней",
        "advantages": "Онлайн-оформление, без справок",
        "weak_points": "Ниже порог тотала (65%). Обязательные франшизы.",
        "rating": "4.7",
        "offices": "онлайн"
    },
    "РГС": {
        "franchise": "Безусловная – по умолчанию. Возможны динамическая, условно-безусловная, агрегатная.",
        "without_certificates": "Стекла: неограниченное кол-во раз - ИСКЛЮЧАЯ стеклянную крышу. Кузовные элементы: 1 раз в год.",
        "gap": "Включен, если СС индексируемая. Не включен, если не индексируемая.",
        "total_loss": "75% от СС",
        "fire": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "terrorism": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "drone": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "tow_truck": "Петковые ТС - лимит 7 000 руб. Грузовые ТС - лимит 10 000 руб.",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия",
        "weak_points": "Самовозгорание и Терроризм исключены. Износ за 1-ый месяц - 7% (у РЕСО - 3%).",
        "rating": "4.1",
        "offices": "700+"
    },
    "Югория": {
        "franchise": "Условно-безусловная франшиза. При пролонгации возможна доп. франшиза.",
        "without_certificates": "Стекла: 1 раз, за исключением панорамной крыши и люка",
        "gap": "Неагрегатная - изменяющаяся",
        "total_loss": "Не указан",
        "fire": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "terrorism": "Нет инф.",
        "drone": "Входит",
        "tow_truck": "Лимит 5% от СС, но не более 15 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия пролонгации",
        "weak_points": "При пролонгации доп. франшиза. Самовозгорание исключено.",
        "rating": "3.9",
        "offices": "400+"
    },
    "СберСтрахование": {
        "franchise": "6 видов франшиз: условная, безусловная, безусловная при ДТП, динамическая, безусловная со 2-го случая, агрегатная.",
        "without_certificates": "Вариантно: 1 раз - 1 деталь кузова + стекла. Только стекла.",
        "gap": "Включен, если СС индексируемая. Не включен, если не индексируемая.",
        "total_loss": "70% от СС",
        "fire": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "terrorism": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "drone": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "tow_truck": "Петковые ТС - лимит 6 000 руб. Грузовые ТС - лимит 12 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "7 рабочих дней",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Тотал 70%. Самовозгорание и Терроризм исключены.",
        "rating": "4.0",
        "offices": "1000+"
    },
    "Согласие": {
        "franchise": "Условно-безусловная \\ динамическая",
        "without_certificates": "Стандартно: Неограниченно стекла (искл. крыша и люк) + 1 раз любой элемент",
        "gap": "В разделе 'Условия страхования' указывается как риск ГЭП",
        "total_loss": "70% от СС",
        "fire": "За доп. плату, 1.15 для ФЛ и 1.05 для ЮЛ",
        "terrorism": "За доп. плату, тариф 1.1% только для МСК и МО",
        "drone": "За доп. плату, только для МСК и МО",
        "tow_truck": "5 000 руб. (до 3,5 т). 10 000 руб. (свыше 3,5 т и за рубежом)",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия",
        "weak_points": "Тотал 70%. Эвакуатор 5 000 руб. (ниже РЕСО).",
        "rating": "4.2",
        "offices": "300+"
    },
    "Совкомбанк Страхование": {
        "franchise": "Условно-безусловная. Обязательная франшиза 25% (при не уведомлении о смене региона)",
        "without_certificates": "Только ремонт или замена ветрового стекла",
        "gap": "Нет инф.",
        "total_loss": "75% от СС",
        "fire": "Входит в группу событий №2",
        "terrorism": "ИСКЛЮЧЕНИЕ из покрытия",
        "drone": "ИСКЛЮЧЕНИЕ из покрытия",
        "tow_truck": "6 500 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Группы событий",
        "weak_points": "Терроризм исключен. Обязательная франшиза.",
        "rating": "3.8",
        "offices": "200+"
    }
}

# ==================== ПОЛЯ КАСКО ====================

KASKO_FIELDS = [
    "franchise", "without_certificates", "gap", "total_loss", "fire", "terrorism",
    "drone", "tow_truck", "repair_type", "payment_terms", "advantages",
    "weak_points", "rating", "offices"
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
    "payment_terms": "Срок выплаты",
    "advantages": "Преимущества",
    "weak_points": "Слабые места",
    "rating": "Рейтинг",
    "offices": "Офисы"
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

def fetch_url(url: str, timeout: int = 20, allow_redirects: bool = True) -> Optional[str]:
    """Загрузить URL с обходом блокировок"""
    for attempt in range(3):
        try:
            headers = get_headers()
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                verify=False,
                allow_redirects=allow_redirects
            )
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                # Пробуем другой User-Agent
                time.sleep(1)
                continue
            elif response.status_code in [301, 302]:
                # Перенаправление
                if 'Location' in response.headers:
                    new_url = response.headers['Location']
                    if not new_url.startswith('http'):
                        new_url = urljoin(url, new_url)
                    return fetch_url(new_url, timeout, allow_redirects)
        except requests.exceptions.SSLError:
            try:
                response = requests.get(
                    url,
                    headers=get_headers(),
                    timeout=timeout,
                    verify=False,
                    allow_redirects=allow_redirects
                )
                if response.status_code == 200:
                    return response.text
            except:
                pass
        except:
            pass
        time.sleep(1)
    return None

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_source_info(level: int) -> Dict:
    levels = {
        1: {"emoji": "🟢", "label": "Официальный сайт", "type": "official"},
        2: {"emoji": "🔵", "label": "Агрегатор", "type": "aggregator"},
        3: {"emoji": "🟣", "label": "Спец. агрегатор", "type": "special"},
        4: {"emoji": "🟠", "label": "Рейтинг", "type": "rating"},
        5: {"emoji": "🟡", "label": "Интернет-поиск", "type": "search"},
        6: {"emoji": "⚪", "label": "Внутренняя база", "type": "memory"},
    }
    return levels.get(level, {"emoji": "⬜", "label": "Неизвестно", "type": "unknown"})

# ==================== РАБОТА С PDF (УЛУЧШЕННАЯ) ====================

def extract_text_from_pdf(pdf_url: str) -> Optional[str]:
    """Скачать PDF и извлечь текст с обработкой разных форматов"""
    try:
        # Пробуем импортировать PyPDF2
        import PyPDF2
        
        response = requests.get(pdf_url, headers=get_headers(), timeout=30, verify=False)
        if response.status_code != 200:
            return None
        
        # Проверяем, что это действительно PDF
        content_type = response.headers.get('Content-Type', '')
        if 'pdf' not in content_type.lower() and not pdf_url.lower().endswith('.pdf'):
            # Если это не PDF, пробуем открыть как HTML
            if 'text/html' in content_type.lower():
                # Это HTML, а не PDF
                return None
        
        # Пробуем прочитать PDF
        try:
            pdf_bytes = io.BytesIO(response.content)
            reader = PyPDF2.PdfReader(pdf_bytes)
            
            # Проверяем, что PDF не пустой
            if len(reader.pages) == 0:
                return None
            
            text = ""
            for page in reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except:
                    continue
            
            if text.strip():
                return text
            else:
                return None
                
        except PyPDF2.errors.PdfReadError:
            # PDF может быть защищён или повреждён
            # Пробуем альтернативный метод (если доступен)
            try:
                # Пробуем через pypdf (новая версия)
                import pypdf
                pdf_bytes = io.BytesIO(response.content)
                reader = pypdf.PdfReader(pdf_bytes)
                text = ""
                for page in reader.pages:
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    except:
                        continue
                if text.strip():
                    return text
            except:
                pass
            
            # Если ничего не помогло, пишем в лог
            print(f"      ⚠️ Не удалось прочитать PDF (возможно защищён): {pdf_url}")
            return None
            
    except ImportError:
        print("      ⚠️ PyPDF2 не установлен")
        return None
    except Exception as e:
        print(f"      ⚠️ Ошибка PDF: {e}")
        return None

def find_pdf_links(html: str, base_url: str) -> List[str]:
    """Найти ссылки на PDF на странице"""
    soup = BeautifulSoup(html, 'html.parser')
    pdf_links = []
    
    # Ищем все ссылки
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if not href:
            continue
        
        full_url = urljoin(base_url, href)
        
        # Проверяем, что это PDF
        if '.pdf' in href.lower() or '.pdf' in full_url.lower():
            # Отфильтровываем мусор
            if not any(x in href.lower() for x in ['cookie', 'privacy', 'policy']):
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
        
        # Ищем по тексту "правила"
        text = link.get_text().lower()
        if any(x in text for x in ['правила', 'условия', 'тарифы', 'правило']):
            if full_url not in pdf_links:
                pdf_links.append(full_url)
    
    # Ищем ссылки в тексте
    for tag in soup.find_all(['div', 'p', 'li', 'td']):
        text = tag.get_text().lower()
        if '.pdf' in text:
            matches = re.findall(r'https?://[^\s<>"\']+\.pdf', text)
            for match in matches:
                if match not in pdf_links:
                    pdf_links.append(match)
    
    return pdf_links

# ==================== ПАРСИНГ СТРАНИЦЫ КАСКО + PDF ====================

def parse_kasko_page(company: str, url: str) -> Dict:
    """Парсинг страницы КАСКО + поиск и парсинг PDF"""
    print(f"  📂 Уровень 1: Страница КАСКО — {url}")
    
    result = {}
    html = fetch_url(url)
    
    if not html:
        print(f"    ⚠️ Не удалось загрузить страницу")
        return result
    
    # ---- 1. Парсим текст страницы ----
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    
    text = clean_text(soup.get_text())
    
    # Ключевые слова для поиска на странице
    field_patterns = {
        "franchise": ["франшиз", "франшиза", "безусловн", "условн"],
        "total_loss": ["тотал", "полная гибель", "гибель", "75%", "70%", "65%"],
        "gap": ["gap", "гэп", "сохранение стоимости", "gар"],
        "without_certificates": ["без справок", "без документ"],
        "fire": ["самовозгоран", "возгоран", "пожар"],
        "terrorism": ["терроризм", "терр. акт"],
        "drone": ["бпла", "беспилот", "дрон"],
        "tow_truck": ["эвакуа"],
        "repair_type": ["ремонт", "стоа", "дилер"],
        "payment_terms": ["срок выплат", "рабочих дней", "дней"]
    }
    
    for field, keywords in field_patterns.items():
        for kw in keywords:
            if kw in text.lower():
                # Ищем предложение с ключевым словом
                sentences = re.split(r'[.!?]', text)
                for sentence in sentences:
                    if kw in sentence.lower():
                        value = clean_text(sentence)
                        if len(value) > 15 and len(value) < 350:
                            # Проверяем, что это не мусор
                            if not any(x in value.lower() for x in ["войти", "регистрац", "подпис", "©"]):
                                result[field] = {
                                    "value": value,
                                    "source": {
                                        "level": 1,
                                        "name": f"Страница КАСКО {company}",
                                        "url": url,
                                        "found_at": datetime.now().isoformat()
                                    }
                                }
                                print(f"    ✅ Найдено: {FIELD_LABELS.get(field, field)}")
                                break
                    if field in result:
                        break
            if field in result:
                break
    
    # ---- 2. Ищем и парсим PDF ----
    print(f"    🔍 Ищем PDF на странице...")
    pdf_links = find_pdf_links(html, url)
    
    if pdf_links:
        print(f"    📄 Найдено PDF: {len(pdf_links)}")
        
        # Парсим каждый PDF
        pdf_fields_found = set()
        for pdf_url in pdf_links[:5]:  # Ограничиваем 5 PDF для скорости
            print(f"      📥 Загружаем PDF: {pdf_url[:80]}...")
            
            pdf_text = extract_text_from_pdf(pdf_url)
            if not pdf_text:
                continue
            
            pdf_text_lower = pdf_text.lower()
            
            # Ищем данные в PDF
            for field, keywords in field_patterns.items():
                if field in result or field in pdf_fields_found:
                    continue
                    
                for kw in keywords:
                    if kw in pdf_text_lower:
                        # Ищем предложение с ключевым словом в PDF
                        sentences = re.split(r'[.!?]', pdf_text)
                        for sentence in sentences:
                            if kw in sentence.lower():
                                value = clean_text(sentence)
                                # Проверяем, что значение не слишком длинное
                                if len(value) > 15 and len(value) < 400:
                                    result[field] = {
                                        "value": value,
                                        "source": {
                                            "level": 1,
                                            "name": f"PDF {company}",
                                            "url": pdf_url,
                                            "found_at": datetime.now().isoformat()
                                        }
                                    }
                                    pdf_fields_found.add(field)
                                    print(f"      ✅ Из PDF: {FIELD_LABELS.get(field, field)}")
                                    break
                            if field in result:
                                break
                    if field in result:
                        break
    
    print(f"    📊 Найдено: {len(result)} полей")
    return result

# ==================== УРОВЕНЬ 6: ПАМЯТЬ ====================

def get_from_memory(company: str, field: str) -> Optional[Dict]:
    if company not in KASKO_PDF_DATA:
        return None
    value = KASKO_PDF_DATA[company].get(field)
    if not value or value in ["Нет инф.", "Не указан"]:
        return None
    return {
        "value": value,
        "source": {
            "level": 6,
            "name": "Внутренняя база (PDF)",
            "url": None,
            "found_at": "2026-09-04"
        }
    }

# ==================== СБОР ДАННЫХ ====================

def collect_company_data(company: str) -> Dict:
    print(f"\n🔍 {company}")
    print("━" * 50)
    
    result = {}
    found = set()
    source_stats = {1: 0, 6: 0}
    
    # Уровень 1: Страница КАСКО + PDF
    if company in KASKO_PAGES:
        data = parse_kasko_page(company, KASKO_PAGES[company])
        for field, val in data.items():
            if field not in found:
                result[field] = val
                found.add(field)
                source_stats[1] += 1
    
    # Уровень 6: Память (заполняем пропуски)
    print(f"  📂 Уровень 6: Внутренняя база (PDF)")
    for field in KASKO_FIELDS:
        if field in found:
            continue
        memory_data = get_from_memory(company, field)
        if memory_data:
            result[field] = memory_data
            found.add(field)
            source_stats[6] += 1
            print(f"    ✅ Из памяти: {FIELD_LABELS.get(field, field)}")
    
    print(f"\n📊 {company}: собрано {len(found)}/{len(KASKO_FIELDS)} полей")
    for level, count in source_stats.items():
        if count > 0:
            info = get_source_info(level)
            print(f"  {info['emoji']} {info['label']}: {count}")
    
    return result

def collect_all_data() -> Dict:
    print("\n" + "=" * 60)
    print("📊 СБОР ДАННЫХ: КАСКО")
    print("=" * 60)
    
    all_data = {}
    for company in KASKO_PDF_DATA.keys():
        all_data[company] = collect_company_data(company)
        time.sleep(1.5)  # Задержка между компаниями
    
    all_data["_last_updated"] = datetime.now().isoformat()
    return all_data

# ==================== ЗАГРУЗКА/СОХРАНЕНИЕ ====================

DATA_FILE = "insurance_data.json"

def load_data() -> Dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📦 Загружено из кэша: {len(data) - 1} компаний")
                return data
        except Exception as e:
            print(f"⚠️ Ошибка загрузки кэша: {e}")
    
    print("🔄 Данных нет, запускаем сбор...")
    data = collect_all_data()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ==================== FLASK ====================

print("🚀 Загрузка приложения...")
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
    print("🔄 Ручное обновление...")
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
        <span class="badge">14 параметров</span>
        <span class="badge">6 уровней поиска</span>
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
        <span class="legend-item">🟢 Уровень 1 — Официальный сайт</span>
        <span class="legend-item">⚪ Уровень 6 — Внутренняя база</span>
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
                            {{ data1[field].value }}
                        {% else %}
                            {{ data1[field] }}
                        {% endif %}
                        {% if data1[field] is mapping and 'source' in data1[field] %}
                            {% set s = data1[field].source %}
                            <span class="source-icon" title="Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})">{% if s.level == 1 %}🟢{% elif s.level == 6 %}⚪{% else %}⬜{% endif %}</span>
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
                            {{ data2[field].value }}
                        {% else %}
                            {{ data2[field] }}
                        {% endif %}
                        {% if data2[field] is mapping and 'source' in data2[field] %}
                            {% set s = data2[field].source %}
                            <span class="source-icon" title="Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})">{% if s.level == 1 %}🟢{% elif s.level == 6 %}⚪{% else %}⬜{% endif %}</span>
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
