import os
import requests
from datetime import datetime, timedelta

SMARTGAS_KEY = os.environ.get("SMARTGAS_API_KEY")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

date_to = datetime.utcnow().date()
date_from = date_to - timedelta(days=5)

BASE_URL = "http://business.smartgas.global:8080/public-api/v1"
headers = {"Authorization": SMARTGAS_KEY}
params = {"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text[:4000]})

resp = requests.get(f"{BASE_URL}/transactions", headers=headers, params=params, timeout=60)
send_telegram(f"СТАТУС: {resp.status_code}\nПЕРИОД: {date_from}—{date_to}\nОТВЕТ (сырой):\n{resp.text[:1500]}")
print(resp.status_code, resp.text[:1500])
