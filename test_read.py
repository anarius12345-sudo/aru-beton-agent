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

top=call("report/get_result_rows",{"tableIndex":0,"indexFrom":0,"indexTo":50},sid)
out=[f"дат верхнего уровня: {len(top) if isinstance(top,list) else '?'}"]
# берём первую дату с детьми и пробуем get_result_subrows
for di,r in enumerate(top if isinstance(top,list) else []):
    if r.get("rows",0)>0:
        out.append(f"строка {di}: детей={r.get('rows')}")
        sub=call("report/get_result_subrows",{"tableIndex":0,"rowIndex":di,"indexFrom":0,"indexTo":30},sid)
        out.append("get_result_subrows -> "+("список "+str(len(sub)) if isinstance(sub,list) else str(sub)[:150]))
        if isinstance(sub,list):
            for s in sub[:6]:
                c=[cl(x) for x in s.get("c",[])]
                out.append("  "+" | ".join(c)[:180])
        break
tg("\n".join(out)[:4000])
