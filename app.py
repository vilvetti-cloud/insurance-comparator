# app.py — PDF + ИНТЕРНЕТ-ПОИСК (БЕЗ ПАМЯТИ)

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

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_headers() -> Dict:
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    }

def fetch_url(url: str, timeout: int = 25) -> Optional[str]:
    """Загрузить URL с обходом блокировок"""
    for attempt in range(3):
        try:
            response = requests.get(url, headers=get_headers(), timeout=timeout, verify=False, allow_redirects=True)
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                time.sleep(2)
                continue
            elif response.status_code in [301, 302, 303, 307, 308]:
                if 'Location' in response.headers:
                    new_url = response.headers['Location']
                    if not new_url.startswith('http'):
                        new_url = urljoin(url, new_url)
                    return fetch_url(new_url, timeout)
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
        1: {"emoji": "📄", "label": "PDF правила", "type": "pdf"},
        2: {"emoji": "🟡", "label": "Интернет-поиск", "type": "search"},
    }
    return levels.get(level, {"emoji": "⬜", "label": "Неизвестно", "type": "unknown"})

# ==================== ПОИСК PDF НА СТРАНИЦЕ (ВСЕМИ СПОСОБАМИ) ====================

def find_pdf_links(html: str, base_url: str) -> List[str]:
    """Найти все ссылки на PDF на странице (всеми возможными способами)"""
    soup = BeautifulSoup(html, 'html.parser')
    pdf_links = []
    
    # 1. Обычные ссылки <a href="...pdf">
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if href and '.pdf' in href.lower():
            full_url = urljoin(base_url, href)
            if full_url not in pdf_links:
                pdf_links.append(full_url)
    
    # 2. data-атрибуты (data-href, data-url, data-file, data-pdf)
    for tag in soup.find_all():
        for attr in ['data-href', 'data-url', 'data-file', 'data-pdf', 'data-src']:
            val = tag.get(attr)
            if val and '.pdf' in val.lower():
                full_url = urljoin(base_url, val)
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
    
    # 3. onclick атрибуты
    for tag in soup.find_all(attrs={'onclick': True}):
        onclick = tag.get('onclick', '')
        # Ищем URL в onclick
        match = re.search(r"['\"]([^'\"]+\.pdf)['\"]", onclick)
        if match:
            full_url = urljoin(base_url, match.group(1))
            if full_url not in pdf_links:
                pdf_links.append(full_url)
    
    # 4. Текст внутри тегов
    for tag in soup.find_all(['p', 'div', 'li', 'td', 'span']):
        text = tag.get_text()
        if '.pdf' in text.lower():
            # Ищем URL в тексте
            match = re.search(r'https?://[^\s<>"\']+\.pdf', text)
            if match:
                full_url = match.group(0)
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
    
    # 5. Ищем в ссылках по тексту "правила", "условия", "полис"
    for link in soup.find_all('a', href=True):
        text = link.get_text().lower()
        href = link.get('href', '').lower()
        if any(kw in text for kw in ['правила', 'условия', 'полис', 'тарифы']):
            if href and ('.pdf' in href or '?download' in href):
                full_url = urljoin(base_url, link.get('href'))
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
    
    return pdf_links

# ==================== ЧТЕНИЕ PDF ====================

def extract_text_from_pdf(pdf_url: str) -> Optional[str]:
    """Скачать PDF и извлечь текст"""
    try:
        import PyPDF2
        
        response = requests.get(pdf_url, headers=get_headers(), timeout=30, verify=False)
        if response.status_code != 200:
            return None
        
        # Проверяем, что это действительно PDF
        content_type = response.headers.get('Content-Type', '')
        if 'pdf' not in content_type.lower() and not pdf_url.lower().endswith('.pdf'):
            return None
        
        try:
            pdf_bytes = io.BytesIO(response.content)
            reader = PyPDF2.PdfReader(pdf_bytes)
            
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
        except:
            pass
        
        # Пробуем pypdf
        try:
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
        
        return None
        
    except ImportError:
        print("      ⚠️ PyPDF2 не установлен")
        return None
    except Exception as e:
        print(f"      ⚠️ Ошибка PDF: {e}")
        return None

# ==================== ИЗВЛЕЧЕНИЕ ДАННЫХ ИЗ ТЕКСТА ====================

def extract_field_from_text(text: str, field: str) -> Optional[str]:
    """Извлечь значение поля из текста по ключевым словам"""
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Ключевые слова для каждого поля
    keywords = {
        "franchise": ["франшиз", "франшиза", "безусловн", "условн"],
        "without_certificates": ["без справок", "без документ"],
        "gap": ["gap", "гэп", "сохранение стоимости"],
        "total_loss": ["тотал", "полная гибель", "гибель", "конструктивн"],
        "fire": ["самовозгоран", "возгоран", "пожар"],
        "terrorism": ["терроризм", "терр. акт"],
        "drone": ["бпла", "беспилот", "дрон"],
        "tow_truck": ["эвакуа"],
        "repair_type": ["ремонт", "стоа", "дилер"],
        "payment_terms": ["срок выплат", "рабочих дней", "дней"]
    }
    
    field_keywords = keywords.get(field, [])
    
    for kw in field_keywords:
        if kw in text_lower:
            # Ищем предложение с ключевым словом
            sentences = re.split(r'[.!?]', text)
            for sentence in sentences:
                if kw in sentence.lower():
                    value = clean_text(sentence)
                    if len(value) > 15 and len(value) < 400:
                        # Проверяем, что это не мусор
                        if not any(x in value.lower() for x in ["отзыв", "рейтинг", "звезд", "спасиб"]):
                            return value
    return None

