# -*- coding: utf-8 -*-
"""
АГЕНТ ARU BETON — ядро (Этап 1).
Сверка "карта (Smartgas) vs бак (Wialon ДУТ)" по методике A/B/C.
Источники: Smartgas API (карты) + Wialon отчёт 13 (Заправки/Сливы по ДУТ) + отчёт 12 (расход по машинам).
Выход: текст-сводка в Телеграм + Excel + PDF (как эталонный файл).
Запуск: GitHub Actions, каждое утро.
"""
import os, json, re, requests
from datetime import datetime, timedelta, timezone

# ---------- секреты ----------
WIALON_TOKEN = os.environ.get("WIALON_TOKEN")
SMARTGAS_KEY = os.environ.get("SMARTGAS_API_KEY")
BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID")

# ---------- константы ----------
WIALON_BASE   = "https://hst-api.wialon.com/wialon/ajax.html"
SMARTGAS_BASE = "http://business.smartgas.global:8080/public-api/v1"
RES_ID    = 29957134
TPL_FUEL  = 13            # ARU_ANALYTICS (группа): Заправки/Сливы
TPL_TRIPS = 12            # ARU_ANALYTICS: Поездки/расход по машинам
GROUP_ID  = 29960488      # Все объекты
TZ        = timezone(timedelta(hours=5))

MATCH_WINDOW_MIN = 90     # окно матчинга карта<->ДУТ (мин)
_RAW_DONE = []            # ВРЕМЕННО: чтобы сырой дамп Wialon ушёл только один раз
PRICE_DT = 336            # ₸/л ДТ (для оценки суммы разницы)

# ---------- нормализация номеров ----------
CYR2LAT = {'А':'A','В':'B','Е':'E','К':'K','М':'M','Н':'H','О':'O','Р':'P','С':'C','Т':'T','У':'Y','Х':'X'}
KNOWN_CODES = {"374FI02","417FJ02","422FJ02","425FJ02","433FJ02","435FJ02","770AKC05","973AIL02","601FZ02","610FZ02","614FZ02","661FZ02","665FZ02","018WK02","019WK02","215GK02","619GP02","699GJ02","718GP02","719GP02","819GA02","822GA02","851GA02","864GA02","867GA02","894GJ02","966GJ02","976GK02","416FJ02","418FJ02","429FJ02","432FJ02","623FI02","623FJ02","AE799A","A965ADD","A574AUD","ABE798A","ADE470A","AEE058A","29354"}

def normalize_code(s):
    if not s: return ""
    s = "".join(CYR2LAT.get(ch, ch) for ch in str(s).strip())
    if "|" in s: s = s.split("|")[-1]
    s = s.strip().replace(" ", "").upper()
    s = re.sub(r'\(.*?\)', '', s)
    cands = re.findall(r'[A-Z0-9]+', s)
    try:
        kc = KNOWN_CODES
    except NameError:
        kc = set()
    for c in cands:
        for k in kc:
            if c.startswith(k):
                return "623FI02" if k=="623FJ02" else k
    best=""
    for c in cands:
        if sum(ch.isdigit() for ch in c)>=2 and len(c)>=4 and len(c)>len(best): best=c
    if best:
        if len(best)>1 and best[-1].isalpha() and best[:-1] in kc: best=best[:-1]
        return "623FI02" if best=="623FJ02" else best
    for c in cands:
        if c.isdigit() and len(c)>=4: return c
    return s

# справочник: код -> тип
REG = {
 "374FI02":"Самосвал","417FJ02":"Самосвал","422FJ02":"Самосвал","425FJ02":"Самосвал","433FJ02":"Самосвал",
 "435FJ02":"Самосвал","770AKC05":"Самосвал","973AIL02":"Самосвал","601FZ02":"Самосвал","610FZ02":"Самосвал",
 "614FZ02":"Самосвал","661FZ02":"Самосвал","665FZ02":"Самосвал",
 "018WK02":"Миксер","019WK02":"Миксер","215GK02":"Миксер","619GP02":"Миксер","699GJ02":"Миксер","718GP02":"Миксер",
 "719GP02":"Миксер","819GA02":"Миксер","822GA02":"Миксер","851GA02":"Миксер","864GA02":"Миксер","867GA02":"Миксер",
 "894GJ02":"Миксер","966GJ02":"Миксер","976GK02":"Миксер","416FJ02":"Миксер","418FJ02":"Миксер","429FJ02":"Миксер",
 "432FJ02":"Миксер","623FI02":"Миксер",
 "AE799A":"Погрузчик","A965ADD":"Погрузчик","A574AUD":"Погрузчик","ABE798A":"Погрузчик","ADE470A":"Погрузчик","AEE058A":"Погрузчик",
 "29354":"Экскаватор",
}


