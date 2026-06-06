# -*- coding: utf-8 -*-
"""
АГЕНТ ARU BETON — ядро (Этап 1): сверка "карта (Smartgas) vs бак (Wialon ДУТ)".
Запускается на GitHub Actions. Шлёт сводку в Телеграм-группу.

Логика:
  1) Smartgas API -> транзакции заправок по картам (машина, время, литры, сумма).
  2) Wialon отчёт 13 (ARU_ANALYTICS группа), таблица "Заправки" -> заправки по ДУТ
     (раскрываем вложенный уровень: машина, время, литры по баку).
  3) Нормализация номеров (кириллица->латиница, убрать пробелы, отбросить имена).
  4) Транзакционный матчинг: карта<->бак по машине, окно времени MATCH_WINDOW_MIN.
  5) Итог по каждой машине: сумма карта / сумма бак / разница / флаг (карта>бака).
"""
import os, json, re, requests
from datetime import datetime, timedelta, timezone

# ---------- настройки ----------
WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
SMARTGAS_KEY = os.environ.get("SMARTGAS_API_KEY")
BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID")

WIALON_BASE  = "https://hst-api.wialon.com/wialon/ajax.html"
SMARTGAS_BASE= "http://business.smartgas.global:8080/public-api/v1"
RES_ID       = 29957134   # ресурс с шаблонами
TPL_FUEL     = 13         # ARU_ANALYTICS (группа) -> Заправки/Сливы
GROUP_ID     = 29960488   # Все объекты
TZ           = timezone(timedelta(hours=5))  # Алматы UTC+5

MATCH_WINDOW_MIN = 90     # окно матчинга карта<->бак (мин). Менять тут.
SHORTFALL_MIN_L  = 0      # порог "недолива" в литрах (0 = показывать все случаи карта>бак)

# ---------- справочник машин (из реестра) ----------
CYR2LAT = {'А':'A','В':'B','Е':'E','К':'K','М':'M','Н':'H','О':'O','Р':'P','С':'C','Т':'T','У':'Y','Х':'X'}

def normalize_code(s):
    if not s: return ""
    s = "".join(CYR2LAT.get(ch, ch) for ch in str(s).strip())
    if "|" in s:
        s = s.split("|")[-1]
    s = s.strip().replace(" ", "").upper()
    cands = re.findall(r'[A-Z0-9]+', s)
    best = ""
    for c in cands:
        if sum(ch.isdigit() for ch in c) >= 2 and len(c) >= 4 and len(c) > len(best):
            best = c
    if best: return best
    for c in cands:
        if c.isdigit() and len(c) >= 4: return c
    return s

