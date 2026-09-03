import json
import os
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

CACHE_FILE = "insurance_cache.json"

# ==================== БАЗОВЫЕ ДАННЫЕ С ИСТОЧНИКАМИ ====================

def get_fallback_data():
    return {
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
            "offices": "1200+",
            "_sources_detail": {
                "total_loss": "Уровень 1 (Официальный сайт: https://www.reso.ru/Avto/Kasko/)",
                "payment_terms": "Уровень 1 (Официальный сайт: https://www.reso.ru/Avto/Kasko/)",
                "franchise": "Уровень 7 (Встроенная база / Fallback)",
                "without_certificates": "Уровень 7 (Встроенная база / Fallback)"
            }
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
            "offices": "500+",
            "_sources_detail": {
                "total_loss": "Уровень 1 (Официальный сайт: https://www.sogaz.ru/kasko/)",
                "payment_terms": "Уровень 1 (Официальный сайт: https://www.sogaz.ru/kasko/)",
                "franchise": "Уровень 7 (Встроенная база / Fallback)",
                "without_certificates": "Уровень 7 (Встроенная база / Fallback)"
            }
        },
        "АльфаСтрахование": {
            "franchise": "Условно-безусловная (применяется к Хищению)",
            "without_certificates": "Стекла без ограничений + 1 кузовной элемент 2 раза в год",
            "gap": "Включен по умолчанию",
            "total_loss": "75%",
            "fire": "За доп. плату, 0,8% от СС",
            "terrorism": "За доп. плату, 0,2-0,3% от СС",
            "drone": "За доп. плату",
            "tow_truck": "Легковые ТС - 5 000 руб.; Прочие - 10 000 руб.",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "7 рабочих дней",
            "advantages": "Без справок с бонусами",
            "weak_points": "Франшиза на Хищение, самовозгорание - за доп. плату",
            "rating": "4.6",
            "offices": "600+",
            "_sources_detail": {
                "total_loss": "Уровень 1 (Официальный сайт: https://www.alfastrah.ru/auto/kasko/)",
                "payment_terms": "Уровень 1 (Официальный сайт: https://www.alfastrah.ru/auto/kasko/)",
                "franchise": "Уровень 7 (Встроенная база / Fallback)"
            }
        },
        "Ингосстрах": {
            "franchise": "Условная/условно-безусловная по каждому случаю или со 2-го случая",
            "without_certificates": "1 раз в год: ЛКП не более 1-й детали; остекление кузова",
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
            "offices": "900+",
            "_sources_detail": {
                "total_loss": "Уровень 1 (Официальный сайт: https://www.ingos.ru/auto/kasko)",
                "payment_terms": "Уровень 1 (Официальный сайт: https://www.ingos.ru/auto/kasko)",
                "franchise": "Уровень 7 (Встроенная база / Fallback)"
            }
        }
    }

OFFICIAL_SOURCES = {
    "РЕСО-Гарантия": ["https://www.reso.ru/Avto/Kasko/"],
    "Ингосстрах": ["https://www.ingos.ru/auto/kasko"],
    "АльфаСтрахование": ["https://www.alfastrah.ru/auto/kasko/"],
    "СОГАЗ": ["https://www.sogaz.ru/kasko/"]
}

def load_or_update_data():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    
    data = get_fallback_data()
    data["_last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return data

INSURANCE_DATA = load_or_update_data()
ALL_COMPANIES = list(get_fallback_data().keys())

# ==================== МАРШРУТЫ И ЛОГИРОВАНИЕ ====================

@app.route('/', methods=['GET', 'POST'])
def index():
    last_updated = INSURANCE_DATA.get("_last_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))
    return render_template(
        'index.html', 
        companies=ALL_COMPANIES, 
        last_updated=last_updated
    )

@app.route('/compare', methods=['GET', 'POST'])
def compare():
    if request.method == 'GET':
        return redirect(url_for('index'))

    company1 = request.form.get('company1')
    company2 = request.form.get('company2')
    
    if not company1 or not company2:
        return redirect(url_for('index'))
    
    data1 = INSURANCE_DATA.get(company1, {})
    data2 = INSURANCE_DATA.get(company2, {})

    # === ВЫВОД ИСТОЧНИКОВ В ЛОГИ RENDER ===
    print("\n" + "="*50)
    print(f"📊 [LOG] СРАВНЕНИЕ: {company1} VS {company2}")
    print("="*50)
    
    print(f"📍 ИСТОЧНИКИ ДЛЯ {company1}:")
    sources1_detail = data1.get("_sources_detail", {})
    if sources1_detail:
        for field, src in sources1_detail.items():
            print(f"   • [{field}]: {src}")
    else:
        print("   • Данные взяты из базы Уровня 7 (Fallback)")

    print(f"\n📍 ИСТОЧНИКИ ДЛЯ {company2}:")
    sources2_detail = data2.get("_sources_detail", {})
    if sources2_detail:
        for field, src in sources2_detail.items():
            print(f"   • [{field}]: {src}")
    else:
        print("   • Данные взяты из базы Уровня 7 (Fallback)")
    print("="*50 + "\n")
    # ======================================

    advantages = []

    m1 = re.search(r'\d+', str(data1.get("total_loss", "")))
    m2 = re.search(r'\d+', str(data2.get("total_loss", "")))
    if m1 and m2:
        v1, v2 = int(m1.group()), int(m2.group())
        if v1 > v2:
            advantages.append(f"✅ {company1} имеет более высокий порог тотала: {v1}% против {v2}% у {company2}")
        elif v2 > v1:
            advantages.append(f"✅ {company2} имеет более высокий порог тотала: {v2}% против {v1}% у {company1}")

    pm1 = re.search(r'\d+', str(data1.get("payment_terms", "")))
    pm2 = re.search(r'\d+', str(data2.get("payment_terms", "")))
    if pm1 and pm2:
        pv1, pv2 = int(pm1.group()), int(pm2.group())
        if pv1 < pv2:
            advantages.append(f"⚡ {company1} быстрее выплачивает возмещение: {pv1} дней против {pv2} дней у {company2}")
        elif pv2 < pv1:
            advantages.append(f"⚡ {company2} быстрее выплачивает возмещение: {pv2} дней против {pv1} дней у {company1}")

    sources1 = OFFICIAL_SOURCES.get(company1, ["Официальный сайт " + company1])
    sources2 = OFFICIAL_SOURCES.get(company2, ["Официальный сайт " + company2])
    last_updated = INSURANCE_DATA.get("_last_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))

    return render_template(
        'result.html', 
        company1=company1, 
        company2=company2, 
        data1=data1, 
        data2=data2, 
        advantages=advantages, 
        sources1=sources1,
        sources2=sources2,
        last_updated=last_updated,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