def car_type(code):
    if code in REG: return REG[code]
    # 864GA -> 864GA02
    if code+"02" in REG: return REG[code+"02"]
    return "Прочее"

# ---------- helpers ----------
def tg(text):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text[:4000]})
def tg_doc(path, caption=""):
    with open(path,"rb") as f:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                      data={"chat_id":CHAT_ID,"caption":caption[:1000]}, files={"document":f})
def wcall(svc, params, sid):
    return requests.get(WIALON_BASE, params={"svc":svc,"params":json.dumps(params),"sid":sid}, timeout=180).json()
def cval(c):
    return c.get("t","") if isinstance(c, dict) else (c if c is not None else "")
def pnum(x):
    if x is None: return 0.0
    s = str(x).replace("\xa0"," ").replace(" ","").replace("л","").replace("l","").replace(",",".")
    m = re.search(r'-?\d+\.?\d*', s)
    return float(m.group()) if m else 0.0
def is_car(label):
    """строка-машина (а не дата/итого)?"""
    if not label: return False
    if "|" in str(label): return True
    return False

# ====================================================================
# SMARTGAS
# ====================================================================
def get_smartgas(d_from, d_to):
    out=[]
    page=1; last=1
    while page<=last and page<=50:
        try:
            r=requests.get(f"{SMARTGAS_BASE}/transactions",
                headers={"Authorization":SMARTGAS_KEY},
                params={"dateFrom":d_from.isoformat(),"dateTo":d_to.isoformat(),"page":page}, timeout=90)
            data=r.json(); block=data.get("transactions",{})
            if isinstance(block,dict):
                txns=block.get("data",[])
                last=block.get("last_page", block.get("lastPage", 1)) or 1
            elif isinstance(block,list):
                txns=block; last=1
            else:
                txns=[]; last=1
            for t in txns:
                dn=t.get("display_name","")
                cdt=parse_dt(t.get("created_at",""))
                if cdt: cdt=cdt+timedelta(hours=5)   # FIX: Smartgas API отдаёт UTC -> +5ч (Алматы), как и Wialon
                out.append({"code":normalize_code(dn),"raw":dn,
                    "dt":cdt,
                    "liters":pnum(t.get("deliver_quantity",0)),
                    "order_amt":pnum(t.get("total_order_amt",0)),
                    "fuel":t.get("product_title",""),"azs":t.get("store_title",""),
                    "by_name":not bool(re.search(r'\d{3}', normalize_code(dn)))})
            if not txns: break
            page+=1
        except Exception as e:
            tg(f"⚠️ Smartgas стр.{page}: {e}"); break
    try: tg(f"[diag Smartgas] транзакций: {len(out)} (страниц: {page-1})")
    except: pass
    return out

# ====================================================================
# WIALON Заправки (отчёт 13, уровень машин)
# ====================================================================
def parse_dt(s, base_date=None):
    s = str(s).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M:%S","%d.%m.%Y %H:%M:%S"):
        try: return datetime.strptime(s[:19], fmt)
        except: pass
    # только время "HH:MM:SS" + базовая дата
    if base_date and re.match(r'^\d{1,2}:\d{2}:\d{2}$', s):
        try:
            h,m,sec = map(int, s.split(":"))
            return datetime(base_date.year,base_date.month,base_date.day,h,m,sec)
        except: pass
    return None

