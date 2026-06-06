"""
ТЕСТ 1 — проверка связи с Телеграм.
Этот маленький скрипт просто отправляет сообщение в группу.
Если оно придёт — значит токен бота и ID группы введены правильно,
и можно двигаться дальше к полному агенту.

Ключи берутся из "секретов" (переменных окружения), НЕ пишутся в коде.
"""
import os
import requests

# Читаем секреты из окружения (в GitHub Actions они задаются в Settings → Secrets)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise SystemExit("Не заданы TELEGRAM_BOT_TOKEN и/или TELEGRAM_CHAT_ID в секретах.")

text = (
    "✅ Тест агента ARU Beton\n"
    "Связь с Телеграм работает.\n"
    "Это сообщение отправлено автоматически — значит токен бота и ID группы верны."
)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(url, data={"chat_id": CHAT_ID, "text": text})

print("HTTP статус:", resp.status_code)
print("Ответ Телеграм:", resp.text)

if resp.status_code == 200 and resp.json().get("ok"):
    print("УСПЕХ: сообщение отправлено в группу.")
else:
    print("ОШИБКА: проверьте токен бота и ID группы.")
