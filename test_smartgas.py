"""
ТЕСТ 2 — проверка связи со Smartgas API.
Запрашивает заправки за последние 3 дня и присылает в Телеграм,
сколько транзакций получено и на какую сумму.
Цель — убедиться, что ключ Smartgas работает и данные приходят.
"""
import os
import requests
from datetime import datetime, timedelta

SMARTGAS_KEY = os.environ.get("SMARTGAS_API_KEY")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not all([SMARTGAS_KEY, BOT_TOKEN, CHAT_ID]):
    raise SystemExit("Не заданы секреты SMARTGAS_API_KEY / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.")

# Период: последние 3 дня
date_to = datetime.utcnow().date()
date_from = date_to - timedelta(days=3)

BASE_URL = "http://business.smartgas.global:8080/public-api/v1"
headers = {"Authorization": SMARTGAS_KEY}
params = {"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

try:
    resp = requests.get(f"{BASE_URL}/transactions", headers=headers, params=params, timeout=60)
    print("HTTP статус:", resp.status_code)
    print("Ответ (первые 500 символов):", resp.text[:500])

    if resp.status_code == 200:
        data = resp.json()
        txns = data.get("transactions", [])
        total_liters = sum(float(t.get("volume_liters", 0)) for t in txns)
        total_kzt = sum(float(t.get("amount_kzt", 0)) for t in txns)
        msg = (
            f"✅ Smartgas API работает\n"
            f"Период: {date_from} — {date_to}\n"
            f"Заправок получено: {len(txns)}\n"
            f"Объём: {total_liters:.0f} л\n"
            f"Сумма: {total_kzt:,.0f} ₸".replace(",", " ")
        )
        send_telegram(msg)
        print("УСПЕХ:", msg)
    else:
        msg = f"⚠️ Smartgas API вернул код {resp.status_code}. Проверьте ключ. Ответ: {resp.text[:200]}"
        send_telegram(msg)
        print(msg)
except Exception as e:
    msg = f"❌ Ошибка при запросе к Smartgas: {e}"
    send_telegram(msg)
    print(msg)