def _parse_event(cells, lbl, cur_date):
    """Строку отчёта -> ('fuel'/'drain', dict) или None."""
    g = str(cells[0]).strip() if cells else ""
    if not is_car(g): return None
    code = normalize_code(g)
    tm = parse_dt(str(cells[1]) if len(cells)>1 else "", cur_date)
    if tm: tm = tm + timedelta(hours=5)
    if "аправк" in lbl:
        liters = pnum(cells[4]) if len(cells)>4 else 0.0
        if 20 <= liters <= 350:
            return ("fuel", {"code":code,"raw":g,"dt":tm,"liters":liters,
                             "pos":str(cells[2]) if len(cells)>2 else ""})
    elif "лив" in lbl:
        liters = pnum(cells[5]) if len(cells)>5 else 0.0
        if liters >= 1:
            return ("drain", {"code":code,"raw":g,"dt":tm,"liters":liters,
                              "pos":str(cells[3]) if len(cells)>3 else ""})
    return None

def _read_old(idx, lbl, sid):
    """Старый способ: дата -> get_result_subrows (1 уровень). У машин с 2+ заправками вернёт ПОДЫТОГ."""
    out_f=[]; out_d=[]
    top=wcall("report/get_result_rows",{"tableIndex":idx,"indexFrom":0,"indexTo":300},sid)
    if not isinstance(top,list): return out_f,out_d,top
    for di,drow in enumerate(top):
        dcells=[cval(c) for c in drow.get("c",[])]
        cur_date=None
        g0=str((dcells+[""])[0]).strip()
        if re.match(r'^\d{2}\.\d{2}\.\d{4}$',g0):
            try: cur_date=datetime.strptime(g0,"%d.%m.%Y")
            except: pass
        sub=wcall("report/get_result_subrows",{"tableIndex":idx,"rowIndex":di,"indexFrom":0,"indexTo":500},sid)
        if not isinstance(sub,list): continue
        for k in sub:
            ev=_parse_event([cval(c) for c in k.get("c",[])], lbl, cur_date)
            if ev: (out_f if ev[0]=="fuel" else out_d).append(ev[1])
    return out_f,out_d,top

def _read_flat(idx, lbl, sid):
    """Новый способ: select_result_rows -> всё дерево; берём только ЛИСТЬЯ (d==0) = отдельные заправки."""
    out_f=[]; out_d=[]
    flat=wcall("report/select_result_rows",{"tableIndex":idx,
        "config":{"type":"range","data":{"from":0,"to":100000,"level":255}}},sid)
    if not isinstance(flat,list): return out_f,out_d,flat
    cur_date=None
    for r in flat:
        cells=[cval(c) for c in r.get("c",[])]
        if not cells: continue
        g0=str(cells[0]).strip()
        if re.match(r'^\d{2}\.\d{2}\.\d{4}$',g0):
            try: cur_date=datetime.strptime(g0,"%d.%m.%Y")
            except: pass
            continue
        if (r.get("d",0) or 0)!=0: continue   # пропускаем группы/подытоги, берём только листья
        ev=_parse_event(cells, lbl, cur_date)
        if ev: (out_f if ev[0]=="fuel" else out_d).append(ev[1])
    return out_f,out_d,flat

