import os, json, requests
from datetime import datetime, timedelta, timezone
WT=os.environ.get("WIALON_TOKEN"); BOT=os.environ.get("TELEGRAM_BOT_TOKEN"); CHAT=os.environ.get("TELEGRAM_CHAT_ID")
BASE="https://hst-api.wialon.com/wialon/ajax.html"; RES,GRP=29957134,29960488
def tg(t): requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",data={"chat_id":CHAT,"text":t[:4000]})
def call(s,p,sid): return requests.get(BASE,params={"svc":s,"params":json.dumps(p),"sid":sid},timeout=120).json()
sid=requests.get(BASE,params={"svc":"token/login","params":'{"token":"%s"}'%WT},timeout=60).json()["eid"]
tz=timezone(timedelta(hours=5));now=datetime.now(tz)
st=int((now-timedelta(days=5)).replace(hour=0,minute=0,second=0).timestamp());en=int(now.timestamp())
call("report/cleanup_result",{},sid)
call("report/exec_report",{"reportResourceId":RES,"reportTemplateId":13,"reportObjectId":GRP,"reportObjectSecId":0,"interval":{"from":st,"to":en,"flags":0}},sid)
top=call("report/get_result_rows",{"tableIndex":0,"indexFrom":0,"indexTo":50},sid)
# сырой JSON второй строки (первая дата)
row = top[1] if isinstance(top,list) and len(top)>1 else (top[0] if isinstance(top,list) else top)
tg("RAW строки-даты:\n"+json.dumps(row, ensure_ascii=False)[:3500])
# и пробуем subrows с обработкой ошибки
try:
    sub=call("report/get_result_subrows",{"tableIndex":0,"rowIndex":1,"indexFrom":0,"indexTo":10},sid)
    tg("subrows ответ:\n"+json.dumps(sub, ensure_ascii=False)[:2000])
except Exception as e:
    tg("subrows ошибка: "+str(e))
