import os, json, requests
from datetime import datetime, timedelta, timezone

WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BASE = "https://hst-api.wialon.com/wialon/ajax.html"
RES_ID, TEMPLATE_ID, GROUP_ID = 29957134, 13, 29960488

def tg(text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": text[:4000]})
def call(svc, params, sid):
    return requests.get(BASE, params={"svc": svc, "params": json.dumps(params), "sid": sid}, timeout=120).json()

sid = requests.get(BASE, params={"svc":"token/login","params":'{"token":"%s"}'%WIALON_TOKEN}, timeout=60).json()["eid"]
tz = timezone(timedelta(hours=5)); now = datetime.now(tz)
start = int((now - timedelta(days=5)).replace(hour=0,minute=0,second=0).timestamp()); end = int(now.timestamp())

call("report/cleanup_result", {}, sid)
call("report/exec_report", {"reportResourceId":RES_ID,"reportTemplateId":TEMPLATE_ID,
    "reportObjectId":GROUP_ID,"reportObjectSecId":0,"interval":{"from":start,"to":end,"flags":0}}, sid)

# верхний уровень таблицы 0 (Заправки) — машины
top = call("report/get_result_rows", {"tableIndex":0,"indexFrom":0,"indexTo":100}, sid)
out = [f"ВЕРХ (машины): {len(top)} строк"]
for i, row in enumerate(top[:8]):
    name = row.get("c",[{}])[0]
    name = name.get("t","") if isinstance(name,dict) else name
    out.append(f"#{i} '{name}' детей={row.get('rows',0)}")
tg("\n".join(out))

# раскрываем первую машину с детьми
for i, row in enumerate(top):
    if row.get("rows",0) > 0:
        child = call("report/select_result_rows", {"tableIndex":0,"config":{"type":"range","data":{"from":0,"to":50,"level":1,"unitInfo":1}}}, sid)
        nm = row.get("c",[{}])[0]; nm = nm.get("t","") if isinstance(nm,dict) else nm
        lines = [f"ДЕТИ машины '{nm}':"]
        rows2 = child if isinstance(child, list) else child.get("rows", [])
        for c in (rows2[:6] if isinstance(rows2, list) else []):
            cells = c.get("c", [])
            vals = [str(x.get("t","")) if isinstance(x,dict) else str(x) for x in cells]
            lines.append(" | ".join(vals)[:280])
        tg("\n".join(lines)[:4000])
        break