def get_wialon_fuel(sid, ts_from, ts_to):
    wcall("report/cleanup_result", {}, sid)
    rep = wcall("report/exec_report", {"reportResourceId":RES_ID,"reportTemplateId":TPL_FUEL,
        "reportObjectId":GROUP_ID,"reportObjectSecId":0,"interval":{"from":ts_from,"to":ts_to,"flags":0}}, sid)
    tables = rep.get("reportResult",{}).get("tables",[])
    res = {"fuel":[], "drain":[]}
    for idx,t in enumerate(tables):
        lbl=t.get("label","")
        if "аправк" not in lbl and "лив" not in lbl: continue
        of,od,top   = _read_old(idx, lbl, sid)
        ff,fd,flat  = _read_flat(idx, lbl, sid)
        # выбираем способ, который нашёл БОЛЬШЕ заправок (flat разворачивает подытоги; old — fallback)
        use_f = ff if (ff and len(ff)>=len(of)) else of
        use_d = fd if (fd and len(fd)>=len(od)) else od
        res["fuel"]  += use_f
        res["drain"] += use_d
        # ВРЕМЕННАЯ ДИАГНОСТИКА. Убрать после проверки.
        if not _RAW_DONE and "аправк" in lbl:
            _RAW_DONE.append(1)
            try:
                tg(f"[diag методы] старый: {len(of)} заправок | flat(select): {len(ff)} | "
                   f"flat-всего-строк: {len(flat) if isinstance(flat,list) else 'нет'} | "
                   f"выбран: {'flat' if use_f is ff else 'старый'}")
                if isinstance(flat,list):
                    samp=[]
                    for r in flat[:30]:
                        cc=[cval(c) for c in r.get("c",[])]+["","","","",""]
                        samp.append([r.get("d"), str(cc[0])[:13], str(cc[1])[:19], str(cc[4])[:8]])
                    tg("[RAW flat d/name/time/liters]\n"+json.dumps(samp, ensure_ascii=False)[:3300])
            except Exception as _e:
                tg(f"[diag методы err] {_e}")
    # отсев строк-итогов: внутри (машина, день) если строка == сумме остальных -> убрать
    from collections import defaultdict
    grp=defaultdict(list)
    for x in res["fuel"]:
        day = x["dt"].date() if x["dt"] else None
        grp[(x["code"], day)].append(x)
    cleaned=[]
    for (code,day),items in grp.items():
        if len(items)<=1:
            cleaned += items; continue
        # ищем строку, чьё liters ~= сумме остальных
        removed_total=False
        for i,it in enumerate(items):
            others=[items[j]["liters"] for j in range(len(items)) if j!=i]
            if others and abs(it["liters"] - sum(others)) < 1.0:
                # это итог — пропускаем его, берём остальные
                cleaned += [items[j] for j in range(len(items)) if j!=i]
                removed_total=True
                break
        if not removed_total:
            cleaned += items
    res["fuel"]=cleaned

    for kk in res:
        seen=set(); uniq=[]
        for x in res[kk]:
            tkey = x["dt"].strftime("%Y-%m-%d %H:%M") if x["dt"] else "?"
            key=(x["code"],tkey,round(x["liters"]/0.5)*0.5)
            if key in seen: continue
            seen.add(key); uniq.append(x)
        res[kk]=uniq
    try:
        msg=f"[diag Wialon] заправок: {len(res['fuel'])}, сливов: {len(res['drain'])}\n"
        for f in res["fuel"][:5]: msg+=f"  {f['code']} {f['dt']} {f['liters']}л\n"
        tg(msg)
    except: pass
    return res

# ====================================================================
# МАТЧИНГ A/B/C
# ====================================================================
def match_abc(sg, wl_fuel):
    """Жадный матчинг по коду + времени ±MATCH_WINDOW_MIN. Возврат: A(пары), B(карта без ДУТ), C(ДУТ без карты)."""
    win = timedelta(minutes=MATCH_WINDOW_MIN)
    cards = [dict(x, used=False) for x in sg]
    baks  = [dict(x, used=False) for x in wl_fuel]
    pairs = []
    cand = []
    for i,c in enumerate(cards):
        if c["liters"]<=0: continue
        for j,b in enumerate(baks):
            if c["code"]!=b["code"]: continue
            # близость литров: ДУТ обычно чуть меньше карты; допускаем разницу до 40% или 60 л
            ld = abs(c["liters"]-b["liters"])
            if ld > max(60, c["liters"]*0.40): continue
            # время — вторичный критерий (если обе даты есть)
            gap = 0.0
            if c["dt"] and b["dt"]:
                gap = abs((c["dt"]-b["dt"]).total_seconds())/60.0
            cand.append((ld, gap, i, j))
    cand.sort()
    for ld,gap,i,j in cand:
        if cards[i]["used"] or baks[j]["used"]: continue
        cards[i]["used"]=True; baks[j]["used"]=True
        pairs.append({"code":cards[i]["code"],"mp":cards[i]["liters"],"dut":baks[j]["liters"],
                      "delta":cards[i]["liters"]-baks[j]["liters"],"gap":gap,
                      "azs":cards[i]["azs"],"dt":cards[i]["dt"],"fuel":cards[i]["fuel"]})
    # диагностика матчинга
    try:
        cset=sorted(set(c["code"] for c in cards)); bset=sorted(set(b["code"] for b in baks))
        common=sorted(set(cset)&set(bset))
        only_card=sorted(set(cset)-set(bset)); only_bak=sorted(set(bset)-set(cset))
        tg(f"[diag match] карт-кодов:{len(cset)} бак-кодов:{len(bset)} общих:{len(common)} пар:{len(pairs)}\n"
           f"только карта: {','.join(only_card[:10])}\n"
           f"только бак: {','.join(only_bak[:10])}")
    except: pass
    B = [c for c in cards if not c["used"]]   # карта без ДУТ
    C = [b for b in baks if not b["used"]]    # ДУТ без карты
    return pairs, B, C

