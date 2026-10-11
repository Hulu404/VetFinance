"""Generates tests/golden/set02 (bank statements in 1CClientBankExchange, Vetmanager export, initial state).

Deterministic, no randomness. The labels in truth.json are written by hand here (what SHOULD happen);
expected.json is produced by compute_expected_set02.py, which re-parses the generated files on its own
and cross-checks them against these labels. Neither script imports backend/.
"""
import json
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "set02"
(OUT / "vetmanager").mkdir(parents=True, exist_ok=True)

OWN = {"name": 'ООО "ВетКлиника Лапа"', "inn": "7799000100"}
BANK = {"name": 'ПАО "Банк-Пример"', "bik": "044525999", "corr": "30101810000000000999", "inn": "7710000077"}
ACC_M, ACC_R = "40702810500000000101", "40702810500000000102"
FILE1_TO = date(2026, 9, 22)
FILE2_START = date(2026, 9, 15)
RATE_BP = 190  # 1.9 % acquiring tariff
ACQ_PARAMS = {"rate_bp": 190, "max_delay_business_days": 3, "tolerance_kop": 100, "max_group_days": 3,
              "mismatch_search_pct": 10}


def D(d, m=9):
    return date(2026, m, d)


# ---- people (pet owners: must never reach the DB) ----------------------------------------------------
CLIENTS = [
    ("Смирнова", "Ольга", "Петровна"), ("Волков", "Игорь", "Сергеевич"), ("Кузнецова", "Анна", "Викторовна"),
    ("Морозов", "Сергей", "Андреевич"), ("Лебедев", "Михаил", "Олегович"), ("Новикова", "Елена", "Сергеевна"),
    ("Белова", "Татьяна", "Игоревна"), ("Григорьева", "Мария", "Александровна"), ("Фёдоров", "Алексей", "Николаевич"),
    ("Орлова", "Наталья", "Дмитриевна"), ("Попов", "Артём", "Николаевич"), ("Соколова", "Юлия", "Андреевна"),
    ("Михайлов", "Денис", "Романович"), ("Васильева", "Ирина", "Павловна"), ("Зайцев", "Кирилл", "Валерьевич"),
    ("Павлова", "Светлана", "Олеговна"), ("Семёнов", "Георгий", "Фёдорович"), ("Голубева", "Вера", "Степановна"),
    ("Виноградов", "Леонид", "Ильич"), ("Богданова", "Алина", "Романовна"), ("Тарасов", "Руслан", "Маратович"),
    ("Беляева", "Дарья", "Сергеевна"), ("Комаров", "Виктор", "Павлович"), ("Никитина", "Оксана", "Юрьевна"),
    ("Ершов", "Борис", "Аркадьевич"),
]
DOCTORS = [("Андреев", "Павел", "Игоревич"), ("Левина", "Ирина", "Сергеевна"), ("Сорокин", "Артём", "Денисович")]


def fio(i):
    s, n, p = CLIENTS[i]
    return f"{s} {n} {p}"


def short(i):
    s, n, p = CLIENTS[i]
    return f"{s} {n[0]}.{p[0]}."


# ---- statement documents -----------------------------------------------------------------------------
DOCS = []  # one dict per bank document
TRUTH = {}  # label -> expected outcome per leg


def foreign_acct(seed, person=False):
    return ("40817810" if person else "40702810") + "9" + f"{int(seed) % 10**11:011d}"


def cp_legal(name, inn):
    return {"name": name, "inn": inn, "acct": foreign_acct(inn), "bank": 'АО "Банк-Другой"', "bik": "044525777",
            "corr": "30101810000000000777", "legal": True}


def cp_person(i, n):
    return {"name": fio(i), "inn": "", "acct": foreign_acct(n, True), "bank": 'АО "Банк-Другой"',
            "bik": "044525777", "corr": "30101810000000000777", "legal": False}


def add(label, kind, book, amount, cp, purpose, number, doc_type="Платежное поручение", doc_date=None,
        files=None, own=ACC_M, category=None, status="ok", dup_of=None, comma=False):
    """kind in|out: money flow for the clinic account `own`. amount > 0 kopecks."""
    DOCS.append(dict(label=label, kind=kind, book=book, amount=amount, cp=cp, purpose=purpose, number=number,
                     doc_type=doc_type, doc_date=doc_date or book, files=files, own=own, comma=comma))
    TRUTH[label] = dict(category=category, status=status, dup_of=dup_of,
                        kind="in" if kind == "in" else "out", transfer=False)


