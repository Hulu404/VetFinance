"""Postgres queries of stage 5: services, settings, techcards, stock for prices, hours of doctors, rooms.

A mixin of PgRepository; every query is limited to the clinic of the connection (RLS applies as well).
"""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.rows import ServiceRecord
from engine.dashboard_inputs import SaleInput, SaleLineInput
from engine.efficiency_inputs import DoctorInput, RoomBookingInput, RoomInput, ScheduleSlotInput
from engine.pricing_inputs import (
    ServiceSettingInput,
    StockBatchInput,
    StockItemInput,
    TechcardInput,
    TechcardLineInput,
)

_SERVICE_COLS = "id::text, source, external_id, name, group_name, manual_price"
_EDITABLE = {"name": "name", "group": "group_name", "price": "manual_price"}


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class PgPricing:
    _conn: AsyncConnection

    async def _clinic(self) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------ services
    async def list_services(self) -> list[ServiceRecord]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(f"select {_SERVICE_COLS} from services where clinic_id = :cid order by name, id"),  # noqa: S608
            {"cid": cid},
        )
        return [ServiceRecord(*r) for r in res.all()]

    async def get_service(self, service_id: str) -> ServiceRecord | None:
        key = _uuid_or_none(service_id)
        if key is None:
            return None
        cid = await self._clinic()
        res = await self._conn.execute(
            text(f"select {_SERVICE_COLS} from services where clinic_id = :cid and id = :id"),  # noqa: S608
            {"cid": cid, "id": key},
        )
        row = res.first()
        return None if row is None else ServiceRecord(*row)

    async def create_manual_service(
        self, name: str, group: str | None, price: int
    ) -> ServiceRecord:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "insert into services (clinic_id, source, name, group_name, manual_price) "  # noqa: S608
                f"values (:cid, 'manual', :name, :grp, :price) returning {_SERVICE_COLS}"
            ),
            {"cid": cid, "name": name, "grp": group, "price": price},
        )
        return ServiceRecord(*res.one())

    async def update_manual_service(self, service_id: str, changes: dict[str, Any]) -> None:
        cid = await self._clinic()
        sets = [f"{_EDITABLE[k]} = :{k}" for k in changes if k in _EDITABLE]
        if not sets:
            return
        await self._conn.execute(
            text(
                f"update services set {', '.join(sets)} "  # noqa: S608
                "where clinic_id = :cid and id = :id and source = 'manual'"
            ),
            {**changes, "cid": cid, "id": uuid.UUID(service_id)},
        )

    async def delete_manual_service(self, service_id: str) -> None:
        cid = await self._clinic()
        await self._conn.execute(
            text("delete from services where clinic_id = :cid and id = :id and source = 'manual'"),
            {"cid": cid, "id": uuid.UUID(service_id)},
        )

    # ------------------------------------------------------------ settings and techcards
    async def list_service_settings(self) -> list[ServiceSettingInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select s.id::text, s.name, s.group_name, ss.minutes, ss.doctor_pct_bp from services s "
                "left join service_settings ss on ss.service_id = s.id and ss.clinic_id = s.clinic_id "
                "where s.clinic_id = :cid order by s.name, s.id"
            ),
            {"cid": cid},
        )
        return [ServiceSettingInput(*r) for r in res.all()]

    async def list_techcards(self) -> list[TechcardInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select t.service_id::text, l.item_id::text, l.qty, l.part from techcards t "
                "left join techcard_lines l on l.service_id = t.service_id and l.clinic_id = t.clinic_id "
                "where t.clinic_id = :cid order by t.service_id, l.sort_order, l.id"
            ),
            {"cid": cid},
        )
        cards: dict[str, list[TechcardLineInput]] = {}
        for service_id, item_id, qty, part in res.all():
            lines = cards.setdefault(str(service_id), [])
            if item_id is not None:
                lines.append(TechcardLineInput(str(item_id), Decimal(qty), str(part)))
        return [TechcardInput(k, tuple(v)) for k, v in cards.items()]

    async def save_recipe(
        self,
        service_id: str,
        minutes: int | None,
        doctor_pct_bp: int | None,
        lines: Sequence[TechcardLineInput],
    ) -> None:
        cid, sid = await self._clinic(), uuid.UUID(service_id)
        await self._conn.execute(
            text(
                "insert into service_settings (service_id, clinic_id, minutes, doctor_pct_bp) "
                "values (:sid, :cid, :minutes, :pct) on conflict (service_id) do update set "
                "minutes = excluded.minutes, doctor_pct_bp = excluded.doctor_pct_bp"
            ),
            {"sid": sid, "cid": cid, "minutes": minutes, "pct": doctor_pct_bp},
        )
        await self._conn.execute(
            text(
                "insert into techcards (service_id, clinic_id) values (:sid, :cid) "
                "on conflict (service_id) do update set updated_at = now()"
            ),
            {"sid": sid, "cid": cid},
        )
        await self._conn.execute(
            text("delete from techcard_lines where clinic_id = :cid and service_id = :sid"),
            {"sid": sid, "cid": cid},
        )
        for order, line in enumerate(lines):
            await self._conn.execute(
                text(
                    "insert into techcard_lines (clinic_id, service_id, item_id, part, qty, sort_order) "
                    "values (:cid, :sid, :item, :part, :qty, :ord)"
                ),
                {"cid": cid, "sid": sid, "item": uuid.UUID(line.item_id), "part": line.part,
                 "qty": line.qty, "ord": order},
            )  # fmt: skip

    # ------------------------------------------------------------ stock, sales, doctors, rooms
    async def list_pricing_stock_items(self) -> list[StockItemInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select id::text, name, unit from stock_items where clinic_id = :cid order by name, id"
            ),
            {"cid": cid},
        )
        return [StockItemInput(*r) for r in res.all()]

    async def list_pricing_batches(self) -> list[StockBatchInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select id::text, item_id::text, qty, unit_cost, received_on, expires_on "
                "from stock_batches where clinic_id = :cid order by received_on nulls first, id"
            ),
            {"cid": cid},
        )
        return [StockBatchInput(r[0], r[1], Decimal(r[2]), r[3], r[4], r[5]) for r in res.all()]

    async def list_pricing_sales(self, first: date, last: date) -> list[SaleInput]:
        cid = await self._clinic()
        ids = await self._conn.execute(
            text(
                "select external_id, id::text from services where clinic_id = :cid and external_id is not null"
            ),
            {"cid": cid},
        )
        service_ids = {str(r[0]): str(r[1]) for r in ids.all()}
        res = await self._conn.execute(
            text(
                "select external_id, date, status, lines from sales "
                "where clinic_id = :cid and date between :first and :last"
            ),
            {"cid": cid, "first": first, "last": last},
        )
        return [
            SaleInput(day, status, tuple(_line(x, service_ids) for x in lines), ext)
            for ext, day, status, lines in res.all()
        ]

    async def list_doctor_inputs(self) -> list[DoctorInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select id::text, code, name, hours_per_week from doctors where clinic_id = :cid order by code, id"
            ),
            {"cid": cid},
        )
        return [
            DoctorInput(r[0], r[1], r[2], None if r[3] is None else Decimal(r[3]))
            for r in res.all()
        ]

    async def set_doctor_hours(self, hours: dict[str, Decimal | None]) -> None:
        cid = await self._clinic()
        for doctor_id, value in hours.items():
            await self._conn.execute(
                text("update doctors set hours_per_week = :h where clinic_id = :cid and id = :id"),
                {"h": value, "cid": cid, "id": uuid.UUID(doctor_id)},
            )

    async def get_avg_visit_minutes(self) -> int:
        cid = await self._clinic()
        res = await self._conn.execute(
            text("select avg_visit_minutes from clinics where id = :cid"), {"cid": cid}
        )
        return int(res.scalar_one())

    async def set_avg_visit_minutes(self, minutes: int) -> None:
        cid = await self._clinic()
        await self._conn.execute(
            text("update clinics set avg_visit_minutes = :m where id = :cid"),
            {"m": minutes, "cid": cid},
        )

    async def list_rooms(self) -> list[RoomInput]:
        cid = await self._clinic()
        rooms = await self._conn.execute(
            text(
                "select id::text, name, has_schedule from rooms where clinic_id = :cid order by name, id"
            ),
            {"cid": cid},
        )
        slots = await self._conn.execute(
            text(
                "select room_id::text, weekday, from_min, to_min from room_schedule_slots where clinic_id = :cid"
            ),
            {"cid": cid},
        )
        by_room: dict[str, list[ScheduleSlotInput]] = {}
        for room_id, weekday, start, end in slots.all():
            by_room.setdefault(str(room_id), []).append(ScheduleSlotInput(weekday, start, end))
        return [
            RoomInput(r[0], r[1], tuple(by_room.get(r[0], [])) if r[2] else None)
            for r in rooms.all()
        ]

    async def list_room_bookings(self, first: date, last: date) -> list[RoomBookingInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select date, room_id::text, minutes from room_bookings "
                "where clinic_id = :cid and date between :first and :last"
            ),
            {"cid": cid, "first": first, "last": last},
        )
        return [RoomBookingInput(*r) for r in res.all()]


def _line(raw: dict[str, Any], service_ids: dict[str, str]) -> SaleLineInput:
    ext = raw.get("service_id")
    return SaleLineInput(
        str(raw["kind"]),
        int(raw["amount"]),
        service_ids.get(str(ext)) if ext else None,
        str(raw.get("name") or ""),
        Decimal(str(raw.get("qty", 1))),
        int(raw.get("price", 0)),
    )
