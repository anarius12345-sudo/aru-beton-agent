import os, json, requests
from datetime import datetime, timedelta, timezone
WT=os.environ.get("WIALON_TOKEN"); BOT=os.environ.get("TELEGRAM_BOT_TOKEN"); CHAT=os.environ.get("TELEGRAM_CHAT_ID")
BASE="https://hst-api.wialon.com/wialon/ajax.html"; RES,GRP=29957134,29960488
def tg(t): requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",data={"chat_id":CHAT,"text":t[:4000]})
def call(s,p,sid): return requests.get(BASE,params={"svc":s,"params":json.dumps(p),"sid":sid},timeout=120).json()
def cl(c): return str(c.get("t","")) if isinstance(c,dict) else str(c)
sid=requests.get(BASE,params={"svc":"token/login","params":'{"token":"%s"}'%WT},timeout=60).json()["eid"]
tz=timezone(timedelta(hours=5));now=datetime.now(tz)
st=int((now-timedelta(days=5)).replace(hour=0,minute=0,second=0).timestamp());en=int(now.timestamp())
call("report/cleanup_result",{},sid)
call("report/exec_report",{"reportResourceId":RES,"reportTemplateId":13,"reportObjectId":GRP,"reportObjectSecId":0,"interval":{"from":st,"to":en,"flags":0}},sid)

# СПОСОБ A: range level 2
a=call("report/select_result_rows",{"tableIndex":0,"config":{"type":"range","data":{"from":0,"to":40,"level":2,"unitInfo":1}}},sid)
out=["СПОСОБ range/level2:"]
if isinstance(a,list):
    out.append(f"строк: {len(a)}")
    for r in a[:12]:
        c=[cl(x) for x in r.get("c",[])]
        out.append(("["+str(r.get('level','?'))+"] "+" | ".join(c))[:200])
else:
    out.append("не список: "+str(a)[:200])
tg("\n".join(out)[:4000])
