from flask import Flask, render_template, request, session, redirect, url_for
from datetime import datetime
import json
import os
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ==================== ДАННЫЕ ====================
INSURANCE_DATA = {
    "РЕСО-Гарантия": {
        "franchise": "Безусловная / условно-безусловная (с 1-го или со 2-го случая)",
        "without_certificates": "Стекла без ограничений; 1 кузовной элемент в год",
        "gap": "Отдельный риск",
        "total_loss": "75%",
        "fire": "Входит",
        "terrorism": "Входит",
        "drone": "Лимит 1% СС",
        "tow_truck": "Лимит 1% СС",
        "repair_type": "Ремонт у официального дилера",
        "payment_terms": "5 рабочих дней",
        "advantages": "Ремонт у дилера, 5 дней на выплату, без учета износа",
        "weak_points": "Требуется уточнение условий по телефону",
        "rating": "4.5",
        "offices": "1200+"
    },
    "СОГАЗ": {
        "franchise": "Безусловная / условно-безусловная / динамическая",
        "without_certificates": "Вариантно: 1 раз один элемент / Неограниченно стекла + 1 раз кузовной",
        "gap": "Указывается отдельным риском",
        "total_loss": "70%",
        "fire": "Входит",
        "terrorism": "Исключение",
        "drone": "Исключение",
        "tow_truck": "Лимит 0,5% от СС",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "30 рабочих дней",
        "advantages": "Гибкие условия, надёжность",
        "weak_points": "Тотал 70%, срок выплаты 30 дней",
        "rating": "4.3",
        "offices": "500+"
    },
    "АльфаСтрахование": {
        "franchise": "Условно-безусловная (применяется к Хищению)",
        "without_certificates": "Стекла без ограничений + 1 кузовной элемент 2 раза в год",
        "gap": "Включен по умолчанию",
        "total_loss": "75%",
        "fire": "За доп. плату, 0,8% от СС",
        "terrorism": "За доп. плату, 0,2-0,3% от СС",
        "drone": "За доп. плату",
        "tow_truck": "Петковые ТС - 5 000 руб.; Прочие - 10 000 руб.",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "7 рабочих дней",
        "advantages": "Без справок с бонусами",
        "weak_points": "Франшиза действует на Хищение, самовозгорание - за доп. плату",
        "rating": "4.6",
        "offices": "600+"
    },
    "Ингосстрах": {
        "franchise": "Условная/условно-безусловная по каждому случаю или со 2-го случая",
        "without_certificates": "1 раз в год: ЛПКП не более 1-й детали; остекление кузова",
        "gap": "Включен при отметке «Постоянная страховая сумма»",
        "total_loss": "75%",
        "fire": "Входит",
        "terrorism": "За доп. плату, 0,3%",
        "drone": "За доп. плату",
        "tow_truck": "По запросу",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "10 рабочих дней",
        "advantages": "Широкая сеть офисов, гибкие условия",
        "weak_points": "Без справок – только ЛКП 1 детали, возможны ограничения по пробегу",
        "rating": "4.4",
        "offices": "900+"
    },
    "Ренессанс": {
        "franchise": "11 видов франшиз (безусловная, франшиза виновника, со 2-го случая)",
        "without_certificates": "Вариативно (стекла 1 раз в год / без ограничений / до 5% СС 2 раза)",
        "gap": "Отдельный риск",
        "total_loss": "75%",
        "fire": "Только для электромобилей",
        "terrorism": "За доп. плату, 0,5% от СС на легковые ТС",
        "drone": "За доп. плату, 0,5% от СС на легковые",
        "tow_truck": "Петковые ТС - лимит 10 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Много вариантов франшизы, гибкие условия",
        "weak_points": "Франшиза по хищению/угону, эвакуация - за доп. плату",
        "rating": "4.3",
        "offices": "500+"
    },
    "Т-Страхование": {
        "franchise": "Условно-безусловная (для ТС старше 5 лет - обязательные франшизы)",
        "without_certificates": "Стекла: неогранич. кол-во раз; Кузовные элементы: 1 раз в год - до 3% от СС",
        "gap": "Отдельный риск",
        "total_loss": "65%",
        "fire": "Нет инф.",
        "terrorism": "Нет инф.",
        "drone": "Нет инф.",
        "tow_truck": "Лимит 10 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "5 рабочих дней",
        "advantages": "Онлайн-оформление, без справок",
        "weak_points": "Ниже порог тотала, обязательные франшизы для некоторых сегментов",
        "rating": "4.7",
        "offices": "онлайн"
    },
    "ВСК": {
        "franchise": "Условно-безусловная (может не применяться по отдельным рискам)",
        "without_certificates": "Стекла: 5% СС (неагрегатная); Прочие элементы: 3% СС (агрегатная)",
        "gap": "Включен, если указан 1 период страхования (1 год)",
        "total_loss": "75%",
        "fire": "Исключение из страхового покрытия",
        "terrorism": "Исключение из страхового покрытия",
        "drone": "Включен при наличии в полисе GAP и отметки официальный дилер",
        "tow_truck": "Петковые ТС - лимит 5 000 руб.; Прочие - лимит 15 000 руб.",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия по справкам",
        "weak_points": "Камеры кругового обзора не оплачиваются без справок, самовозгорание - исключено",
        "rating": "4.2",
        "offices": "800+"
    },
    "Согласие": {
        "franchise": "Условно-безусловная / динамическая",
        "without_certificates": "Неограниченно стекла (искл. крыша и люк) + 1 раз любой элемент",
        "gap": "В разделе 'Условия страхования' указывается как риск ГЭП",
        "total_loss": "70%",
        "fire": "За доп. плату, 1.15% для ФЛ",
        "terrorism": "За доп. плату, тариф 1.1% только для МСК и МО",
        "drone": "За доп. плату",
        "tow_truck": "5 000 руб. (до 3,5 т); 10 000 руб. (свыше 3,5 т)",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия",
        "weak_points": "Тотал 70% (РЕСО 75%), эвакуатор 5 000 руб. (ниже РЕСО)",
        "rating": "4.2",
        "offices": "300+"
    },
    "Югория": {
        "franchise": "Условно-безусловная (при пролонгации - 3% от СС на каждый случай)",
        "without_certificates": "Стекла: 1 раз (исключая панорамную крышу)",
        "gap": "По типу страховой суммы: неагрегатная - изменяющаяся",
        "total_loss": "Не указан",
        "fire": "Исключение из покрытия",
        "terrorism": "Нет инф.",
        "drone": "Входит",
        "tow_truck": "Лимит 5% от СС, но не более 15 000 рублей",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия пролонгации",
        "weak_points": "При пролонгации возможна доп. франшиза, самовозгорание исключено",
        "rating": "3.9",
        "offices": "400+"
    },
    "СберСтрахование": {
        "franchise": "6 видов франшиз (условная, безусловная, динамическая, со 2-го случая, агрегатная)",
        "without_certificates": "Вариантно: 1 раз - 1 деталь кузова + стекла / Только стекла",
        "gap": "Включен, если СС индексируемая",
        "total_loss": "70%",
        "fire": "Исключение",
        "terrorism": "Исключение",
        "drone": "Исключение",
        "tow_truck": "Петковые ТС - 6 000 руб.; Грузовые - 12 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "7 рабочих дней",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Тотал 70% (РЕСО 75%), аваром/эвакуация могут быть исключены",
        "rating": "4.0",
        "offices": "1000+"
    },
    "Совкомбанк Страхование": {
        "franchise": "Условно-безусловная / Условная по отдельным группам / Обязательная 25%",
        "without_certificates": "Только ремонт или замена ветрового стекла",
        "gap": "Нет инф.",
        "total_loss": "75%",
        "fire": "Входит в группу событий №2",
        "terrorism": "Исключение",
        "drone": "Исключение",
        "tow_truck": "Лимит 6 500 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Группы событий",
        "weak_points": "Терроризм исключен, обязательная франшиза",
        "rating": "3.8",
        "offices": "200+"
    }
}

