import os, json, requests
from datetime import datetime, timedelta, timezone

WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BASE = "https://hst-api.wialon.com/wialon/ajax.html"
RES_ID, GROUP_ID = 29957134, 29960488

def tg(t):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": t[:4000]})
def call(svc, params, sid):
    return requests.get(BASE, params={"svc": svc, "params": json.dumps(params), "sid": sid}, timeout=120).json()
def cell(c):
    return str(c.get("t","")) if isinstance(c,dict) else str(c)

sid = requests.get(BASE, params={"svc":"token/login","params":'{"token":"%s"}'%WIALON_TOKEN}, timeout=60).json()["eid"]
tz = timezone(timedelta(hours=5)); now = datetime.now(tz)
start = int((now - timedelta(days=5)).replace(hour=0,minute=0,second=0).timestamp()); end = int(now.timestamp())

# пробуем шаблон 12 (ARU_ANALYTICS без "группа")
call("report/cleanup_result", {}, sid)
rep = call("report/exec_report", {"reportResourceId":RES_ID,"reportTemplateId":12,
    "reportObjectId":GROUP_ID,"reportObjectSecId":0,"interval":{"from":start,"to":end,"flags":0}}, sid)

if "reportResult" not in rep:
    tg(f"❌ tid=12 не выполнился: {json.dumps(rep)[:500]}")
else:
    tables = rep["reportResult"]["tables"]
    tg("ШАБЛОН 12 — таблицы:\n" + "\n".join(f"[{i}] {t.get('label')} строк:{t.get('rows')}" for i,t in enumerate(tables)))
    # верхний уровень первой таблицы
    top = call("report/get_result_rows", {"tableIndex":0,"indexFrom":0,"indexTo":50}, sid)
    out = [f"[0] {tables[0].get('label')} | колонки: " + " | ".join(tables[0].get("header",[])), f"верхних строк: {len(top)}"]
    for r in top[:15]:
        out.append(f"[детей={r.get('rows',0)}] " + " | ".join(cell(c) for c in r.get('c',[]))[:200])
    tg("\n".join(out))
