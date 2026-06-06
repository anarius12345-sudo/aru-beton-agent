import os, json, requests
from datetime import datetime, timedelta, timezone

WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BASE = "https://hst-api.wialon.com/wialon/ajax.html"

RES_ID = 29957134      # ресурс с шаблонами
TEMPLATE_ID = 13       # ARU_ANALYTICS (группа)
GROUP_ID = 29960488    # Все объекты

def tg(text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": text[:4000]})

def call(svc, params, sid):
    return requests.get(BASE, params={"svc": svc, "params": json.dumps(params), "sid": sid}, timeout=120).json()

# вход
login = requests.get(BASE, params={"svc": "token/login", "params": '{"token":"%s"}' % WIALON_TOKEN}, timeout=60).json()
if "eid" not in login:
    tg(f"❌ вход не удался: {login}"); raise SystemExit()
sid = login["eid"]

# период: вчера (по местному времени Алматы = UTC+5)
now = datetime.now(timezone(timedelta(hours=5)))
y = (now - timedelta(days=1)).date()
start = int(datetime(y.year, y.month, y.day, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))).timestamp())
end = int(datetime(y.year, y.month, y.day, 23, 59, 59, tzinfo=timezone(timedelta(hours=5))).timestamp())

# очистить прошлый отчёт
call("report/cleanup_result", {}, sid)

# выполнить отчёт по группе объектов (reportObjectIdList — id группы)
r = call("report/exec_report", {
    "reportResourceId": RES_ID,
    "reportTemplateId": TEMPLATE_ID,
    "reportObjectId": GROUP_ID,
    "reportObjectSecId": 0,
    "interval": {"from": start, "to": end, "flags": 0}
}, sid)

if "reportResult" not in r:
    tg(f"❌ exec_report не дал результата:\n{json.dumps(r)[:1500]}")
    raise SystemExit()

tables = r["reportResult"].get("tables", [])
lines = [f"✅ Отчёт выполнен. Период: {y}", f"Таблиц: {len(tables)}"]
for i, t in enumerate(tables):
    lines.append(f"[{i}] {t.get('label','?')} — строк: {t.get('rows',0)} | колонок: {len(t.get('header',[]))}")

tg("\n".join(lines))

# покажем заголовки первой таблицы с ненулевыми строками
for i, t in enumerate(tables):
    if t.get("rows", 0) > 0:
        tg(f"Таблица [{i}] «{t.get('label')}» колонки:\n" + " | ".join(t.get("header", [])))
        break
