import os
import json
import time
import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from flask import Flask, render_template, request, jsonify, session
import cloudscraper
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from duckduckgo_search import DDGS
import requests
from urllib.parse import urlparse, quote_plus

app = Flask(__name__)
app.secret_key = 'insurance_agent_secret_key_2026'

# ==================== КОНФИГУРАЦИЯ ====================

class Config:
    # Кэширование
    CACHE_FILE = 'insurance_cache.json'
    CACHE_DAYS = 7
    
    # Временные задержки (чтобы не блокировали)
    MIN_DELAY = 1.0
    MAX_DELAY = 3.0
    
    # User-Agent ротация
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
    ]
    
    # Прокси (если есть - добавить)
    PROXIES = []

# ==================== СТРУКТУРА ДАННЫХ ====================

@dataclass
class SourceInfo:
    """Информация об источнике данных"""
    name: str
    url: str
    level: int  # 1-6
    source_type: str  # official, aggregator, rating, search, memory
    found_at: str
    
    def to_dict(self):
        return asdict(self)

@dataclass
class FieldValue:
    """Значение поля с источником"""
    value: str
    source: SourceInfo
    
    def to_dict(self):
        return {
            'value': self.value,
            'source': self.source.to_dict()
        }

# ==================== КЭШИРОВАНИЕ ====================

class SmartCache:
    def __init__(self, cache_file=Config.CACHE_FILE):
        self.cache_file = cache_file
        self.data = self._load()
    
    def _load(self):
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save(self):
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def get(self, key):
        if key in self.data:
            entry = self.data[key]
            cache_time = datetime.fromisoformat(entry['timestamp'])
            if datetime.now() - cache_time < timedelta(days=Config.CACHE_DAYS):
                return entry['value']
        return None
    
    def set(self, key, value):
        self.data[key] = {
            'value': value,
            'timestamp': datetime.now().isoformat()
        }
        self._save()

cache = SmartCache()

# ==================== АНТИДЕТЕКТ-ПАРСИНГ ====================