# ====================================================================
# СБОРКА EXCEL
# ====================================================================
def build_excel(path, period, pairs, B, C, sg, wl, drains):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = Workbook()
    HEAD = PatternFill("solid", fgColor="1F4E78"); HF = Font(bold=True,color="FFFFFF")
    RED  = PatternFill("solid", fgColor="C00000")
    thin = Side(style="thin",color="BFBFBF"); BORD = Border(thin,thin,thin,thin)
    def style_head(ws,row,ncol,fill=HEAD):
        for c in range(1,ncol+1):
            cell=ws.cell(row=row,column=c); cell.fill=fill; cell.font=HF
            cell.alignment=Alignment(horizontal="center",vertical="center"); cell.border=BORD
    def zebra(ws,r0,r1,ncol):
        for r in range(r0,r1+1):
            f = PatternFill("solid",fgColor="F2F2F2") if (r-r0)%2 else None
            for c in range(1,ncol+1):
                cell=ws.cell(row=r,column=c); cell.border=BORD
                if f: cell.fill=f

    # ---- Баланс ----
    ws=wb.active; ws.title="Баланс"
    ws["A1"]="БАЛАНС ТОПЛИВА: карты ↔ ДУТ"; ws["A1"].font=Font(bold=True,size=13)
    ws["A2"]=f"Период проверки: {period}"
    mpA=sum(p["mp"] for p in pairs); dutA=sum(p["dut"] for p in pairs)
    mpB=sum(b["liters"] for b in B); dutC=sum(c["liters"] for c in C)
    sumA=sum(p["mp"] for p in pairs)*0  # сумма ₸ из sg
    sum_all=sum(t["order_amt"] for t in sg)
    hdr=["№","Категория","Событий","МП, л","ДУТ, л","Разница МП−ДУТ, л","Сумма, ₸"]
    ws.append([]); ws.append(hdr); hr=ws.max_row; style_head(ws,hr,len(hdr))
    rows=[
        [1,"A — карта+ДУТ сопоставлены",len(pairs),round(mpA,1),round(dutA,1),round(mpA-dutA,1),round(sum(t['order_amt'] for t in sg if any(p['code']==t['code'] for p in pairs)),0)],
        [2,"B — карта есть, ДУТ нет",len(B),round(mpB,1),"—","—",round(sum(b['order_amt'] for b in B),0)],
        [3,"C — ДУТ есть, карты нет",len(C),"—",round(dutC,1),"—","—"],
        ["","ИТОГО",len(pairs)+len(B)+len(C),round(mpA+mpB,1),round(dutA+dutC,1),round(mpA-dutA,1),round(sum_all,0)],
    ]
    for r in rows: ws.append(r)
    zebra(ws,hr+1,ws.max_row,len(hdr))
    ws.append([]); ws.append(["ПРОВЕРКА СХОДИМОСТИ"])
    pct = (mpA-dutA)/mpA*100 if mpA else 0
    ws.append(["Карты всего (МП)",round(mpA+mpB,1),f"A+B={round(mpA+mpB,1)}"])
    ws.append(["Wialon всего (ДУТ)",round(dutA+dutC,1),f"A+C={round(dutA+dutC,1)}"])
    ws.append(["Разница в кат. A",round(mpA-dutA,1),f"{pct:.2f}%",f"{round((mpA-dutA)*PRICE_DT):,} ₸".replace(',',' ')])
    for col,w in zip("ABCDEFG",[5,32,10,12,12,18,16]): ws.column_dimensions[col].width=w

    # ---- Заправки с ДУТ (категория A) ----
    ws=wb.create_sheet("Заправки с ДУТ")
    ws["A1"]="ЗАПРАВКИ С ДАТЧИКОМ (категория A)"; ws["A1"].font=Font(bold=True,size=12)
    ws["A2"]=f"Период проверки: {period}"
    hdr=["№","Код ТС","Тип","Время карты","АЗС","МП, л","ДУТ, л","Δ, л","Δ %","Разрыв, мин"]
    ws.append([]); ws.append(hdr); hr=ws.max_row; style_head(ws,hr,len(hdr))
    for i,p in enumerate(sorted(pairs,key=lambda x:x["code"]),1):
        dpct = p["delta"]/p["mp"]*100 if p["mp"] else 0
        ws.append([i,p["code"],car_type(p["code"]),
                   p["dt"].strftime("%Y-%m-%d %H:%M") if p["dt"] else "",
                   (p["azs"] or "")[:30],round(p["mp"],1),round(p["dut"],1),
                   round(p["delta"],1),round(dpct,1),round(p["gap"],1)])
    ws.append(["","ИТОГО",f"{len(pairs)} зап.","","",round(mpA,1),round(dutA,1),round(mpA-dutA,1),"",""])
    zebra(ws,hr+1,ws.max_row,len(hdr))
    for col,w in zip("ABCDEFGHIJ",[5,12,12,17,32,8,8,8,7,11]): ws.column_dimensions[col].width=w

    # ---- По машинам ----
    ws=wb.create_sheet("По машинам")
    ws["A1"]="СВОДКА ПО МАШИНАМ"; ws["A1"].font=Font(bold=True,size=12)
    ws["A2"]=f"Период проверки: {period}"
    hdr=["№","Код ТС","Тип","МП (карта), л","ДУТ (Wialon), л","Наличие"]
    ws.append([]); ws.append(hdr); hr=ws.max_row; style_head(ws,hr,len(hdr))
    codes=set([t["code"] for t in sg]+[f["code"] for f in wl])
    bycode={}
    for t in sg: bycode.setdefault(t["code"],{"mp":0,"dut":0}); bycode[t["code"]]["mp"]+=t["liters"]
    for f in wl: bycode.setdefault(f["code"],{"mp":0,"dut":0}); bycode[f["code"]]["dut"]+=f["liters"]
    for i,code in enumerate(sorted(codes),1):
        v=bycode[code]; has="карта+ДУТ" if v["mp"]>0 and v["dut"]>0 else ("только карта" if v["mp"]>0 else "только Wialon")
        ws.append([i,code,car_type(code),round(v["mp"],1) if v["mp"] else "—",round(v["dut"],1) if v["dut"] else "—",has])
    zebra(ws,hr+1,ws.max_row,len(hdr))
    for col,w in zip("ABCDEF",[5,12,12,15,16,14]): ws.column_dimensions[col].width=w

    # ---- Карта без датчика (B) ----
    ws=wb.create_sheet("Карта без датчика")
    ws["A1"]="КАРТА БЕЗ ДАТЧИКА (категория B)"; ws["A1"].font=Font(bold=True,size=12)
    ws["A2"]=f"Период проверки: {period}"
    hdr=["№","Код ТС","Время","АЗС","Литры","₸","Топливо"]
    ws.append([]); ws.append(hdr); hr=ws.max_row; style_head(ws,hr,len(hdr),RED)
    for i,b in enumerate(sorted(B,key=lambda x:(x["dt"] or datetime.min)),1):
        ws.append([i,b["code"] if not b["by_name"] else "(по имени)",
                   b["dt"].strftime("%Y-%m-%d %H:%M") if b["dt"] else "",
                   (b["azs"] or "")[:30],round(b["liters"],1),round(b["order_amt"],0),b["fuel"]])
    zebra(ws,hr+1,ws.max_row,len(hdr))
    for col,w in zip("ABCDEFG",[5,12,17,32,8,10,10]): ws.column_dimensions[col].width=w

    # ---- Wialon без карты (C) ----
    ws=wb.create_sheet("Wialon без карты")
    ws["A1"]="WIALON БЕЗ КАРТЫ (категория C)"; ws["A1"].font=Font(bold=True,size=12)
    ws["A2"]=f"Период проверки: {period}"
    hdr=["№","Код ТС","Тип","Время Wialon","Залито, л","Место"]
    ws.append([]); ws.append(hdr); hr=ws.max_row; style_head(ws,hr,len(hdr),RED)
    for i,c in enumerate(sorted(C,key=lambda x:x["code"]),1):
        ws.append([i,c["code"],car_type(c["code"]),
                   c["dt"].strftime("%Y-%m-%d %H:%M") if c["dt"] else "",
                   round(c["liters"],1),(c["pos"] or "")[:30]])
    zebra(ws,hr+1,ws.max_row,len(hdr))
    for col,w in zip("ABCDEF",[5,12,12,17,10,32]): ws.column_dimensions[col].width=w

    # ---- Сливы ----
    ws=wb.create_sheet("Сливы")
    ws["A1"]="СЛИВЫ ТОПЛИВА (по ДУТ)"; ws["A1"].font=Font(bold=True,size=12)
    ws["A2"]=f"Период проверки: {period}"
    hdr=["№","Код ТС","Тип","Время","Слито, л","Место"]
    ws.append([]); ws.append(hdr); hr=ws.max_row; style_head(ws,hr,len(hdr),RED)
    for i,d in enumerate(sorted(drains,key=lambda x:-x["liters"]),1):
        ws.append([i,d["code"],car_type(d["code"]),
                   d["dt"].strftime("%Y-%m-%d %H:%M") if d["dt"] else "",
                   round(d["liters"],1),(d["pos"] or "")[:30]])
    zebra(ws,hr+1,ws.max_row,len(hdr))
    for col,w in zip("ABCDEF",[5,12,12,17,10,32]): ws.column_dimensions[col].width=w

    wb.save(path)
    return {"mpA":mpA,"dutA":dutA,"mpB":mpB,"dutC":dutC,"pct":pct,
            "nA":len(pairs),"nB":len(B),"nC":len(C),"sum_all":sum_all,"drains":len(drains)}

