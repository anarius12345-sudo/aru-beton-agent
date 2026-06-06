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
data = resp.json()

# Заправки лежат в transactions.data
block = data.get("transactions", {})
txns = block.get("data", []) if isinstance(block, dict) else []

liters = sum(float(t.get("deliver_quantity", 0)) for t in txns)
order_sum = sum(float(t.get("total_order_amt", 0)) for t in txns)
accept_sum = sum(float(t.get("accept_amt", 0)) for t in txns)

msg = (
    f"✅ Smartgas API — данные получены\n"
    f"Период: {date_from} — {date_to}\n"
    f"Заправок: {len(txns)}\n"
    f"Объём: {liters:.0f} л\n"
    f"Сумма заказа: {order_sum:,.0f} ₸\n"
    f"Принято к оплате: {accept_sum:,.0f} ₸"
).replace(",", " ")
send_telegram(msg)
print(msg)