ALL_COMPANIES = list(INSURANCE_DATA.keys())
USERS_FILE = "users.json"

def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

@app.route('/')
def index():
    user = session.get('user')
    return render_template('index.html', companies=ALL_COMPANIES, user=user, now=datetime.now().strftime("%Y-%m-%d %H:%M"))

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
            return "❌ Выберите обе компании!"
        
        data1 = INSURANCE_DATA.get(main_company, {})
        data2 = INSURANCE_DATA.get(company2, {})
        
        advantages = []
        total1 = data1.get("total_loss", "0%").replace("%", "")
        total2 = data2.get("total_loss", "0%").replace("%", "")
        if total1.isdigit() and total2.isdigit():
            if int(total1) > int(total2):
                advantages.append(f"✅ {main_company} лучше по порогу тотала: {total1}% vs {total2}%")
        
        return render_template('result.html',
                             company1=main_company,
                             company2=company2,
                             main_company=main_company,
                             data1=data1,
                             data2=data2,
                             advantages=advantages,
                             timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    return render_template('compare_form.html', companies=ALL_COMPANIES)

@app.route('/payment')
def payment():
    return render_template('payment.html', user=session.get('user'))

# ==================== ШАБЛОНЫ ====================
os.makedirs('templates', exist_ok=True)

with open('templates/index.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Сравнение КАСКО</title>
<style>
body{font-family:Arial;padding:10px;background:#f5f5f5}
.container{max-width:500px;margin:0 auto;background:white;padding:20px;border-radius:10px}
h1{font-size:20px;text-align:center;color:#2c3e50}
.user-bar{text-align:right;font-size:14px;margin-bottom:15px}
.btn{display:block;width:100%;padding:14px;background:#27ae60;color:white;text-align:center;text-decoration:none;border:none;border-radius:8px;font-size:16px;cursor:pointer;margin:10px 0}
.btn-blue{background:#3498db}
.btn-orange{background:#f39c12}
.status{text-align:center;font-size:14px;padding:10px;border-radius:8px;margin:10px 0}
.status-ok{background:#d5f5e3;color:#27ae60}
.status-no{background:#fadbd8;color:#e74c3c}
.meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
a{color:#3498db;text-decoration:none}
</style>
</head>
<body>
<div class="container">
<div class="user-bar">{% if user %}👤 {{ user }} | <a href="/logout">Выйти</a>{% else %}<a href="/login">Войти</a> | <a href="/register">Регистрация</a>{% endif %}</div>
<h1>🔍 Сравнение КАСКО</h1>
<p style="text-align:center;color:#555;">Сравни страховые компании за 99 ₽</p>
{% if user %}
<div class="status status-ok">✅ Вы вошли как {{ user }}</div>
<a href="/compare" class="btn">📊 Новое сравнение</a>
<a href="/payment" class="btn btn-blue">💳 Оплатить (99 ₽ / 399 ₽)</a>
{% else %}
<div class="status status-no">⚠️ Войдите, чтобы сравнивать</div>
<a href="/login" class="btn btn-blue">🔑 Войти</a>
<a href="/register" class="btn btn-orange">📝 Зарегистрироваться</a>
{% endif %}
<div class="meta">Обновлено: {{ now }}</div>
</div>
</body>
</html>
''')

with open('templates/compare_form.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Сравнение</title>
<style>
body{font-family:Arial;padding:10px;background:#f5f5f5}
.container{max-width:500px;margin:0 auto;background:white;padding:20px;border-radius:10px}
select{width:100%;padding:12px;margin:8px 0;border:1px solid #ddd;border-radius:8px}
.btn{width:100%;padding:14px;background:#27ae60;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}
.vs{text-align:center;font-size:24px;color:#e74c3c;margin:5px 0}
.back{display:inline-block;margin-top:10px;color:#3498db;text-decoration:none}
.label{font-weight:bold;color:#555;display:block;margin-top:10px}
</style>
</head>
<body>
<div class="container">
<h1>📊 Сравнение</h1>
<p style="text-align:center;color:#555;">Выберите основную компанию и вторую для сравнения</p>
<form method="post">
<label class="label">🏆 Основная компания (ваша):</label>
<select name="main_company" required>
<option value="">-- Выберите --</option>{% for c in companies %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
</select>
<div class="vs">⚔️</div>
<label class="label">Компания для сравнения:</label>
<select name="company2" required>
<option value="">-- Выберите --</option>{% for c in companies %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
</select>
<button type="submit" class="btn">Сравнить →</button>
</form>
<a href="/" class="back">← На главную</a>
</div>
</body>
</html>
''')

with open('templates/result.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Результат сравнения</title>
<style>
body{font-family:Arial;padding:10px;background:#f5f5f5}
.container{max-width:600px;margin:0 auto;background:white;padding:20px;border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}
th,td{border:1px solid #ddd;padding:8px;text-align:left}
th{background:#2c3e50;color:white}
.main-badge{background:#27ae60;color:white;padding:3px 10px;border-radius:12px;font-size:12px;margin-left:10px}
.vs-title{text-align:center;font-size:18px;font-weight:bold;margin:10px 0;padding:10px;background:#f0f8ff;border-radius:8px}
.advantage{color:#27ae60}
.back{display:inline-block;margin-top:10px;color:#3498db;text-decoration:none}
.meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
</style>
</head>
<body>
<div class="container">
<h1>📊 Результат сравнения</h1>
<div class="vs-title">🏆 {{ main_company }} <span class="main-badge">ОСНОВНАЯ</span><br>⚔️ {{ company2 }}</div>
<table>
<tr><th>Параметр</th><th>{{ company1 }}</th><th>{{ company2 }}</th></tr>
<tr><td>Франшиза</td><td>{{ data1.franchise or '—' }}</td><td>{{ data2.franchise or '—' }}</td></tr>
<tr><td>Порог тотала</td><td>{{ data1.total_loss or '—' }}</td><td>{{ data2.total_loss or '—' }}</td></tr>
<tr><td>Рейтинг</td><td>{{ data1.rating or '—' }}</td><td>{{ data2.rating or '—' }}</td></tr>
<tr><td>Офисы</td><td>{{ data1.offices or '—' }}</td><td>{{ data2.offices or '—' }}</td></tr>
</table>
<div class="analysis"><strong>📋 Анализ</strong><ul>{% for adv in advantages %}<li class="advantage">✅ {{ adv }}</li>{% endfor %}</ul></div>
<a href="/compare" class="back">← Новое сравнение</a><br>
<a href="/" class="back">На главную</a>
<div class="meta">Обновлено: {{ timestamp }}</div>
</div>
</body>
</html>
''')

with open('templates/register.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Регистрация</title>
<style>body{font-family:Arial;padding:20px;background:#f5f5f5}.container{max-width:400px;margin:0 auto;background:white;padding:20px;border-radius:10px}input{width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:8px}button{width:100%;padding:12px;background:#27ae60;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}a{color:#3498db}</style></head>
<body><div class="container"><h2>Регистрация</h2><form method="post"><input type="text" name="username" placeholder="Имя" required><input type="password" name="password" placeholder="Пароль" required><button type="submit">Зарегистрироваться</button></form><p><a href="/login">Уже есть аккаунт? Войти</a></p></div></body></html>
''')

with open('templates/login.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Вход</title>
<style>body{font-family:Arial;padding:20px;background:#f5f5f5}.container{max-width:400px;margin:0 auto;background:white;padding:20px;border-radius:10px}input{width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:8px}button{width:100%;padding:12px;background:#3498db;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}a{color:#3498db}</style></head>
<body><div class="container"><h2>Вход</h2><form method="post"><input type="text" name="username" placeholder="Имя" required><input type="password" name="password" placeholder="Пароль" required><button type="submit">Войти</button></form><p><a href="/register">Нет аккаунта? Зарегистрироваться</a></p></div></body></html>
''')

with open('templates/payment.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Оплата</title>
<style>body{font-family:Arial;padding:20px;background:#f5f5f5}.container{max-width:400px;margin:0 auto;background:white;padding:20px;border-radius:10px}.btn{display:block;width:100%;padding:14px;margin:10px 0;border:none;border-radius:8px;font-size:16px;cursor:pointer}.btn-green{background:#27ae60;color:white}.btn-blue{background:#3498db;color:white}a{color:#3498db}</style></head>
<body><div class="container"><h2>💳 Оплата</h2><p>Пользователь: {{ user }}</p><form method="post" action="/pay"><button type="submit" name="type" value="single" class="btn btn-green">🔹 Разовое сравнение — 99 ₽</button><button type="submit" name="type" value="subscription" class="btn btn-blue">🔹 Подписка на месяц — 399 ₽</button></form><br><a href="/">На главную</a></div></body></html>
''')
