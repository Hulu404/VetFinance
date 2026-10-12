"""Import of a bank statement in the 1C format: parse, plan with the engine, store in one transaction.

Nothing is stored before every check has passed, and the whole import runs inside the request
transaction, so an error leaves the database as it was. The file itself is never stored: it contains
names of pet owners, only its hash and the counters are kept (raw_events).
"""

import hashlib
from datetime import date, timedelta

from app.errors import ApiError, not_found, rate_limited, validation_reason
from app.repo import Repository
from app.rows import AccountRow, NewTx
from app.schemas_tx import ImportOut, NamedRefOut, PeriodOut
from app.services.present import engine_rules
from engine.bank_1c import (
    NewOperation,
    ParsedStatement,
    StatementFormatError,
    UnknownAccountError,
    parse_1c_statement,
    statement_to_operations,
)
from engine.importing import ImportPlan, plan_import

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_IMPORTS_PER_MINUTE = 10
RATE_WINDOW_SECONDS = 60
DEDUP_WINDOW_DAYS = 3
SOURCE = "bank"
EVENT_SOURCE = "bank_statement"
TAIL = 4


def _parse(raw: bytes) -> ParsedStatement:
    if not raw.strip():
        raise validation_reason("empty", "В файле нет операций. Проверьте период выписки.")
    if len(raw) > MAX_FILE_BYTES:
        raise validation_reason(
            "too_large", "Файл больше 10 МБ. Выгрузите выписку за меньший период."
        )
    try:
        return parse_1c_statement(raw)
    except StatementFormatError as exc:
        raise validation_reason("unsupported_format", str(exc)) from exc


def _mismatch(account_number: str) -> ApiError:
    return validation_reason(
        "account_mismatch",
        "В выписке есть счёт, которого нет в клинике, или он не совпадает с выбранным.",
        account_tail=account_number[-TAIL:],
    )


def _own_numbers(accounts: list[AccountRow]) -> dict[str, str]:
    return {a.number: a.id for a in accounts if a.number}


def _operations(
    parsed: ParsedStatement, accounts: list[AccountRow], selected: str | None
) -> tuple[list[NewOperation], AccountRow]:
    """Operations of the file and the account the answer talks about."""
    own = _own_numbers(accounts)
    by_number = {a.number: a for a in accounts if a.number}
    chosen: AccountRow | None = None
    if selected is not None:
        chosen = next((a for a in accounts if a.id == selected), None)
        if chosen is None:
            raise not_found("Счёт не найден.")
        in_file = {s.account_number for s in parsed.sections}
        if chosen.number is None or chosen.number not in in_file:
            raise _mismatch(parsed.sections[0].account_number)
    try:
        operations = statement_to_operations(parsed, own)
    except UnknownAccountError as exc:
        raise _mismatch(exc.account_number) from exc
    return operations, chosen or by_number[parsed.sections[0].account_number]


def _to_new_tx(plan: ImportPlan, import_id: str) -> list[NewTx]:
    rows: list[NewTx] = []
    for planned in plan.rows:
        op = planned.op
        digest = hashlib.sha256(
            f"{op.date.isoformat()}|{op.amount}|{op.description}".encode()
        ).hexdigest()
        rows.append(
            NewTx(
                account_id=planned.account_id,
                date=op.date,
                description=op.description,
                amount=op.amount,
                kind=op.kind,
                source=SOURCE,
                status=planned.status,
                external_id=op.external_id,
                category_id=planned.category,
                category_source="rule" if planned.category else None,
                rule_id=planned.rule_id,
                counterparty_inn=op.counterparty_inn,
                counterparty_name=op.counterparty_name,
                doc_number=op.number,
                transfer_group=op.transfer_group,
                duplicate_of=planned.duplicate_of,
                duplicate_state="pending" if planned.duplicate_of else None,
                import_id=import_id,
                dedup_hash=digest,
            )
        )
    return rows


async def import_bank_statement(repo: Repository, raw: bytes, account_id: str | None) -> ImportOut:
    if (
        await repo.count_recent_raw_events(EVENT_SOURCE, RATE_WINDOW_SECONDS)
        >= MAX_IMPORTS_PER_MINUTE
    ):
        raise rate_limited("Слишком много загрузок подряд. Подождите минуту.", RATE_WINDOW_SECONDS)
    parsed = _parse(raw)
    accounts = await repo.list_account_rows()
    operations, shown = _operations(parsed, accounts, account_id)
    own = _own_numbers(accounts)
    dates = [o.date for o in operations]
    window = timedelta(days=DEDUP_WINDOW_DAYS)
    candidates = (
        await repo.duplicate_candidates(min(dates) - window, max(dates) + window) if dates else []
    )
    known = await repo.existing_external_ids(SOURCE, [o.external_id for o in operations])
    rules = engine_rules(await repo.list_rules())
    plan = plan_import(operations, own, known, rules, candidates, DEDUP_WINDOW_DAYS)
    period = _period(parsed, dates)
    import_id = await repo.add_raw_event(
        EVENT_SOURCE,
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        {
            "sections": len(parsed.sections),
            "documents": len(parsed.documents),
            "period": [period.from_.isoformat(), period.to.isoformat()],
            "loaded": plan.loaded,
            "duplicates": plan.duplicates,
            "to_check": plan.to_check,
            "already_loaded": plan.already_loaded,
            "skipped": parsed.skipped,
        },
    )
    await repo.insert_transactions(_to_new_tx(plan, import_id))
    by_number = {a.number: a for a in accounts if a.number}
    for section in parsed.sections:
        if section.date_to is not None:
            await repo.set_last_statement_to(by_number[section.account_number].id, section.date_to)
    return ImportOut(
        import_id=import_id,
        account=NamedRefOut(id=shown.id, name=shown.name),
        period=period,
        loaded=plan.loaded,
        duplicates=plan.duplicates,
        to_check=plan.to_check,
        already_loaded=plan.already_loaded,
        skipped=parsed.skipped,
    )


def _period(parsed: ParsedStatement, dates: list[date]) -> PeriodOut:
    starts = [s.date_from for s in parsed.sections if s.date_from]
    ends = [s.date_to for s in parsed.sections if s.date_to]
    pool = starts + ends + dates
    if not pool:
        raise validation_reason("empty", "В файле нет операций. Проверьте период выписки.")
    return PeriodOut(from_=min(starts or pool), to=max(ends or pool))
