import os, json, requests
from datetime import datetime, timedelta, timezone
WIALON_TOKEN=os.environ.get("WIALON_TOKEN"); BOT=os.environ.get("TELEGRAM_BOT_TOKEN"); CHAT=os.environ.get("TELEGRAM_CHAT_ID")
BASE="https://hst-api.wialon.com/wialon/ajax.html"; RES,GRP=29957134,29960488
def tg(t): requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",data={"chat_id":CHAT,"text":t[:4000]})
def call(s,p,sid): return requests.get(BASE,params={"svc":s,"params":json.dumps(p),"sid":sid},timeout=120).json()
def cl(c): return str(c.get("t","")) if isinstance(c,dict) else str(c)
sid=requests.get(BASE,params={"svc":"token/login","params":'{"token":"%s"}'%WIALON_TOKEN},timeout=60).json()["eid"]
tz=timezone(timedelta(hours=5)); now=datetime.now(tz)
st=int((now-timedelta(days=5)).replace(hour=0,minute=0,second=0).timestamp()); en=int(now.timestamp())
call("report/cleanup_result",{},sid)
call("report/exec_report",{"reportResourceId":RES,"reportTemplateId":13,"reportObjectId":GRP,"reportObjectSecId":0,"interval":{"from":st,"to":en,"flags":0}},sid)
# раскрываем УРОВЕНЬ 2
rows=call("report/select_result_rows",{"tableIndex":0,"config":{"type":"range","data":{"from":0,"to":3000,"level":2,"unitInfo":1}}},sid)
out=["УРОВЕНЬ 2:"]; sh=0
for r in rows if isinstance(rows,list) else []:
    c=[cl(x) for x in r.get("c",[])]
    if not c: continue
    # пропускаем строки-даты и пустые
    if "----" in c[0]: continue
    out.append("• "+" ║ ".join(f"[{i}]{v}" for i,v in enumerate(c))[:330]); sh+=1
    if sh>=10: break
tg("\n".join(out)[:4000])