def add_transfer(label, book, amount, src, dst, purpose, number):
    DOCS.append(dict(label=label, kind="transfer", book=book, amount=amount, src=src, dst=dst, purpose=purpose,
                     number=number, doc_type="Платежное поручение", doc_date=book, files=None, own=None, comma=False))
    TRUTH[label] = dict(category=None, status="ok", dup_of=None, kind="transfer", transfer=True)


LANDLORD = cp_legal('ООО "Парк-Аренда"', "7701000011")
VETSNAB = cp_legal('ООО "Вет-Снаб"', "7702000022")
VETSNAB_PLUS = cp_legal('ООО "Вет-Снаб Плюс"', "7702000033")
ENERGO = cp_legal('АО "Энергосбыт"', "7703000044")
LAB = cp_legal('ООО "ВетЛаб-Диагностика"', "7704000055")
FNS = cp_legal("УФК по г. Москве (ИФНС России № 7 по г. Москве)", "7707000066")
ZOO = cp_legal('ООО "Зоопитомник Альфа"', "7705000088")
KINO = cp_legal('ООО "Кинолог-Центр"', "7706000099")
IP = {"name": "ИП Козлов Андрей Викторович", "inn": "773300000012", "acct": foreign_acct(773300000012),
      "bank": 'АО "Банк-Другой"', "bik": "044525777", "corr": "30101810000000000777", "legal": True}
BANKCP = {"name": BANK["name"], "inn": BANK["inn"], "acct": "30232810000000000001", "bank": BANK["name"],
          "bik": BANK["bik"], "corr": BANK["corr"], "legal": True}

# ---- Vetmanager export (built first: card batches drive the acquiring credits) ------------------------
CASH_PAY = [(D(1), 620000), (D(2), 315050), (D(8), 990000), (D(15), 420000), (D(22), 735025), (D(29), 280000)]
CARD_PAY = [(D(2), 1240000), (D(2), 860000), (D(3), 1550000), (D(3), 450000), (D(4), 1350000), (D(5), 550000),
            (D(6), 300000), (D(14), 900000), (D(14), 600000), (D(14), 300000), (D(21), 1600000),
            (D(28), 1400000), (D(28), 1100000), (D(29), 1400000), (D(30), 900000)]
UNPAID = [(D(9), 540000), (D(16), 1275000), (D(23), 312000)]
DELETED = [(D(10), 800000)]


