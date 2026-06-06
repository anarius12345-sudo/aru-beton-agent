import os, json, requests
from datetime import datetime, timedelta, timezone

WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BASE = "https://hst-api.wialon.com/wialon/ajax.html"

RES_ID = 29957134
TEMPLATE_ID = 13
GROUP_ID = 29960488

def tg(text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": text[:4000]})

def call(svc, params, sid):
    return requests.get(BASE, params={"svc": svc, "params": json.dumps(params), "sid": sid}, timeout=120).json()

login = requests.get(BASE, params={"svc": "token/login", "params": '{"token":"%s"}' % WIALON_TOKEN}, timeout=60).json()
sid = login["eid"]

tz = timezone(timedelta(hours=5))
now = datetime.now(tz)
start = int((now - timedelta(days=5)).replace(hour=0, minute=0, second=0).timestamp())
end = int(now.timestamp())

call("report/cleanup_result", {}, sid)
r = call("report/exec_report", {
    "reportResourceId": RES_ID, "reportTemplateId": TEMPLATE_ID,
    "reportObjectId": GROUP_ID, "reportObjectSecId": 0,
    "interval": {"from": start, "to": end, "flags": 0}
}, sid)

def read_rows(table_index, label):
    rows = call("report/get_result_rows", {"tableIndex": table_index, "indexFrom": 0, "indexTo": 1000}, sid)
    out = [f"=== {label} (таблица {table_index}) ==="]
    if not isinstance(rows, list):
        out.append(f"нет строк: {str(rows)[:200]}")
        return "\n".join(out)
    out.append(f"строк верхнего уровня: {len(rows)}")
    for row in rows[:8]:
        cells = row.get("c", [])
        vals = []
        for c in cells:
            vals.append(str(c.get("t", "")) if isinstance(c, dict) else str(c))
        # есть ли вложенные (раскрытие по заправкам внутри машины)
        nested = row.get("rows", 0)
        out.append(f"[{nested} внутр.] " + " | ".join(vals)[:280])
    return "\n".join(out)

tg(read_rows(0, "Заправки"))