# ====================================================================
# PDF
# ====================================================================
def build_pdf(path, period, stats, pairs, drains):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        # шрифт с кириллицей
        fp=None
        for cand in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
            if os.path.exists(cand): fp=cand; break
        if fp: pdfmetrics.registerFont(TTFont("DV", fp))
        fn = "DV" if fp else "Helvetica"
        doc=SimpleDocTemplate(path,pagesize=A4,topMargin=15*mm,bottomMargin=15*mm)
        st=getSampleStyleSheet()
        h=ParagraphStyle("h",parent=st["Title"],fontName=fn,fontSize=15)
        n=ParagraphStyle("n",parent=st["Normal"],fontName=fn,fontSize=9)
        el=[Paragraph("Сверка топлива ARU Beton",h),
            Paragraph(f"Период: {period}",n),Spacer(1,8)]
        data=[["Категория","Событий","МП, л","ДУТ, л","Разница"],
              ["A карта+ДУТ",stats["nA"],f"{stats['mpA']:.0f}",f"{stats['dutA']:.0f}",f"{stats['mpA']-stats['dutA']:.0f}"],
              ["B карта без ДУТ",stats["nB"],f"{stats['mpB']:.0f}","—","—"],
              ["C ДУТ без карты",stats["nC"],"—",f"{stats['dutC']:.0f}","—"]]
        t=Table(data,hAlign="LEFT")
        t.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),fn),("FONTSIZE",(0,0),(-1,-1),9),
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F4E78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("GRID",(0,0),(-1,-1),0.4,colors.grey)]))
        el+=[t,Spacer(1,6),
             Paragraph(f"Разница в категории A: {stats['mpA']-stats['dutA']:.0f} л ({stats['pct']:.2f}%) ≈ {round((stats['mpA']-stats['dutA'])*PRICE_DT):,} ₸".replace(',',' '),n),
             Paragraph(f"Сливов по ДУТ: {stats['drains']}",n)]
        doc.build(el)
        return True
    except Exception as e:
        tg(f"⚠️ PDF не создан: {e}")
        return False