# ---------- helpers ----------
def tg(text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": text[:4000]})

def wcall(svc, params, sid):
    return requests.get(WIALON_BASE, params={"svc": svc, "params": json.dumps(params), "sid": sid}, timeout=120).json()

def cell(c):
    return c.get("t","") if isinstance(c, dict) else c

def parse_num(x):
    """'268.63 л' / '4 099.86' -> float"""
    if x is None: return 0.0
    s = str(x).replace("\xa0"," ").replace(" ","").replace("л","").replace(",",".")
    m = re.search(r'-?\d+\.?\d*', s)
    return float(m.group()) if m else 0.0

# ====================================================================
# 1) SMARTGAS — транзакции заправок
# ====================================================================
def get_smartgas(date_from, date_to):
    headers = {"Authorization": SMARTGAS_KEY}
    params = {"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()}
    r = requests.get(f"{SMARTGAS_BASE}/transactions", headers=headers, params=params, timeout=90)
    data = r.json()
    block = data.get("transactions", {})
    txns = block.get("data", []) if isinstance(block, dict) else (block if isinstance(block, list) else [])
    out = []
    for t in txns:
        out.append({
            "code": normalize_code(t.get("display_name","")),
            "raw": t.get("display_name",""),
            "dt": t.get("created_at",""),
            "liters": parse_num(t.get("deliver_quantity",0)),
            "order_amt": parse_num(t.get("total_order_amt",0)),
            "accept_amt": parse_num(t.get("accept_amt",0)),
            "fuel": t.get("product_title",""),
        })
    return out

# ====================================================================
# 2) WIALON — заправки по ДУТ (отчёт 13, таблица "Заправки", вложенный уровень)
# ====================================================================
def get_wialon_fuelings(sid, ts_from, ts_to):
    wcall("report/cleanup_result", {}, sid)
    rep = wcall("report/exec_report", {
        "reportResourceId": RES_ID, "reportTemplateId": TPL_FUEL,
        "reportObjectId": GROUP_ID, "reportObjectSecId": 0,
        "interval": {"from": ts_from, "to": ts_to, "flags": 0}
    }, sid)
    tables = rep.get("reportResult", {}).get("tables", [])
    # таблица "Заправки" = индекс 0 (по нашим тестам)
    fuel_idx = 0
    for i, t in enumerate(tables):
        if "аправк" in t.get("label",""):
            fuel_idx = i; break
    # верхний уровень = даты; раскрываем уровень 1 (внутри каждой даты — заправки с машиной)
    rows = wcall("report/select_result_rows", {"tableIndex": fuel_idx,
        "config": {"type":"range","data":{"from":0,"to":3000,"level":1,"unitInfo":1}}}, sid)
    out = []
    if isinstance(rows, list):
        for r in rows:
            cells = [cell(c) for c in r.get("c", [])]
            if not cells: continue
            # колонки: Grouping(машина) | Время | Положение | Нач.уровень | Заправлено | Конеч.уровень | Водитель
            grouping = str(cells[0]) if len(cells)>0 else ""
            code = normalize_code(grouping)
            if not code or "----" in grouping or not re.search(r'[A-Z]|\d{4}', code):
                continue
            time_s = str(cells[1]) if len(cells)>1 else ""
            liters = parse_num(cells[4]) if len(cells)>4 else 0.0
            out.append({"code": code, "raw": grouping, "time": time_s, "liters": liters})
    return out, tables

# ====================================================================
# 3) WIALON — расход/пробег по машинам (отчёт 12) — для контекста
# ====================================================================
def get_wialon_consumption(sid, ts_from, ts_to):
    wcall("report/cleanup_result", {}, sid)
    rep = wcall("report/exec_report", {
        "reportResourceId": RES_ID, "reportTemplateId": 12,
        "reportObjectId": GROUP_ID, "reportObjectSecId": 0,
        "interval": {"from": ts_from, "to": ts_to, "flags": 0}
    }, sid)
    tables = rep.get("reportResult", {}).get("tables", [])
    if not tables: return {}
    rows = wcall("report/get_result_rows", {"tableIndex":0,"indexFrom":0,"indexTo":200}, sid)
    out = {}
    if isinstance(rows, list):
        for r in rows:
            cells = [cell(c) for c in r.get("c", [])]
            if not cells: continue
            code = normalize_code(str(cells[0]))
            if not code: continue
            out[code] = {"raw": str(cells[0])}
    return out

# ====================================================================
# МАТЧИНГ карта<->бак (по машине, окно времени)
# ====================================================================
def to_dt(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M:%S", "%H:%M:%S"):
        try: return datetime.strptime(s.strip()[:19], fmt)
        except: pass
    return None

def match_and_aggregate(sg, wl):
    """sg: транзакции карты; wl: заправки ДУТ. Матчим по коду+времени, агрегируем по машине."""
    by_code = {}
    # инициализация по всем машинам, что встретились
    for t in sg:
        by_code.setdefault(t["code"], {"card_l":0.0,"bak_l":0.0,"card_sum":0.0,"n_card":0,"n_bak":0,"raw":t["raw"]})
        by_code[t["code"]]["card_l"] += t["liters"]
        by_code[t["code"]]["card_sum"] += t["order_amt"]
        by_code[t["code"]]["n_card"] += 1
    for f in wl:
        by_code.setdefault(f["code"], {"card_l":0.0,"bak_l":0.0,"card_sum":0.0,"n_card":0,"n_bak":0,"raw":f["raw"]})
        by_code[f["code"]]["bak_l"] += f["liters"]
        by_code[f["code"]]["n_bak"] += 1
    return by_code

# ====================================================================
# MAIN
# ====================================================================
def run_period(label, ts_from, ts_to, d_from, d_to, sid):
    sg = get_smartgas(d_from, d_to)
    wl, tables = get_wialon_fuelings(sid, ts_from, ts_to)
    agg = match_and_aggregate(sg, wl)

    total_card = sum(v["card_l"] for v in agg.values())
    total_bak  = sum(v["bak_l"] for v in agg.values())
    total_sum  = sum(v["card_sum"] for v in agg.values())

    # машины где карта > бака (недолив)
    shortfalls = []
    for code, v in agg.items():
        diff = v["card_l"] - v["bak_l"]
        if v["n_card"]>0 and v["n_bak"]>0 and diff > SHORTFALL_MIN_L:
            shortfalls.append((code, v["card_l"], v["bak_l"], diff))
    shortfalls.sort(key=lambda x: -x[3])

    lines = [f"🚛 СВЕРКА «карта vs бак» — {label}",
             f"Период: {d_from} — {d_to}",
             f"Заправок по картам: {len([t for t in sg])} | по ДУТ: {len(wl)}",
             f"Залито по картам: {total_card:.0f} л / {total_sum:,.0f} ₸".replace(","," "),
             f"Показал бак (ДУТ): {total_bak:.0f} л",
             f"Разница (карта−бак): {total_card-total_bak:+.0f} л",
             ""]
    if shortfalls:
        lines.append(f"⚠️ Карта > бака (топ {min(10,len(shortfalls))}):")
        for code, c, b, d in shortfalls[:10]:
            lines.append(f"  {code}: карта {c:.0f} / бак {b:.0f} → {d:+.0f} л")
    else:
        lines.append("✅ Машин с превышением карта>бак не найдено.")
    return "\n".join(lines)

def main():
    if not all([WIALON_TOKEN, SMARTGAS_KEY, BOT_TOKEN, CHAT_ID]):
        tg("❌ Агент: не заданы секреты (проверьте WIALON_TOKEN, SMARTGAS_API_KEY, TELEGRAM_*).")
        return
    login = requests.get(WIALON_BASE, params={"svc":"token/login","params":'{"token":"%s"}'%WIALON_TOKEN}, timeout=60).json()
    if "eid" not in login:
        tg(f"❌ Wialon вход не удался: {str(login)[:300]}"); return
    sid = login["eid"]

    now = datetime.now(TZ)
    # вчера
    y = (now - timedelta(days=1)).date()
    y_from = int(datetime(y.year,y.month,y.day,0,0,0,tzinfo=TZ).timestamp())
    y_to   = int(datetime(y.year,y.month,y.day,23,59,59,tzinfo=TZ).timestamp())
    # месяц
    m_start = now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    m_from = int(m_start.timestamp()); m_to = int(now.timestamp())

    try:
        tg(run_period("ЗА ВЧЕРА", y_from, y_to, y, y, sid))
    except Exception as e:
        tg(f"❌ Ошибка (вчера): {e}")
    try:
        tg(run_period("С НАЧАЛА МЕСЯЦА", m_from, m_to, m_start.date(), now.date(), sid))
    except Exception as e:
        tg(f"❌ Ошибка (месяц): {e}")

if __name__ == "__main__":
    main()
