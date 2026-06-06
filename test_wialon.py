import os
import requests

WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

BASE = "https://hst-api.wialon.com/wialon/ajax.html"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text[:4000]})

# Шаг 1: вход по токену -> получаем sid
login = requests.get(BASE, params={
    "svc": "token/login",
    "params": '{"token":"%s"}' % WIALON_TOKEN
}, timeout=60)
lj = login.json()

if "eid" not in lj:
    send_telegram(f"❌ Wialon: вход не удался.\nОтвет: {login.text[:1000]}")
    raise SystemExit("login failed")

sid = lj["eid"]

# Шаг 2: запрос списка машин (units)
units = requests.get(BASE, params={
    "svc": "core/search_items",
    "params": '{"spec":{"itemsType":"avl_unit","propName":"sys_name","propValueMask":"*","sortType":"sys_name"},"force":1,"flags":1,"from":0,"to":0}',
    "sid": sid
}, timeout=60)
uj = units.json()

items = uj.get("items", [])
names = [it.get("nm", "?") for it in items]

msg = (
    f"✅ Wialon API работает\n"
    f"Вход по токену успешен (sid получен).\n"
    f"Машин в системе: {len(items)}\n"
    f"Примеры: " + ", ".join(names[:8])
)
send_telegram(msg)
print(msg)