# ====================================================================
# RUN
# ====================================================================
def run_period(label, ts_from, ts_to, d_from, d_to, sid, tag):
    period=f"{d_from.strftime('%d.%m.%Y')} – {d_to.strftime('%d.%m.%Y')}"
    sg = get_smartgas(d_from - timedelta(days=1), d_to + timedelta(days=1))  # FIX: берём шире, чтобы не терять края суток из-за UTC
    # фильтр по локальной дате периода (после +5ч Smartgas уже в Алматы)
    def _in_period(t):
        if t["dt"] is None: return True
        d = t["dt"].date()
        return d_from <= d <= d_to
    sg = [t for t in sg if _in_period(t)]
    wl = get_wialon_fuel(sid, ts_from, ts_to)
    fuelings = [f for f in wl["fuel"] if f["dt"] is None or (d_from <= f["dt"].date() <= d_to)]
    drains = [x for x in wl["drain"] if x["dt"] is None or (d_from <= x["dt"].date() <= d_to)]
    pairs, B, C = match_abc(sg, fuelings)

    xlsx=f"/tmp/Анализ_заправки_{tag}.xlsx"; pdf=f"/tmp/Сверка_{tag}.pdf"
    stats=build_excel(xlsx, period, pairs, B, C, sg, fuelings, drains)
    has_pdf=build_pdf(pdf, period, stats, pairs, drains)

    diff=stats["mpA"]-stats["dutA"]
    lines=[f"🚛 СВЕРКА «карта vs бак» — {label}",f"Период: {period}","",
           f"📥 Куплено по картам: {stats['mpA']+stats['mpB']:.0f} л / {stats['sum_all']:,.0f} ₸".replace(',',' '),
           f"⛽ ДУТ Wialon: {stats['dutA']+stats['dutC']:.0f} л","",
           f"A сопоставлено: {stats['nA']} | разница {diff:+.0f} л ({stats['pct']:.1f}%) ≈ {round(diff*PRICE_DT):,} ₸".replace(',',' '),
           f"B карта без ДУТ: {stats['nB']} ({stats['mpB']:.0f} л)",
           f"C ДУТ без карты: {stats['nC']} ({stats['dutC']:.0f} л)",
           f"💧 Сливы по ДУТ: {stats['drains']}"]
    # топ расхождений в A
    big=sorted([p for p in pairs if abs(p["delta"])>=15],key=lambda x:-abs(x["delta"]))[:5]
    if big:
        lines.append("\n⚠️ Крупные расхождения (A):")
        for p in big:
            lines.append(f"  {p['code']}: МП {p['mp']:.0f} / ДУТ {p['dut']:.0f} → {p['delta']:+.0f} л")
    tg("\n".join(lines))
    tg_doc(xlsx, f"Excel: анализ заправок {period}")
    if has_pdf: tg_doc(pdf, f"PDF: сверка {period}")

