import os, json, requests
from datetime import datetime, timedelta, timezone

WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BASE = "https://hst-api.wialon.com/wialon/ajax.html"
RES_ID, TEMPLATE_ID, GROUP_ID = 29957134, 13, 29960488

def tg(t):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": t[:4000]})
def call(svc, params, sid):
    return requests.get(BASE, params={"svc": svc, "params": json.dumps(params), "sid": sid}, timeout=120).json()

sid = requests.get(BASE, params={"svc":"token/login","params":'{"token":"%s"}'%WIALON_TOKEN}, timeout=60).json()["eid"]
tz = timezone(timedelta(hours=5)); now = datetime.now(tz)
start = int((now - timedelta(days=5)).replace(hour=0,minute=0,second=0).timestamp()); end = int(now.timestamp())

call("report/cleanup_result", {}, sid)
rep = call("report/exec_report", {"reportResourceId":RES_ID,"reportTemplateId":TEMPLATE_ID,
    "reportObjectId":GROUP_ID,"reportObjectSecId":0,"interval":{"from":start,"to":end,"flags":0}}, sid)
tables = rep["reportResult"]["tables"]

def cell(c):
    return str(c.get("t","")) if isinstance(c,dict) else str(c)

# Для каждой таблицы: раскрываем ТОЛЬКО уровень 1 (строки), без трека (unitInfo=0)
for idx, t in enumerate(tables):
    label = t.get("label","?")
    rows = call("report/select_result_rows", {"tableIndex":idx,
        "config":{"type":"range","data":{"from":0,"to":500,"level":1,"unitInfo":0}}}, sid)
    if not isinstance(rows, list):
        tg(f"=== {label}: нет строк ({str(rows)[:100]})"); continue
    out = [f"=== [{idx}] {label} | колонки: " + " | ".join(t.get("header",[]))]
    cnt = 0
    for r in rows:
        # r['c'] = ячейки строки-машины; вложенные заправки в r может не быть при level1
        cells = r.get("c",[])
        vals = [cell(c) for c in cells]
        out.append(" | ".join(vals)[:250])
        cnt += 1
        if cnt >= 25: 
            out.append(f"...ещё {len(rows)-25} строк"); break
    tg("\n".join(out))