def next_business_day(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def commission(gross):
    return (gross * RATE_BP + 5000) // 10000  # half up; all gross values here divide exactly


def card_batches():
    b = {}
    for d, a in CARD_PAY:
        b.setdefault(next_business_day(d), []).append((d, a))
    return dict(sorted(b.items()))


# Acquiring credits as the bank pays them (bank behaviour, hand-written):
#   (sale days covered, credit date, kopecks to subtract from the tariff-based net)
# 03.09 / 07.09: normal, 04.09: rounding noise of 30 kop (inside tolerance), 07.09 covers Fri+Sat+Sun,
# 15.09: bank charged 2.5 % instead of the 1.9 % tariff (under-payment), 24.09: paid after 3 business days,
# 30.09: ONE sum for two sale days (28 and 29), sale day 30.09 has no credit yet (pending at month end).
BANK_GROUPS = [([D(2)], D(3), 0), ([D(3)], D(4), 30), ([D(4), D(5), D(6)], D(7), 0), ([D(14)], D(15), "rate250"),
               ([D(21)], D(24), 0), ([D(28), D(29)], D(30), 0)]
gross_by_day = {}
for _d, _a in CARD_PAY:
    gross_by_day[_d] = gross_by_day.get(_d, 0) + _a
for days_, settle, tweak in BANK_GROUPS:
    net = sum(gross_by_day[x] - commission(gross_by_day[x]) for x in days_)
    if tweak == "rate250":
        net = sum(gross_by_day[x] * (10000 - 250) // 10000 for x in days_)
    else:
        net -= tweak
    gross = sum(gross_by_day[x] for x in days_)
    dtxt = ", ".join(x.strftime("%d.%m.%Y") for x in days_)
    add(f"acq{settle.strftime('%d')}", "in", settle, net, BANKCP,
        f"Возмещение по операциям эквайринга за {dtxt}. Сумма операций {gross // 100}.{gross % 100:02d}, "
        f"к зачислению {net // 100}.{net % 100:02d}. НДС не облагается.",
        f"{7000 + settle.day}", doc_type="Банковский ордер", doc_date=days_[-1], category="Выручка (эквайринг)")

# ---- ordinary operations -----------------------------------------------------------------------------
add("d06", "out", D(2), 18000000, LANDLORD,
    "Аренда помещения за сентябрь 2026 по договору 17/А от 01.01.2026. НДС не облагается.", "0051", category="Аренда")
add("d07", "out", D(4), 9432050, VETSNAB, "Оплата по счету 4471 от 01.09.2026. НДС не облагается.", "0052",
    category="Препараты")  # FINAL state; on import it is status=check (no rule), fixed by hand in the scenario
# retroactive rule: d28 stays "check" until the rule from d07 is created, then becomes "Препараты";
# d29 is categorised BY HAND before the rule exists and must not be touched by it.
add("d28", "out", D(8), 2380000, VETSNAB, "Оплата по счету 4490 от 03.09.2026. НДС не облагается.", "0065",
    category="Препараты")  # FINAL state
add("d29", "out", D(11), 1100000, VETSNAB, "Оплата по счету 4500 от 09.09.2026. НДС не облагается.", "0066",
    category="Прочие расходы")  # FINAL state (manual)
add("d08", "out", D(7), 15000, BANKCP, "Комиссия за переводы за период 01.09.2026-06.09.2026", "7101",
    doc_type="Банковский ордер", category="Банковские комиссии")
add("d09", "out", D(8), 3890000, LAB, "Оплата анализов по договору 5 от 12.03.2026. НДС не облагается.", "0053",
    category="Лаборатория")
add("d10", "out", D(10), 2246018, ENERGO, "Оплата электроэнергии за август 2026, лицевой счет 770-4411.", "0054",
    doc_type="Платежное требование", category="Коммунальные услуги", comma=True)
add("d11", "out", D(15), 6700000, FNS, "Единый налоговый платеж. Уплата налога по УСН. НДС не облагается.", "0055",
    category="Налоги и взносы")
add("d12", "out", D(14), 31500000, BANKCP,
    "Перечисление заработной платы по реестру № 9 за первую половину сентября 2026.", "0056", category="Зарплата")
add("d27", "out", D(9), 310000, IP, "Оплата по договору", "0057", status="check")
add("d26", "out", D(17), 120000, cp_person(6, 26), f"Возврат средств за отмену приема. {short(6)}", "0059",
    status="check")
add("e6", "out", D(30), 120000, BANKCP, "Комиссия за обслуживание расчетного счета за сентябрь 2026", "7102",
    doc_type="Банковский ордер", category="Банковские комиссии")
add("e7", "out", D(28), 4120000, FNS, "Единый налоговый платеж. Страховые взносы за август 2026.", "0063",
    category="Налоги и взносы")
# supplier rule: d07 is corrected by hand with create_rule; e2/e3 (same INN) must follow the rule, e4 (other INN) must not
add("e2", "out", D(24), 6178000, VETSNAB, "Оплата по счету 4519 от 21.09.2026. НДС не облагается.", "0060",
    category="Препараты")
add("e3", "out", D(28), 5000000, VETSNAB, "Предоплата по договору поставки 12/Б", "0062", category="Препараты")
add("e4", "out", D(25), 1240000, VETSNAB_PLUS, "Оплата по счету 88", "0061", status="check")

# payments from individuals (pet owners) and companies
add("d13", "in", D(3), 450000, cp_person(0, 1), f"Оплата ветеринарных услуг по счету 118. {short(0)}", "5101",
    category="Выручка", status="duplicate", dup_of="b1")
add("d14", "in", D(9), 230000, cp_person(1, 2), f"Оплата ветеринарных услуг. {fio(1)}", "5102", category="Выручка")
add("d15", "in", D(14), 720000, cp_person(2, 3), f"Оплата ветеринарных услуг, приём 12.09. {short(2)}", "5103",
    doc_date=D(12), category="Выручка", status="duplicate", dup_of="b2")
add("d16", "in", D(20), 600000, cp_person(3, 4), "Оплата ветеринарных услуг", "5104", category="Выручка")
add("d17", "in", D(10), 340000, cp_person(4, 5), f"Оплата ветеринарных услуг. {fio(4)}", "5105", category="Выручка")
add("d18", "in", D(16), 980000, cp_person(5, 6), f"Перевод от {short(5)} за собаку", "5106", status="check")
add("d22", "in", D(11), 500000, cp_person(8, 7), f"Оплата ветеринарных услуг. {short(8)}", "7301", category="Выручка",
    status="duplicate", dup_of="b4")
add("d23", "in", D(11), 500000, cp_person(9, 8), f"Оплата ветеринарных услуг. {short(9)}", "7302", category="Выручка")
add("e1", "in", D(21), 380000, cp_person(7, 9), f"Оплата ветеринарных услуг. {fio(7)}", "5107", category="Выручка",
    files=[2])  # posted late by the bank: only in the second file
add("t1", "in", D(18), 850000, ZOO, "Оплата по счету 35 за ветеринарное обслуживание питомника", "218", status="check")
add("t2", "in", D(18), 850000, ZOO, "Оплата по счету 36 за ветеринарное обслуживание питомника", "219", status="check")
add("t3", "in", D(18), 850000, KINO, "Оплата по счету 12", "77", status="check")

add_transfer("d24", D(11), 20000000, ACC_M, ACC_R,
             "Перевод собственных средств на резервный счет. НДС не облагается.", "0058")
add_transfer("d25", D(21), 5000000, ACC_R, ACC_M,
             "Возврат собственных средств с резервного счета. НДС не облагается.", "0064")

# rows that exist in the system before the statements (bot / manual); sources are overridden to "manual" for API runs
EXISTING = [
    dict(label="b1", account="main", date="2026-09-03", amount=450000, source="bot", category="Выручка",
         description="Оплата приема (бот)", note="duplicate of d13 (same day)"),
    dict(label="b2", account="main", date="2026-09-12", amount=720000, source="bot", category="Выручка",
         description="Оплата приема (бот)", note="duplicate of d15 (bank date +2 days)"),
    dict(label="b3", account="main", date="2026-09-14", amount=600000, source="bot", category="Выручка",
         description="Оплата приема (бот)", note="NOT a duplicate of d16: 6 days apart"),
    dict(label="b4", account="main", date="2026-09-11", amount=500000, source="bot", category="Выручка",
         description="Оплата приема (бот)", note="pairs with exactly one of d22/d23 (the first by number)"),
    dict(label="m1", account="main", date="2026-09-10", amount=-340000, source="manual", category="Прочие расходы",
         description="Выплата курьеру", note="NOT a duplicate of d17: opposite sign"),
]
MANUAL_AFTER_IMPORT = dict(label="m_post", account="main", date="2026-09-09", amount=230000, source="manual",
                           category="Выручка", description="Оплата приема (ввод вручную)",
                           note="entered after file 1: becomes duplicate of d14")
TRUTH["m_post"] = dict(category="Выручка", status="duplicate", dup_of="d14", kind="in", transfer=False)
for e in EXISTING:
    TRUTH[e["label"]] = dict(category=e["category"], status="ok", dup_of=None,
                             kind="in" if e["amount"] > 0 else "out", transfer=False)


# ---- render 1C -----------------------------------------------------------------------------------------
def fm(kop, comma=False):
    s = f"{kop // 100}.{kop % 100:02d}"
    return s.replace(".", ",") if comma else s


def ds(d):
    return d.strftime("%d.%m.%Y") if d else ""


def party_lines(prefix, p):
    shown = f"ИНН {p['inn']} {p['name']}" if p["inn"] and p["legal"] else p["name"]
    lines = [f"{prefix}={shown}"]
    if p["inn"]:
        lines.append(f"{prefix}ИНН={p['inn']}")
    if p["legal"]:
        lines.append(f"{prefix}1={p['name']}")
    lines += [f"{prefix}РасчСчет={p['acct']}", f"{prefix}Банк1={p['bank']}", f"{prefix}БИК={p['bik']}",
              f"{prefix}Корсчет={p['corr']}"]
    return lines


OWNP = {"name": OWN["name"], "inn": OWN["inn"], "legal": True, "bank": BANK["name"], "bik": BANK["bik"],
        "corr": BANK["corr"]}


def doc_lines(d):
    if d["kind"] == "transfer":
        payer, receiver = dict(OWNP, acct=d["src"]), dict(OWNP, acct=d["dst"])
        debit = credit = d["book"]
        pacct, racct = d["src"], d["dst"]
    elif d["kind"] == "in":
        payer, receiver = d["cp"], dict(OWNP, acct=d["own"])
        debit, credit = None, d["book"]
        pacct, racct = d["cp"]["acct"], d["own"]
    else:
        payer, receiver = dict(OWNP, acct=d["own"]), d["cp"]
        debit, credit = d["book"], None
        pacct, racct = d["own"], d["cp"]["acct"]
    lines = ["СекцияДокумент=" + d["doc_type"], f"Номер={d['number']}", f"Дата={ds(d['doc_date'])}",
             f"Сумма={fm(d['amount'], d['comma'])}", f"ПлательщикСчет={pacct}", f"ДатаСписано={ds(debit)}"]
    lines += party_lines("Плательщик", payer)
    lines += [f"ПолучательСчет={racct}", f"ДатаПоступило={ds(credit)}"]
    lines += party_lines("Получатель", receiver)
    lines += ["ВидПлатежа=Электронно", "ВидОплаты=01", "Очередность=5", f"НазначениеПлатежа={d['purpose']}",
              "КонецДокумента"]
    return lines


def legs_of(d):
    """[(own_account, signed_amount, booked_date)] for every clinic account touched by the document."""
    if d["kind"] == "transfer":
        return [(d["src"], -d["amount"], d["book"]), (d["dst"], d["amount"], d["book"])]
    return [(d["own"], d["amount"] if d["kind"] == "in" else -d["amount"], d["book"])]


def in_files(d):
    if d["files"]:
        return d["files"]
    out = []
    accs = {a for a, _, _ in legs_of(d)}
    if d["book"] <= FILE1_TO:
        out.append(1)
    if d["book"] >= FILE2_START and ACC_M in accs:
        out.append(2)
    return out


OPENING = {ACC_M: 125000000, ACC_R: 30000000}


def render(fileno, d_from, d_to, accounts, repeat_label=None):
    docs = [d for d in DOCS if fileno in in_files(d)]
    docs.sort(key=lambda d: (d["book"], d["number"]))
    head = ["1CClientBankExchange", "ВерсияФормата=1.03", "Кодировка=Windows", "Отправитель=Банк-Пример",
            "Получатель=", f"ДатаСоздания={ds(d_to + timedelta(days=1))}", "ВремяСоздания=08:15:00",
            f"ДатаНачала={ds(d_from)}", f"ДатаКонца={ds(d_to)}"]
    head += [f"РасчСчет={a}" for a in accounts]
    head += ["Документ=Платежное поручение", "Документ=Платежное требование", "Документ=Банковский ордер"]
    secs = []
    for a in accounts:
        before = OPENING[a] + sum(s for dd in DOCS for (ac, s, b) in legs_of(dd) if ac == a and b < d_from)
        legs = [s for dd in docs for (ac, s, b) in legs_of(dd) if ac == a and d_from <= b <= d_to]
        tin = sum(s for s in legs if s > 0)
        tout = -sum(s for s in legs if s < 0)
        secs += ["СекцияРасчСчет", f"ДатаНачала={ds(d_from)}", f"ДатаКонца={ds(d_to)}", f"РасчСчет={a}",
                 f"НачальныйОстаток={fm(before)}", f"ВсегоПоступило={fm(tin)}", f"ВсегоСписано={fm(tout)}",
                 f"КонечныйОстаток={fm(before + tin - tout)}", "КонецРасчСчет"]
    body = []
    for d in docs:
        body += doc_lines(d)
        if d["label"] == repeat_label:  # the bank exported this document twice
            body += doc_lines(d)
    text = "\r\n".join(head + secs + body + ["КонецФайла"]) + "\r\n"
    return text.encode("cp1251")


(OUT / "bank_statement_1.txt").write_bytes(render(1, D(1), FILE1_TO, [ACC_M, ACC_R], repeat_label="d09"))
(OUT / "bank_statement_2.txt").write_bytes(render(2, D(15), D(30), [ACC_M]))


# ---- Vetmanager (assumed REST API shape: {"success", "data": {"totalCount", "<entity>": [...]}}) --------
def wrap(entity, rows):
    return {"success": True, "message": "Records Retrieved Successfully",
            "data": {"totalCount": str(len(rows)), entity: rows}}


def m4(kop):
    return f"{kop // 100}.{kop % 100:02d}00"


GOODS = [("1", "Первичный приём", 1), ("2", "Вакцинация", 1), ("3", "УЗИ", 1), ("4", "Хирургия", 1),
         ("11", "Корм лечебный", 0), ("12", "Препарат", 0)]
invoices_src = ([(d, a, "exec", "cash") for d, a in CASH_PAY] + [(d, a, "exec", "card") for d, a in CARD_PAY]
                + [(d, a, "save", None) for d, a in UNPAID] + [(d, a, "deleted", None) for d, a in DELETED])
invoices_src.sort(key=lambda x: (x[0], x[1]))
clients, pets, admissions, invoices, lines, payments = [], [], [], [], [], []
for n, (d, a, st, method) in enumerate(invoices_src):
    cid, pid, aid, iid = str(100 + n), str(200 + n), str(300 + n), str(400 + n)
    s, nm, pt = CLIENTS[n]
    clients.append({"id": cid, "last_name": s, "first_name": nm, "middle_name": pt,
                    "address": f"г. Москва, ул. Примерная, д. {n + 1}, кв. {n + 10}",
                    "cell_phone": f"+7 (916) 100-00-{n + 10:02d}", "home_phone": "",
                    "email": f"owner{n + 1}@example.test", "status": "ACTIVE", "balance": "0.0000"})
    pets.append({"id": pid, "owner_id": cid, "alias": ["Бусинка", "Рекс", "Мурка", "Барсик", "Шарик"][n % 5],
                 "type_id": "1" if n % 2 else "2", "sex": "male" if n % 2 else "female"})
    doc_idx = n % 3
    note = f"Со слов владельца {s}: вялость, отказ от корма." if n == 0 else "Осмотр, назначения выданы."
    stamp = f"{d.isoformat()} {9 + n % 8:02d}:{(n * 7) % 60:02d}:00"
    admissions.append({"id": aid, "client_id": cid, "patient_id": pid, "user_id": str(10 + doc_idx),
                       "admission_date": stamp, "status": "delete" if st == "deleted" else "save",
                       "description": note})
    invoices.append({"id": iid, "client_id": cid, "pet_id": pid, "user_id": str(10 + doc_idx),
                     "invoice_date": stamp, "amount": m4(a), "status": st, "description": ""})
    svc = a * 70 // 100
    goods = a - svc
    ls = [(str(1 + n % 4), 1, svc)]
    gid = "11" if n % 2 else "12"
    if goods % 2 == 0 and goods:
        ls.append((gid, 2, goods))
    elif goods:
        ls.append((gid, 1, goods))
    for k, (g, q, amt) in enumerate(ls):
        lines.append({"id": str(500 + n * 2 + k), "invoice_id": iid, "good_id": g, "quantity": f"{q}.0000",
                      "price": m4(amt // q)})
    if method:
        payments.append({"id": str(600 + n), "client_id": cid, "invoice_id": iid,
                         "cassa_id": "1" if method == "cash" else "2", "amount": m4(a), "status": "exec",
                         "create_date": f"{d.isoformat()} {10 + n % 8:02d}:{(n * 11) % 60:02d}:00",
                         "description": ""})
users = [{"id": str(10 + i), "last_name": a, "first_name": b, "middle_name": c, "is_active": "1",
          "position_id": "1"} for i, (a, b, c) in enumerate(DOCTORS)]
goods_rows = [{"id": g, "title": t, "is_service": str(s)} for g, t, s in GOODS]
cassa = [{"id": "1", "title": "Касса (наличные)", "type": "cash"},
         {"id": "2", "title": "Эквайринг (терминал)", "type": "card"}]
for name, rows in [("client", clients), ("pet", pets), ("user", users), ("admission", admissions),
                   ("invoice", invoices), ("invoiceDocument", lines), ("good", goods_rows),
                   ("payment", payments), ("cassa", cassa)]:
    (OUT / "vetmanager" / f"{name}.json").write_text(
        json.dumps(wrap(name, rows), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

# ---- initial state, rules, truth ---------------------------------------------------------------------
CATEGORIES = [("Выручка", "income"), ("Выручка (эквайринг)", "income"), ("Аренда", "expense"),
              ("Препараты", "expense"), ("Лаборатория", "expense"), ("Коммунальные услуги", "expense"),
              ("Налоги и взносы", "expense"), ("Зарплата", "expense"), ("Банковские комиссии", "expense"),
              ("Прочие расходы", "expense")]
RULES = [
    {"match": "text", "value": "эквайринга", "direction": "in", "category": "Выручка (эквайринг)"},
    {"match": "inn", "value": LANDLORD["inn"], "direction": None, "category": "Аренда"},
    {"match": "inn", "value": ENERGO["inn"], "direction": None, "category": "Коммунальные услуги"},
    {"match": "inn", "value": LAB["inn"], "direction": None, "category": "Лаборатория"},
    {"match": "text", "value": "единый налоговый платеж", "direction": "out", "category": "Налоги и взносы"},
    {"match": "text", "value": "заработной платы", "direction": "out", "category": "Зарплата"},
    {"match": "text", "value": "комиссия за", "direction": "out", "category": "Банковские комиссии"},
    {"match": "text", "value": "ветеринарных услуг", "direction": "in", "category": "Выручка"},
]
USER_RULE = {"created_from": "d07", "match": "inn", "value": VETSNAB["inn"], "direction": None,
             "category": "Препараты"}
initial = {
    "clinic": {"name": "Клиника «Лапа» (набор 2)", "inn": OWN["inn"], "timezone": "Europe/Moscow"},
    "accounts": [
        {"key": "main", "name": "Расчётный счёт", "kind": "bank", "number": ACC_M,
         "opening_balance": OPENING[ACC_M], "opening_date": "2026-09-01"},
        {"key": "reserve", "name": "Резервный счёт", "kind": "bank", "number": ACC_R,
         "opening_balance": OPENING[ACC_R], "opening_date": "2026-09-01"},
        {"key": "cash", "name": "Касса", "kind": "cash", "number": None, "opening_balance": 5000000,
         "opening_date": "2026-09-01"},
    ],
    "categories": [{"name": n, "type": t} for n, t in CATEGORIES],
    "starter_rules": RULES,
    "acquiring": ACQ_PARAMS,
    "existing_transactions": EXISTING,
    "manual_after_first_import": MANUAL_AFTER_IMPORT,
    "manual_category_before_rule": {"label": "d29", "category": "Прочие расходы"},
    "user_rule_from_edit": USER_RULE,
}
(OUT / "initial.json").write_text(json.dumps(initial, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
(OUT / "truth.json").write_text(json.dumps({
    "legs": TRUTH,
    "numbers": {d["label"]: d["number"] for d in DOCS},
    "pii_surnames": sorted({c[0] for c in CLIENTS}),
    "pii_phones": sorted({c["cell_phone"] for c in clients}),
    "pii_addresses": sorted({c["address"] for c in clients}),
    "pii_emails": sorted({c["email"] for c in clients}),
    "ambiguity_pair": {"existing": "b4", "candidates": ["d22", "d23"], "kept_pair": "d22"},
    "note": "Hand-written labels: what the product SHOULD produce. expected.json is cross-checked against them.",
}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

# surnames must not occur in non-person counterparty names
for p in [LANDLORD, VETSNAB, VETSNAB_PLUS, ENERGO, LAB, FNS, ZOO, KINO, IP, BANKCP]:
    assert not any(c[0].casefold() in p["name"].casefold() for c in CLIENTS), p["name"]
print("generated", len(DOCS), "documents;", len(invoices), "invoices;", len(payments), "payments")