def main():
    if not all([WIALON_TOKEN,SMARTGAS_KEY,BOT_TOKEN,CHAT_ID]):
        tg("❌ Не заданы секреты."); return
    login=requests.get(WIALON_BASE,params={"svc":"token/login","params":'{"token":"%s"}'%WIALON_TOKEN},timeout=60).json()
    if "eid" not in login: tg(f"❌ Wialon вход: {str(login)[:200]}"); return
    sid=login["eid"]
    now=datetime.now(TZ)
    y=(now-timedelta(days=1)).date()
    yf=int(datetime(y.year,y.month,y.day,0,0,0,tzinfo=TZ).timestamp())
    yt=int(datetime(y.year,y.month,y.day,23,59,59,tzinfo=TZ).timestamp())
    ms=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    # ВРЕМЕННО: прогон именно за 05.06 — для сверки с эталоном (A=16) и диагностики Wialon. Убрать после.
    d0=datetime(2026,6,5).date()
    f0=int(datetime(2026,6,5,0,0,0,tzinfo=TZ).timestamp())
    t0=int(datetime(2026,6,5,23,59,59,tzinfo=TZ).timestamp())
    try: run_period("ПРОВЕРКА 05.06 (эталон A=16)", f0, t0, d0, d0, sid, "проверка0506")
    except Exception as e: tg(f"❌ Ошибка (05.06): {e}")
    # ВРЕМЕННО отключены на время диагностики — вернём после починки Wialon:
    # try: run_period("ЗА ВЧЕРА", yf, yt, y, y, sid, "вчера")
    # except Exception as e: tg(f"❌ Ошибка (вчера): {e}")
    # try: run_period("С НАЧАЛА МЕСЯЦА", int(ms.timestamp()), yt, ms.date(), y, sid, "месяц")
    # except Exception as e: tg(f"❌ Ошибка (месяц): {e}")

if __name__=="__main__":
    main()
