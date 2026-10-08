from __future__ import annotations
import json, os, re, time
from pathlib import Path
import requests
import fitz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "local-casco-analysis"
OUT.mkdir(parents=True, exist_ok=True)
MODEL = os.getenv("LOCAL_CASCO_MODEL", "gpt-5-mini")
BASE = os.environ["OPENAI_API_BASE"].rstrip("/")
KEY = os.environ["OPENAI_API_KEY"]

QUESTIONS = {
    "franchise": "Какие виды франшизы предусмотрены? Как определяется размер, когда применяется и от чего зависит?",
    "without_certificates": "Для каких повреждений разрешена выплата без документов компетентных органов? Укажи лимит, количество обращений, исключения и условия.",
    "gap": "Предусмотрено ли возмещение разницы из-за уменьшения стоимости автомобиля (GAP)? При каких событиях и как отдельная опция или часть покрытия?",
    "total_loss": "Как определяется полная гибель автомобиля? Укажи процент, базу расчёта, сравнение и возможность иного порога по договору.",
    "self_ignition": "Как урегулируется повреждение при самовозгорании без внешнего воздействия? Проанализируй определение пожара и исключения внутренних неисправностей.",
    "terrorism": "Как урегулируется ущерб от террористического акта? Если прямо не назван, различи противоправные действия третьих лиц, поджог, подрыв и исключения.",
    "drone": "Как происходит выплата при повреждении БПЛА или его обломками? Если прямо не назван, анализируй падение предметов, противоправные действия и исключения.",
    "tow_truck": "Когда оплачивается эвакуация автомобиля, куда, с каким лимитом или расстоянием? Нужны ли согласование и невозможность движения своим ходом?",
    "repair_type": "Какие формы возмещения доступны: деньги, ремонт на СТОА страховщика, страхователя или дилера? Кто выбирает и какие ограничения?",
    "payment_terms": "Каков срок выплаты или выдачи направления на ремонт, с какого события отсчитывается? Различай рабочие/календарные дни, выплату/рассмотрение и основания продления.",
}
KEYWORDS = {
    "franchise": ["франшиз"], "without_certificates": ["без документов", "без справ", "компетентн", "извещенн"],
    "gap": ["gap", "гэп", "уменьш", "стоимост"], "total_loss": ["полная гибел", "тоталь", "конструктивн"],
    "self_ignition": ["самовозгорани", "пожар", "возгорани", "внутренн"], "terrorism": ["террорист", "терроризм", "подрыв", "поджог"],
    "drone": ["беспилот", "бпла", "дрон", "летательн", "падени"], "tow_truck": ["эвакуац", "эвакуатор", "буксиров"],
    "repair_type": ["стоа", "ремонт", "денежн", "направлени"], "payment_terms": ["срок выплат", "дней", "рабочих дней", "календарн"],
}
SLUGS = ["reso", "vsk", "ingos", "renins", "alfa", "soglasie", "rgs", "t-insurance", "sber", "sovcom", "yugoria"]
NAMES = {"reso":"РЕСО-Гарантия", "vsk":"ВСК", "ingos":"Ингосстрах", "renins":"Ренессанс Страхование", "alfa":"АльфаСтрахование", "soglasie":"Согласие", "rgs":"Росгосстрах", "t-insurance":"Т-Страхование", "sber":"СберСтрахование", "sovcom":"Совкомбанк Страхование", "yugoria":"Югория"}

SCHEMA = {"type":"object", "properties": {k:{"type":"object", "properties": {"value":{"type":["string","null"]},"status":{"type":"string","enum":["answered","partial","not_found"]},"quote":{"type":["string","null"]},"page":{"type":["integer","null"]},"reason":{"type":"string"}}, "required":["value","status","quote","page","reason"],"additionalProperties":False} for k in QUESTIONS}, "required":list(QUESTIONS), "additionalProperties":False}

