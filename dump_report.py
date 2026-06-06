import os, json, requests
from datetime import datetime, timedelta, timezone

WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
BASE = "https://hst-api.wialon.com/wialon/ajax.html"
RES_ID, TEMPLATE_ID, GROUP_ID = 29957134, 13, 29960488

def call(svc, params, sid):
    return requests.get(BASE, params={"svc": svc, "params": json.dumps(params), "sid": sid}, timeout=120).json()

sid = requests.get(BASE, params={"svc":"token/login","params":'{"token":"%s"}'%WIALON_TOKEN}, timeout=60).json()["eid"]
tz = timezone(timedelta(hours=5)); now = datetime.now(tz)
start = int((now - timedelta(days=5)).replace(hour=0,minute=0,second=0).timestamp()); end = int(now.timestamp())

call("report/cleanup_result", {}, sid)
rep = call("report/exec_report", {"reportResourceId":RES_ID,"reportTemplateId":TEMPLATE_ID,
    "reportObjectId":GROUP_ID,"reportObjectSecId":0,"interval":{"from":start,"to":end,"flags":0}}, sid)

dump = {"tables_meta": rep.get("reportResult",{}).get("tables",[]), "data": {}}
for idx, t in enumerate(rep.get("reportResult",{}).get("tables",[])):
    # раскрываем все уровни
    rows = call("report/select_result_rows", {"tableIndex":idx,
        "config":{"type":"range","data":{"from":0,"to":2000,"level":2,"unitInfo":1}}}, sid)
    dump["data"][f"{idx}_{t.get('label')}"] = rows

with open("report_dump.json", "w", encoding="utf-8") as f:
    json.dump(dump, f, ensure_ascii=False, indent=1)
print("saved")
