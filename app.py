# app.py — ИСПРАВЛЕННАЯ ВЕРСИЯ

from flask import Flask, render_template, request, session, redirect, url_for
from datetime import datetime, timedelta
import json
import os
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ==================== ФАЙЛЫ ДЛЯ ХРАНЕНИЯ ====================
USERS_FILE = "users.json"
PAYMENTS_FILE = "payments.json"

# ==================== ДАННЫЕ ====================
INSURANCE_DATA = {
    "РЕСО-Гарантия": {
        "franchise": "Безусловная / условно-безусловная",
        "without_certificates": "Стекла без ограничений; 1 кузовной элемент в год",
        "gap": "Отдельный риск",
        "total_loss": "75%",
        "drone": "Лимит 1% СС",
        "advantages": "Ремонт у дилера, 5 дней на выплату, без учета износа",
        "weak_points": "Требуется уточнение условий",
        "rating": "4.5",
        "offices": "1200+"
    },
    "СОГАЗ": {
        "franchise": "Безусловная / условно-безусловная",
        "without_certificates": "Вариантно: 1 раз один элемент / Неограниченно стекла + 1 раз кузовной",
        "gap": "Отдельный риск",
        "total_loss": "70%",
        "drone": "Исключение",
        "advantages": "Гибкие условия, надёжность",
        "weak_points": "Тотал 70%, выплата 30 дней",
        "rating": "4.3",
        "offices": "500+"
    },
    "АльфаСтрахование": {
        "franchise": "Условно-безусловная",
        "without_certificates": "Стекла без ограничений + 1 кузовной элемент 2 раза в год",
        "gap": "Включен по умолчанию",
        "total_loss": "75%",
        "drone": "За доп. плату",
        "advantages": "Без справок с бонусами",
        "weak_points": "Франшиза на Хищение",
        "rating": "4.6",
        "offices": "600+"
    },
    "Ингосстрах": {
        "franchise": "Условная/условно-безусловная",
        "without_certificates": "ЛПКП 1 деталь; остекление (кроме крыши)",
        "gap": "Включен при постоянной СС",
        "total_loss": "75%",
        "drone": "За доп. плату",
        "advantages": "Широкая сеть офисов",
        "weak_points": "Без справок – только ЛКП 1 детали",
        "rating": "4.4",
        "offices": "900+"
    },
    "Ренессанс": {
        "franchise": "11 видов франшиз",
        "without_certificates": "Вариативно (стекла / до 5% СС)",
        "gap": "Отдельный риск",
        "total_loss": "75%",
        "drone": "За доп. плату",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Эвакуация за доп. плату",
        "rating": "4.3",
        "offices": "500+"
    },
    "Т-Страхование": {
        "franchise": "Условно-безусловная",
        "without_certificates": "Стекла неогранич.; Кузов до 3% СС",
        "gap": "Отдельный риск",
        "total_loss": "65%",
        "drone": "Нет инф.",
        "advantages": "Онлайн-оформление",
        "weak_points": "Ниже порог тотала",
        "rating": "4.7",
        "offices": "онлайн"
    },
    "ВСК": {
        "franchise": "Условно-безусловная",
        "without_certificates": "Стекла: 5% СС; Прочие: 3% СС",
        "gap": "Включен при 1 периоде",
        "total_loss": "75%",
        "drone": "Включен при наличии GAP",
        "advantages": "Гибкие условия по справкам",
        "weak_points": "Камеры не оплачиваются без справок",
        "rating": "4.2",
        "offices": "800+"
    },
    "Согласие": {
        "franchise": "Условно-безусловная / динамическая",
        "without_certificates": "Неограниченно стекла + 1 элемент",
        "gap": "Отдельный риск",
        "total_loss": "70%",
        "drone": "За доп. плату",
        "advantages": "Гибкие условия",
        "weak_points": "Тотал 70%",
        "rating": "4.2",
        "offices": "300+"
    },
    "Югория": {
        "franchise": "Условно-безусловная",
        "without_certificates": "Стекла: 1 раз (кроме панорамной)",
        "gap": "Неагрегатная",
        "total_loss": "Не указан",
        "drone": "Входит",
        "advantages": "Гибкие условия пролонгации",
        "weak_points": "При пролонгации доп. франшиза",
        "rating": "3.9",
        "offices": "400+"
    },
    "СберСтрахование": {
        "franchise": "6 видов франшиз",
        "without_certificates": "1 деталь + стекла / Только стекла",
        "gap": "Включен при индексируемой СС",
        "total_loss": "70%",
        "drone": "Исключение",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Тотал 70%",
        "rating": "4.0",
        "offices": "1000+"
    },
    "Совкомбанк Страхование": {
        "franchise": "Условно-безусловная / Обязательная 25%",
        "without_certificates": "Только ремонт или замена стекла",
        "gap": "Нет инф.",
        "total_loss": "75%",
        "drone": "Исключение",
        "advantages": "Группы событий",
        "weak_points": "Терроризм исключен",
        "rating": "3.8",
        "offices": "200+"
    }
}

ALL_COMPANIES = list(INSURANCE_DATA.keys())

# ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================

def load_users():
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# ==================== МАРШРУТЫ ====================

@app.route('/')
def index():
    user = session.get('user')
    return render_template('index.html', 
                         companies=ALL_COMPANIES,
                         user=user,
                         now=datetime.now().strftime("%Y-%m-%d %H:%M"))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        if username in users:
            return "❌ Пользователь уже существует! <a href='/login'>Войти</a>"
        
        users[username] = hashlib.sha256(password.encode()).hexdigest()
        save_users(users)
        return "✅ Регистрация успешна! <a href='/login'>Войти</a>"
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        if username in users and users[username] == hashlib.sha256(password.encode()).hexdigest():
            session['user'] = username
            return redirect('/')
        return "❌ Неверный логин или пароль!"
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/compare', methods=['GET', 'POST'])
def compare():
    user = session.get('user')
    if not user:
        return redirect('/login')
    
    if request.method == 'POST':
        main_company = request.form.get('main_company')
        company2 = request.form.get('company2')
        
        if not main_company or not company2:
            return "Выберите все компании", 400
        
        data_main = INSURANCE_DATA.get(main_company, {})
        data_comp = INSURANCE_DATA.get(company2, {})
        
        advantages = []
        total_main = data_main.get("total_loss", "0%").replace("%", "")
        total_comp = data_comp.get("total_loss", "0%").replace("%", "")
        if total_main.isdigit() and total_comp.isdigit():
            if int(total_main) > int(total_comp):
                advantages.append(f"✅ {main_company} лучше по порогу тотала: {total_main}% vs {total_comp}%")
        
        return render_template('result.html',
                             company1=main_company,
                             company2=company2,
                             main_company=main_company,
                             data1=data_main,
                             data2=data_comp,
                             advantages=advantages,
                             timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    return render_template('compare_form.html', companies=ALL_COMPANIES)

# ==================== ЗАПУСК ====================
# НЕ ДОБАВЛЯЙ app.run() — Render запускает сам!