def snippets(pdf: Path) -> str:
    doc = fitz.open(pdf)
    pages = []
    for n, page in enumerate(doc, 1):
        text = page.get_text("text") or ""
        low = text.lower()
        score = sum(1 for words in KEYWORDS.values() for w in words if w in low)
        if score:
            pages.append((score, n, re.sub(r"\s+", " ", text).strip()))
    pages.sort(key=lambda x: (-x[0], x[1]))
    chosen = pages[:28]
    # Keep enough context for 10 questions, but remain safely below proxy limits.
    chosen.sort(key=lambda x: x[1])
    result=[]; total=0
    for _, n, text in chosen:
        chunk = text[:2200]
        if total + len(chunk) > 26000: break
        result.append(f"[СТРАНИЦА {n}] {chunk}")
        total += len(chunk)
    return "\n".join(result)

def call(slug, pdf, context):
    prompt = f"""Ты анализируешь официальный технический документ КАСКО страховщика {NAMES[slug]}. Документ — единственный источник. Ответь по всем вопросам сразу в JSON по схеме. Пиши кратко и понятно по-русски, но сохраняй проценты, лимиты, сроки, исключения и зависимость от договора. Если документ не позволяет сделать однозначный вывод, status=partial или not_found и объясни почему. quote должна быть дословным фрагментом из контекста, page — его страница. Не выдумывай информацию и не используй внешние знания.\n\nВОПРОСЫ:\n""" + "\n".join(f"{k}: {q}" for k,q in QUESTIONS.items()) + "\n\nКОНТЕКСТ ДОКУМЕНТА:\n" + context
    prompt += "\nВерни только корректный JSON-объект без markdown-ограждения."
    body = {"model":MODEL,"messages":[{"role":"user","content":prompt}],"response_format":{"type":"json_object"},"max_completion_tokens":12000}
    r=requests.post(BASE+"/chat/completions",headers={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"},json=body,timeout=(20,600))
    r.raise_for_status()
    payload = r.json()
    if "choices" not in payload:
        raise RuntimeError("LLM proxy response has no choices: " + json.dumps(payload, ensure_ascii=False)[:600])
    content=payload["choices"][0]["message"]["content"]
    return json.loads(content)

def main():
    all_results={}; errors=[]
    for slug in SLUGS:
        pdf=ROOT/"data"/"sources"/slug/"technical.pdf"
        if not pdf.exists(): errors.append({"insurer":slug,"reason":"technical.pdf missing"}); continue
        print(f"ANALYZE {slug} {pdf.stat().st_size} bytes", flush=True)
        try:
            ctx=snippets(pdf)
            result=call(slug,pdf,ctx)
            all_results[slug]={"insurer":NAMES[slug],"pdf":str(pdf.relative_to(ROOT)),"model":MODEL,"answers":result}
            print(f"DONE {slug}", flush=True)
        except Exception as e:
            errors.append({"insurer":slug,"reason":type(e).__name__+": "+str(e)[:300]})
            print(f"ERROR {slug} {errors[-1]['reason']}", flush=True)
        time.sleep(1)
    report={"model":MODEL,"questions":QUESTIONS,"results":all_results,"errors":errors,"request_count":len(all_results)}
    (OUT/"analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# Первичный анализ эталонных PDF КАСКО", "", f"Модель: `{MODEL}`; запросов: **{len(all_results)}**", ""]
    for slug, item in all_results.items():
        lines += [f"## {item['insurer']}", f"Источник: `{item['pdf']}`", "", "| Поле | Ответ | Статус | Страница |", "|---|---|---|---|"]
        for key, ans in item["answers"].items():
            value=(ans.get("value") or ans.get("answer") or "Нет однозначного ответа").replace("|","\\|").replace("\n"," ")
            status = ans.get("status")
            if status == "found": status = "answered"
            lines.append(f"| {key} | {value} | {status} | {ans.get('page') or '—'} |")
        lines.append("")
    if errors:
        lines += ["## Ошибки", ""] + [f"- {e['insurer']}: {e['reason']}" for e in errors]
    (OUT/"comparison.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"REPORT {OUT/'comparison.md'}", flush=True)

if __name__ == "__main__": main()