# ==================== ПОИСК В ИНТЕРНЕТЕ ====================

def search_internet(company: str, field: str) -> Optional[Dict]:
    """Поиск в интернете через Яндекс по запросу: Правила страхования КАСКО {company}"""
    query = f"Правила страхования КАСКО {company}"
    print(f"    🔍 Яндекс: '{query}'")
    
    search_url = f"https://yandex.ru/search/?text={quote_plus(query)}&lr=213"
    
    html = fetch_url(search_url, timeout=15)
    if not html:
        print(f"    ⚠️ Яндекс не отвечает")
        return None
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Ищем ссылки на результаты
        for item in soup.find_all(['li', 'div'], class_=re.compile(r'result|serp-item|organic')):
            link_tag = item.find('a')
            if not link_tag:
                continue
            
            href = link_tag.get('href', '')
            if href.startswith('/'):
                href = f"https://yandex.ru{href}"
            
            if not href.startswith('http'):
                continue
            
            # Загружаем страницу
            page_html = fetch_url(href, timeout=15)
            if not page_html:
                continue
            
            # Ищем в тексте страницы
            soup_page = BeautifulSoup(page_html, 'html.parser')
            for tag in soup_page.find_all(["script", "style", "noscript"]):
                tag.decompose()
            page_text = clean_text(soup_page.get_text())
            
            # Ищем поле в тексте
            value = extract_field_from_text(page_text, field)
            if value:
                return {
                    "value": value,
                    "source": {
                        "level": 2,
                        "name": f"Интернет-поиск (Яндекс)",
                        "url": href,
                        "found_at": datetime.now().isoformat()
                    }
                }
        
        return None
        
    except Exception as e:
        print(f"    ⚠️ Ошибка поиска: {e}")
        return None

# ==================== СБОР ДАННЫХ ДЛЯ ОДНОЙ КОМПАНИИ ====================

def collect_company_data(company: str) -> Dict:
    print(f"\n🔍 {company}")
    print("━" * 50)
    
    result = {}
    found = set()
    source_stats = {1: 0, 2: 0}
    
    # УРОВЕНЬ 1: PDF со страницы КАСКО
    print(f"  📂 Уровень 1: Поиск PDF на странице КАСКО")
    
    if company not in KASKO_PAGES:
        print(f"    ⚠️ Нет URL для {company}")
    else:
        url = KASKO_PAGES[company]
        html = fetch_url(url)
        
        if html:
            pdf_links = find_pdf_links(html, url)
            
            if pdf_links:
                print(f"    📄 Найдено PDF: {len(pdf_links)}")
                
                # Пробуем читать каждый PDF
                for pdf_url in pdf_links[:10]:  # Ограничиваем 10 PDF
                    if any(x in pdf_url.lower() for x in ['cookie', 'privacy', 'policy', 'logo']):
                        continue
                    
                    print(f"      📥 Читаем PDF: {pdf_url[:80]}...")
                    
                    pdf_text = extract_text_from_pdf(pdf_url)
                    if not pdf_text:
                        continue
                    
                    # Ищем все поля в этом PDF
                    for field in KASKO_FIELDS:
                        if field in found:
                            continue
                        
                        value = extract_field_from_text(pdf_text, field)
                        if value:
                            result[field] = {
                                "value": value,
                                "source": {
                                    "level": 1,
                                    "name": f"PDF {company}",
                                    "url": pdf_url,
                                    "found_at": datetime.now().isoformat()
                                }
                            }
                            found.add(field)
                            source_stats[1] += 1
                            print(f"      ✅ Из PDF: {FIELD_LABELS.get(field, field)}")
                    
                    # Если нашли все поля — выходим
                    if len(found) >= len(KASKO_FIELDS):
                        break
            else:
                print(f"    ⚠️ PDF не найдены на странице")
        else:
            print(f"    ⚠️ Не удалось загрузить страницу")
    
    # УРОВЕНЬ 2: Интернет-поиск (для недостающих полей)
    missing_fields = [f for f in KASKO_FIELDS if f not in found]
    if missing_fields:
        print(f"  📂 Уровень 2: Интернет-поиск")
        for field in missing_fields:
            search_result = search_internet(company, field)
            if search_result:
                result[field] = search_result
                found.add(field)
                source_stats[2] += 1
                print(f"    ✅ Найдено: {FIELD_LABELS.get(field, field)}")
    
    # ИТОГ
    print(f"\n📊 {company}: собрано {len(found)}/{len(KASKO_FIELDS)} полей")
    for level, count in source_stats.items():
        if count > 0:
            info = get_source_info(level)
            print(f"  {info['emoji']} {info['label']}: {count}")
    
    # Для полей, которые не найдены — ставим "Не найдено"
    for field in KASKO_FIELDS:
        if field not in result:
            result[field] = {
                "value": "Не найдено",
                "source": {
                    "level": 0,
                    "name": "Информация не найдена",
                    "url": None,
                    "found_at": datetime.now().isoformat()
                }
            }
    
    return result

def collect_all_data() -> Dict:
    print("\n" + "=" * 60)
    print("📊 СБОР ДАННЫХ: КАСКО (ТОЛЬКО PDF + ИНТЕРНЕТ)")
    print("=" * 60)
    print("Поля:", ", ".join(FIELD_LABELS[f] for f in KASKO_FIELDS))
    print("=" * 60)
    
    all_data = {}
    for company in KASKO_PAGES.keys():
        all_data[company] = collect_company_data(company)
        time.sleep(2)
    
    all_data["_last_updated"] = datetime.now().isoformat()
    all_data["_fields"] = KASKO_FIELDS
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
        <span class="badge">10 параметров</span>
        <span class="badge">PDF + Поиск</span>
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