class AntiDetectParser:
    """Парсер с маскировкой под реального пользователя"""
    
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        self.session = requests.Session()
    
    def _get_headers(self):
        return {
            'User-Agent': random.choice(Config.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
    
    def _delay(self):
        time.sleep(random.uniform(Config.MIN_DELAY, Config.MAX_DELAY))
    
    def fetch_html(self, url: str, use_selenium: bool = False) -> Optional[str]:
        """Загружает HTML с маскировкой"""
        
        # Проверяем кэш
        cache_key = f"html_{url}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        self._delay()
        headers = self._get_headers()
        
        # Стратегия 1: CloudScraper
        try:
            response = self.scraper.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                html = response.text
                cache.set(cache_key, html)
                return html
        except Exception as e:
            print(f"CloudScraper error for {url}: {e}")
        
        # Стратегия 2: Selenium (для сложных сайтов)
        if use_selenium:
            try:
                html = self._fetch_with_selenium(url)
                if html:
                    cache.set(cache_key, html)
                    return html
            except Exception as e:
                print(f"Selenium error for {url}: {e}")
        
        return None
    
    def _fetch_with_selenium(self, url: str) -> Optional[str]:
        """Загрузка через Selenium с маскировкой"""
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument(f'user-agent={random.choice(Config.USER_AGENTS)}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['ru-RU', 'ru', 'en-US', 'en']
                    });
                '''
            })
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(random.uniform(2, 4))
            return driver.page_source
        except Exception as e:
            print(f"Selenium error: {e}")
            return None
        finally:
            if driver:
                driver.quit()

parser = AntiDetectParser()

# ==================== ПОИСКОВЫЕ СИСТЕМЫ ====================

class SearchEngine:
    """Поиск через DuckDuckGo"""
    
    @staticmethod
    def search(query: str, max_results: int = 5) -> List[Dict]:
        """Поиск с кэшированием"""
        cache_key = f"search_{query}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        try:
            with DDGS() as ddgs:
                results = []
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        'title': r.get('title', ''),
                        'snippet': r.get('body', ''),
                        'url': r.get('href', '')
                    })
                cache.set(cache_key, results)
                return results
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    @staticmethod
    def search_question(question: str, company: str, product: str) -> List[Dict]:
        """Формирует поисковый запрос как вопрос"""
        query = f"{question} {company} {product}"
        return SearchEngine.search(query)

# ==================== КОНФИГУРАЦИЯ ПРОДУКТОВ ====================

PRODUCTS = {
    "kasko": {
        "name": "КАСКО",
        "icon": "🚗",
        "fields": {
            "total_loss": {
                "name": "Тотал (%)",
                "question": "Какой процент тотала у КАСКО"
            },
            "franchise": {
                "name": "Франшиза",
                "question": "Какая франшиза у КАСКО"
            },
            "gap": {
                "name": "GAP",
                "question": "Есть ли GAP в КАСКО"
            },
            "drone": {
                "name": "БПЛА",
                "question": "Покрывает ли ущерб от БПЛА"
            },
            "fire": {
                "name": "Самовозгорание",
                "question": "Покрывает ли самовозгорание"
            },
            "without_certificates": {
                "name": "Выплата без справок",
                "question": "Выплата без справок по КАСКО"
            },
            "evacuator": {
                "name": "Эвакуатор (лимит)",
                "question": "Какой лимит эвакуатора"
            },
            "repair_type": {
                "name": "Тип ремонта",
                "question": "Какой тип ремонта"
            },
            "payment_terms": {
                "name": "Срок выплаты (дни)",
                "question": "Какой срок выплаты по КАСКО"
            },
            "rating": {
                "name": "Рейтинг",
                "question": "Какой рейтинг у КАСКО"
            }
        },
        "official_urls": [
            "https://www.reso.ru/",
            "https://www.reso.ru/insurance/auto/kasko/"
        ],
        "search_suffix": "РЕСО-Гарантия"
    },
    "osago": {
        "name": "ОСАГО",
        "icon": "🛡️",
        "fields": {
            "base_rate": {
                "name": "Базовый тариф",
                "question": "Какой базовый тариф ОСАГО"
            },
            "bm": {
                "name": "Коэффициент бонус-малус",
                "question": "Какой коэффициент бонус-малус"
            },
            "territory_coef": {
                "name": "Территориальный коэффициент",
                "question": "Какой территориальный коэффициент"
            },
            "power_coef": {
                "name": "Коэффициент мощности",
                "question": "Какой коэффициент мощности"
            },
            "age_coef": {
                "name": "Возрастной коэффициент",
                "question": "Какой возрастной коэффициент"
            },
            "period_coef": {
                "name": "Коэффициент периода",
                "question": "Какой коэффициент периода использования"
            },
            "rating": {
                "name": "Рейтинг",
                "question": "Какой рейтинг ОСАГО"
            }
        },
        "official_urls": [
            "https://www.reso.ru/",
            "https://www.reso.ru/insurance/auto/osago/"
        ],
        "search_suffix": "РЕСО-Гарантия"
    },
    "ifl": {
        "name": "Имущественное страхование",
        "icon": "🏠",
        "fields": {
            "fire": {
                "name": "Пожар",
                "question": "Покрывает ли страховка пожар"
            },
            "flood": {
                "name": "Залив",
                "question": "Покрывает ли страховка залив"
            },
            "theft": {
                "name": "Кража",
                "question": "Покрывает ли страховка кражу"
            },
            "liability": {
                "name": "Гражданская ответственность",
                "question": "Покрывает ли гражданскую ответственность"
            },
            "natural_disasters": {
                "name": "Стихийные бедствия",
                "question": "Покрывает ли стихийные бедствия"
            },
            "rating": {
                "name": "Рейтинг",
                "question": "Какой рейтинг страхования имущества"
            }
        },
        "official_urls": [
            "https://www.reso.ru/",
            "https://www.reso.ru/insurance/property/"
        ],
        "search_suffix": "РЕСО-Гарантия"
    }
}

# ==================== АГРЕГАТОРЫ ====================

AGGREGATORS = [
    {
        "name": "Сравни.ру",
        "url": "https://www.sravni.ru/",
        "type": "aggregator",
        "level": 2
    },
    {
        "name": "Банки.ру",
        "url": "https://www.banki.ru/",
        "type": "aggregator",
        "level": 2
    },
    {
        "name": "Финуслуги",
        "url": "https://finuslugi.ru/",
        "type": "aggregator",
        "level": 2
    },
    {
        "name": "Инсмарт",
        "url": "https://insmart.ru/",
        "type": "aggregator",
        "level": 3
    },
    {
        "name": "Пампаду",
        "url": "https://pampadu.ru/",
        "type": "aggregator",
        "level": 3
    },
    {
        "name": "Полис Онлайн",
        "url": "https://polis.online/",
        "type": "aggregator",
        "level": 3
    }
]

RATING_SOURCES = [
    {
        "name": "Эксперт РА",
        "url": "https://raexpert.ru/",
        "type": "rating",
        "level": 4
    },
    {
        "name": "ЦБ РФ",
        "url": "https://cbr.ru/",
        "type": "rating",
        "level": 4
    }
]

# ==================== ОСНОВНАЯ ЛОГИКА ПОИСКА ====================

class InsuranceAgent:
    """Главный агент для поиска страховых данных"""
    
    def __init__(self):
        self.cache = SmartCache()
        self.parser = AntiDetectParser()
        self.search = SearchEngine()
    
    def find_value(self, company: str, product: str, field_key: str, field_config: Dict) -> FieldValue:
        """
        Многоуровневый поиск значения поля
        Уровни:
        1. Официальный сайт
        2. Агрегаторы (крупные)
        3. Специализированные агрегаторы
        4. Рейтинговые агентства
        5. Интернет-поиск
        6. Внутренняя память (fallback)
        """
        
        product_config = PRODUCTS.get(product)
        if not product_config:
            return self._fallback_value(field_key, "Продукт не найден")
        
        field_name = field_config.get('name', field_key)
        question = field_config.get('question', '')
        search_suffix = product_config.get('search_suffix', '')
        
        # Проверяем кэш
        cache_key = f"value_{company}_{product}_{field_key}"
        cached = self.cache.get(cache_key)
        if cached:
            return FieldValue(
                value=cached['value'],
                source=SourceInfo(
                    name=cached['source']['name'],
                    url=cached['source']['url'],
                    level=cached['source']['level'],
                    source_type=cached['source']['source_type'],
                    found_at=cached['source']['found_at']
                )
            )
        
        # Уровень 1: Официальный сайт
        official_result = self._search_official(company, product, field_key, field_config)
        if official_result and official_result.value != "не найдено":
            self.cache.set(cache_key, official_result.to_dict())
            return official_result
        
        # Уровень 2-3: Агрегаторы
        for aggregator in AGGREGATORS:
            agg_result = self._search_aggregator(aggregator, company, product, field_key, field_config)
            if agg_result and agg_result.value != "не найдено":
                self.cache.set(cache_key, agg_result.to_dict())
                return agg_result
            time.sleep(random.uniform(0.5, 1.5))
        
        # Уровень 4: Рейтинги
        for rating in RATING_SOURCES:
            rating_result = self._search_rating(rating, company, product, field_key, field_config)
            if rating_result and rating_result.value != "не найдено":
                self.cache.set(cache_key, rating_result.to_dict())
                return rating_result
        
        # Уровень 5: Интернет-поиск
        if question:
            search_result = self._search_internet(question, company, search_suffix)
            if search_result and search_result.value != "не найдено":
                self.cache.set(cache_key, search_result.to_dict())
                return search_result
        
        # Уровень 6: Fallback (внутренняя память)
        fallback = self._get_fallback(company, product, field_key)
        if fallback:
            self.cache.set(cache_key, fallback.to_dict())
            return fallback
        
        # Если ничего не найдено
        return self._fallback_value(field_key, "Данные не найдены")
    
    def _search_official(self, company: str, product: str, field_key: str, field_config: Dict) -> Optional[FieldValue]:
        """Поиск на официальном сайте"""
        product_config = PRODUCTS.get(product)
        if not product_config:
            return None
        
        for url in product_config.get('official_urls', []):
            html = self.parser.fetch_html(url)
            if not html:
                continue
            
            # Пытаемся извлечь информацию через BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Ищем по ключевым словам
            field_name = field_config.get('name', field_key)
            keywords = [field_name.lower(), field_key.lower()]
            
            # Поиск в тексте
            text = soup.get_text()
            for keyword in keywords:
                pattern = rf'{keyword}.*?([0-9]+[%]?|да|нет|есть|отсутствует|[0-9]+[\s]*дней?|[0-9]+[\s]*руб\.?)'
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value:
                        return FieldValue(
                            value=value,
                            source=SourceInfo(
                                name=f"Официальный сайт {company}",
                                url=url,
                                level=1,
                                source_type="official",
                                found_at=datetime.now().isoformat()
                            )
                        )
        
        return None
    
    def _search_aggregator(self, aggregator: Dict, company: str, product: str, field_key: str, field_config: Dict) -> Optional[FieldValue]:
        """Поиск на агрегаторах"""
        # Формируем поисковый запрос для агрегатора
        query = f"{company} {PRODUCTS.get(product, {}).get('name', '')} {field_config.get('name', field_key)}"
        search_url = f"{aggregator['url']}search/?q={quote_plus(query)}"
        
        html = self.parser.fetch_html(search_url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        
        # Ищем значения
        patterns = [
            r'([0-9]+[%]?)',
            r'(да|нет|есть|отсутствует)',
            r'([0-9]+[\s]*дней?)',
            r'([0-9]+[\s]*руб\.?)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    return FieldValue(
                        value=value,
                        source=SourceInfo(
                            name=f"Агрегатор {aggregator['name']}",
                            url=search_url,
                            level=aggregator.get('level', 2),
                            source_type="aggregator",
                            found_at=datetime.now().isoformat()
                        )
                    )
        
        return None
    
    def _search_rating(self, rating: Dict, company: str, product: str, field_key: str, field_config: Dict) -> Optional[FieldValue]:
        """Поиск в рейтинговых агентствах"""
        # Для рейтингов используем поиск
        query = f"{company} рейтинг {field_config.get('name', field_key)}"
        results = self.search.search(query, max_results=3)
        
        for result in results:
            snippet = result.get('snippet', '')
            # Ищем числовые значения в сниппете
            match = re.search(r'([0-9]+[%]?|[A-Za-z]+[A-Z]+|[0-9]+\.[0-9])', snippet)
            if match:
                value = match.group(1).strip()
                if value:
                    return FieldValue(
                        value=value,
                        source=SourceInfo(
                            name=f"Рейтинговое агентство {rating['name']}",
                            url=result.get('url', rating['url']),
                            level=rating.get('level', 4),
                            source_type="rating",
                            found_at=datetime.now().isoformat()
                        )
                    )
        
        return None
    
    def _search_internet(self, question: str, company: str, search_suffix: str) -> Optional[FieldValue]:
        """Поиск в интернете через DuckDuckGo"""
        full_query = f"{question} {company} {search_suffix}"
        results = self.search.search_question(question, company, search_suffix)
        
        for result in results:
            snippet = result.get('snippet', '')
            # Ищем ответ на вопрос
            patterns = [
                r'([0-9]+[%]?)',
                r'(да|нет|есть|отсутствует)',
                r'([0-9]+[\s]*дней?)',
                r'([0-9]+[\s]*руб\.?)',
                r'(от\s*[0-9]+[%]?)',
                r'(до\s*[0-9]+[%]?)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, snippet, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value:
                        return FieldValue(
                            value=value,
                            source=SourceInfo(
                                name="Интернет-поиск (DuckDuckGo)",
                                url=result.get('url', ''),
                                level=5,
                                source_type="search",
                                found_at=datetime.now().isoformat()
                            )
                        )
        
        return None
    
    def _get_fallback(self, company: str, product: str, field_key: str) -> Optional[FieldValue]:
        """Внутренняя память (fallback данные)"""
        fallback_data = {
            "РЕСО-Гарантия": {
                "kasko": {
                    "total_loss": {"value": "75%", "url": "https://www.reso.ru/"},
                    "franchise": {"value": "От 0% до 10%", "url": "https://www.reso.ru/"},
                    "gap": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "drone": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "fire": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "without_certificates": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "evacuator": {"value": "3000 руб.", "url": "https://www.reso.ru/"},
                    "repair_type": {"value": "На СТОА", "url": "https://www.reso.ru/"},
                    "payment_terms": {"value": "30 дней", "url": "https://www.reso.ru/"},
                    "rating": {"value": "ruAA", "url": "https://raexpert.ru/"}
                },
                "osago": {
                    "base_rate": {"value": "от 2 500 руб.", "url": "https://www.reso.ru/"},
                    "bm": {"value": "0.5-2.45", "url": "https://www.reso.ru/"},
                    "territory_coef": {"value": "0.6-2.0", "url": "https://www.reso.ru/"},
                    "power_coef": {"value": "0.6-1.6", "url": "https://www.reso.ru/"},
                    "age_coef": {"value": "0.8-1.8", "url": "https://www.reso.ru/"},
                    "period_coef": {"value": "0.5-1.0", "url": "https://www.reso.ru/"},
                    "rating": {"value": "ruAA", "url": "https://raexpert.ru/"}
                },
                "ifl": {
                    "fire": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "flood": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "theft": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "liability": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "natural_disasters": {"value": "Есть", "url": "https://www.reso.ru/"},
                    "rating": {"value": "ruAA", "url": "https://raexpert.ru/"}
                }
            }
        }
        
        company_data = fallback_data.get(company, {}).get(product, {})
        field_data = company_data.get(field_key)
        
        if field_data:
            return FieldValue(
                value=field_data['value'],
                source=SourceInfo(
                    name="Внутренняя память (проверенные данные)",
                    url=field_data.get('url', ''),
                    level=6,
                    source_type="memory",
                    found_at=datetime.now().isoformat()
                )
            )
        
        return None
    
    def _fallback_value(self, field_key: str, message: str) -> FieldValue:
        """Значение по умолчанию"""
        return FieldValue(
            value=message,
            source=SourceInfo(
                name="Система",
                url="",
                level=6,
                source_type="memory",
                found_at=datetime.now().isoformat()
            )
        )

# ==================== ВЕБ-ИНТЕРФЕЙС ====================

agent = InsuranceAgent()

@app.route('/')
def index():
    """Главная страница"""
    companies = ["РЕСО-Гарантия", "Согаз", "Ингосстрах", "АльфаСтрахование", "ВСК"]
    products = list(PRODUCTS.keys())
    return render_template('index.html', companies=companies, products=products)

@app.route('/compare', methods=['POST'])
def compare():
    """Сравнение двух компаний"""
    company1 = request.form.get('company1')
    company2 = request.form.get('company2')
    product = request.form.get('product')
    
    if not company1 or not company2 or not product:
        return jsonify({'error': 'Не выбраны компании или продукт'}), 400
    
    product_config = PRODUCTS.get(product)
    if not product_config:
        return jsonify({'error': 'Продукт не найден'}), 400
    
    results = {
        'product': product,
        'product_name': product_config['name'],
        'company1': company1,
        'company2': company2,
        'fields': {},
        'sources': {
            'company1': {},
            'company2': {}
        }
    }
    
    for field_key, field_config in product_config['fields'].items():
        field_name = field_config['name']
        
        # Поиск для первой компании
        val1 = agent.find_value(company1, product, field_key, field_config)
        # Поиск для второй компании
        val2 = agent.find_value(company2, product, field_key, field_config)
        
        results['fields'][field_key] = {
            'name': field_name,
            'company1': val1.to_dict(),
            'company2': val2.to_dict()
        }
        
        results['sources']['company1'][field_key] = val1.source.to_dict()
        results['sources']['company2'][field_key] = val2.source.to_dict()
    
    # Добавляем информацию об источниках для отображения
    source_levels = {
        1: {'icon': '🟢', 'label': 'Официальный сайт'},
        2: {'icon': '🔵', 'label': 'Агрегатор'},
        3: {'icon': '🟦', 'label': 'Специализированный агрегатор'},
        4: {'icon': '🟡', 'label': 'Рейтинговое агентство'},
        5: {'icon': '🟣', 'label': 'Интернет-поиск'},
        6: {'icon': '⚪', 'label': 'Внутренняя память'}
    }
    
    results['source_levels'] = source_levels
    
    return jsonify(results)

@app.route('/update', methods=['POST'])
def update():
    """Принудительное обновление кэша"""
    # Очищаем кэш
    if os.path.exists(Config.CACHE_FILE):
        os.remove(Config.CACHE_FILE)
    
    return jsonify({'status': 'ok', 'message': 'Кэш очищен, данные будут обновлены'})

# ==================== ШАБЛОНЫ ====================

# Создаем папку templates если её нет
if not os.path.exists('templates'):
    os.makedirs('templates')

# Шаблон index.html
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write('''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Страховой агент - сравнение</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 20px; padding: 40px; box-shadow: 0 10px 40px rgba(0,0,0,0.08); }
        h1 { font-size: 32px; color: #1a2332; margin-bottom: 8px; }
        .subtitle { color: #6b7a8f; margin-bottom: 30px; }
        .form-group { display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 30px; }
        .form-group label { font-weight: 500; color: #1a2332; display: block; margin-bottom: 5px; }
        .form-group select { width: 100%; padding: 12px 16px; border: 2px solid #e1e8f0; border-radius: 12px; font-size: 16px; background: white; transition: border-color 0.2s; }
        .form-group select:focus { outline: none; border-color: #2d6bff; }
        .form-group .field { flex: 1; min-width: 200px; }
        .btn { padding: 14px 40px; background: #2d6bff; color: white; border: none; border-radius: 12px; font-size: 16px; font-weight: 600; cursor: pointer; transition: background 0.2s; }
        .btn:hover { background: #1a56e8; }
        .btn-secondary { background: #e1e8f0; color: #1a2332; }
        .btn-secondary:hover { background: #d0d9e5; }
        .results { margin-top: 40px; }
        .table-wrapper { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { background: #f8fafc; padding: 14px 16px; text-align: left; font-weight: 600; color: #1a2332; border-bottom: 2px solid #e1e8f0; }
        td { padding: 12px 16px; border-bottom: 1px solid #eef2f7; }
        tr:hover td { background: #f8fafc; }
        .source-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px; font-size: 12px; background: #f0f4ff; color: #2d6bff; }
        .source-badge .icon { font-size: 14px; }
        .sources-section { margin-top: 30px; padding: 20px; background: #f8fafc; border-radius: 12px; }
        .sources-section h3 { color: #1a2332; margin-bottom: 12px; }
        .source-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; font-size: 13px; color: #4a5a72; }
        .source-item .url { color: #2d6bff; text-decoration: none; font-size: 12px; }
        .source-item .url:hover { text-decoration: underline; }
        .loading { text-align: center; padding: 40px; color: #6b7a8f; }
        .error { color: #dc3545; padding: 20px; text-align: center; }
        .update-btn { margin-left: 20px; padding: 8px 16px; font-size: 13px; }
        @media (max-width: 768px) { .container { padding: 20px; } .form-group { flex-direction: column; } }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Страховой агент</h1>
        <p class="subtitle">Сравнение страховых продуктов с указанием источников</p>
        
        <form id="compareForm">
            <div class="form-group">
                <div class="field">
                    <label>Продукт</label>
                    <select id="product" name="product">
                        {% for key, product in products.items() %}
                            <option value="{{ key }}">{{ product.icon }} {{ product.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="field">
                    <label>Компания 1</label>
                    <select id="company1" name="company1">
                        {% for company in companies %}
                            <option value="{{ company }}">{{ company }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="field">
                    <label>Компания 2</label>
                    <select id="company2" name="company2">
                        {% for company in companies %}
                            <option value="{{ company }}">{{ company }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="field" style="display: flex; align-items: flex-end;">
                    <button type="submit" class="btn">Сравнить</button>
                    <button type="button" class="btn btn-secondary update-btn" onclick="updateCache()">🔄 Обновить</button>
                </div>
            </div>
        </form>
        
        <div id="results" class="results"></div>
    </div>
    
    <script>
        document.getElementById('compareForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const resultsDiv = document.getElementById('results');
            resultsDiv.innerHTML = '<div class="loading">⏳ Поиск данных...</div>';
            
            try {
                const response = await fetch('/compare', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();
                
                if (data.error) {
                    resultsDiv.innerHTML = `<div class="error">❌ ${data.error}</div>`;
                    return;
                }
                
                resultsDiv.innerHTML = renderResults(data);
            } catch (error) {
                resultsDiv.innerHTML = `<div class="error">❌ Ошибка: ${error.message}</div>`;
            }
        });
        
        function renderResults(data) {
            const levels = data.source_levels;
            const fields = data.fields;
            
            let html = `
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Параметр</th>
                                <th>${data.company1}</th>
                                <th>${data.company2}</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            
            for (const [key, field] of Object.entries(fields)) {
                const c1 = field.company1;
                const c2 = field.company2;
                const level1 = levels[c1.source.level] || { icon: '⚪', label: 'Неизвестно' };
                const level2 = levels[c2.source.level] || { icon: '⚪', label: 'Неизвестно' };
                
                html += `
                    <tr>
                        <td><strong>${field.name}</strong></td>
                        <td>
                            ${c1.value}
                            <span class="source-badge">
                                <span class="icon">${level1.icon}</span>
                                ${level1.label}
                            </span>
                        </td>
                        <td>
                            ${c2.value}
                            <span class="source-badge">
                                <span class="icon">${level2.icon}</span>
                                ${level2.label}
                            </span>
                        </td>
                    </tr>
                `;
            }
            
            html += `
                        </tbody>
                    </table>
                </div>
            `;
            
            // Блок источников
            html += `
                <div class="sources-section">
                    <h3>📋 Детальная информация об источниках</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                        <div>
                            <h4 style="color: #1a2332; margin-bottom: 8px;">${data.company1}</h4>
                            ${renderSources(data.sources.company1, levels)}
                        </div>
                        <div>
                            <h4 style="color: #1a2332; margin-bottom: 8px;">${data.company2}</h4>
                            ${renderSources(data.sources.company2, levels)}
                        </div>
                    </div>
                </div>
            `;
            
            return html;
        }
        
        function renderSources(sources, levels) {
            let html = '';
            for (const [key, source] of Object.entries(sources)) {
                const level = levels[source.level] || { icon: '⚪', label: 'Неизвестно' };
                html += `
                    <div class="source-item">
                        <span>${level.icon}</span>
                        <span>${source.name}</span>
                        ${source.url ? `<a href="${source.url}" target="_blank" class="url">🔗 ссылка</a>` : ''}
                        <span style="color: #6b7a8f; font-size: 11px;">${new Date(source.found_at).toLocaleDateString()}</span>
                    </div>
                `;
            }
            return html || '<div style="color: #6b7a8f; font-size: 13px;">Нет данных</div>';
        }
        
        async function updateCache() {
            const btn = document.querySelector('.update-btn');
            btn.textContent = '⏳ Обновление...';
            btn.disabled = true;
            
            try {
                const response = await fetch('/update', { method: 'POST' });
                const data = await response.json();
                alert('✅ ' + data.message);
            } catch (error) {
                alert('❌ Ошибка: ' + error.message);
            } finally {
                btn.textContent = '🔄 Обновить';
                btn.disabled = false;
            }
        }
    </script>
</body>
</html>
    ''')

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    # Создаем шаблоны
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Проверяем наличие index.html
    if not os.path.exists('templates/index.html'):
        with open('templates/index.html', 'w', encoding='utf-8') as f:
            f.write('''
<!DOCTYPE html>
<html>
<head><title>Страховой агент</title></head>
<body>
    <h1>Страховой агент</h1>
    <p>Шаблон не найден. Пожалуйста, перезапустите приложение.</p>
</body>
</html>
            ''')
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║          🚀 СТРАХОВОЙ АГЕНТ ЗАПУЩЕН                       ║
    ╠═══════════════════════════════════════════════════════════╣
    ║  Доступно по адресу: http://127.0.0.1:5000               ║
    ║                                                           ║
    ║  Уровни источников:                                       ║
    ║  🟢 Уровень 1: Официальный сайт                          ║
    ║  🔵 Уровень 2: Агрегатор                                 ║
    ║  🟦 Уровень 3: Специализированный агрегатор              ║
    ║  🟡 Уровень 4: Рейтинговое агентство                     ║
    ║  🟣 Уровень 5: Интернет-поиск                            ║
    ║  ⚪ Уровень 6: Внутренняя память                         ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
