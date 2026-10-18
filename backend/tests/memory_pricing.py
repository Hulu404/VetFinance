"""In-memory stage 5 data layer: services, settings, techcards, stock for prices, hours of doctors, rooms."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from app.rows import ServiceRecord
from engine.dashboard_inputs import SaleInput, SaleLineInput
from engine.efficiency_inputs import RoomBookingInput, RoomInput
from engine.pricing_inputs import (
    ServiceSettingInput,
    StockBatchInput,
    StockItemInput,
    TechcardInput,
    TechcardLineInput,
)
from engine.vetmanager import Sale, Service


class MemoryPricing:
    """Mixin of MemoryRepo; `new_id`, `sales`, `doctor_hours` come from the host."""

    def init_pricing(self) -> None:
        self.services: list[ServiceRecord] = []
        self.service_settings: dict[str, tuple[int | None, int | None]] = {}
        self.recipes: dict[str, list[TechcardLineInput]] = {}
        self.pricing_items: list[StockItemInput] = []
        self.pricing_batches: list[StockBatchInput] = []
        self.hours: dict[str, Decimal | None] = {}
        self.avg_visit_minutes = 30
        self.rooms: list[RoomInput] = []
        self.room_bookings: list[RoomBookingInput] = []

    new_id: Any
    sales: dict[str, Sale]

    async def upsert_service(self, service: Service) -> str:
        for i, rec in enumerate(self.services):
            if rec.external_id == service.external_id:
                new = ServiceRecord(
                    rec.id, "vetmanager", rec.external_id, service.name, service.group, None
                )
                self.services[i] = new
                return "same" if new == rec else "updated"
        self.services.append(
            ServiceRecord(
                self.new_id(), "vetmanager", service.external_id, service.name, service.group, None
            )
        )
        return "new"

    async def list_services(self) -> list[ServiceRecord]:
        return sorted(self.services, key=lambda s: (s.name, s.id))

    async def get_service(self, service_id: str) -> ServiceRecord | None:
        return next((s for s in self.services if s.id == service_id), None)

    async def create_manual_service(
        self, name: str, group: str | None, price: int
    ) -> ServiceRecord:
        rec = ServiceRecord(self.new_id(), "manual", None, name, group, price)
        self.services.append(rec)
        return rec

    async def update_manual_service(self, service_id: str, changes: dict[str, Any]) -> None:
        for i, rec in enumerate(self.services):
            if rec.id == service_id and rec.source == "manual":
                self.services[i] = ServiceRecord(
                    rec.id, rec.source, None, changes.get("name", rec.name),
                    changes.get("group", rec.group) if "group" in changes else rec.group,
                    changes.get("price", rec.manual_price),
                )  # fmt: skip

    async def delete_manual_service(self, service_id: str) -> None:
        self.services = [
            s for s in self.services if not (s.id == service_id and s.source == "manual")
        ]
        self.service_settings.pop(service_id, None)
        self.recipes.pop(service_id, None)

    async def list_service_settings(self) -> list[ServiceSettingInput]:
        out = []
        for s in await self.list_services():
            minutes, pct = self.service_settings.get(s.id, (None, None))
            out.append(ServiceSettingInput(s.id, s.name, s.group, minutes, pct))
        return out

    async def list_techcards(self) -> list[TechcardInput]:
        return [TechcardInput(k, tuple(v)) for k, v in self.recipes.items()]

    async def save_recipe(
        self,
        service_id: str,
        minutes: int | None,
        doctor_pct_bp: int | None,
        lines: Sequence[TechcardLineInput],
    ) -> None:
        self.service_settings[service_id] = (minutes, doctor_pct_bp)
        self.recipes[service_id] = list(lines)

    async def list_pricing_stock_items(self) -> list[StockItemInput]:
        return sorted(self.pricing_items, key=lambda i: (i.name, i.id))

    async def list_pricing_batches(self) -> list[StockBatchInput]:
        return list(self.pricing_batches)

    async def list_pricing_sales(self, first: date, last: date) -> list[SaleInput]:
        ids = {s.external_id: s.id for s in self.services if s.external_id}
        return [
            SaleInput(
                s.date, s.status,
                tuple(
                    SaleLineInput(
                        x.kind, x.amount, ids.get(x.service_external_id or ""), x.name, x.qty, x.price
                    )
                    for x in s.lines
                ),
                s.external_id,
            )
            for s in self.sales.values()
            if first <= s.date <= last
        ]  # fmt: skip

    async def get_avg_visit_minutes(self) -> int:
        return self.avg_visit_minutes

    async def set_avg_visit_minutes(self, minutes: int) -> None:
        self.avg_visit_minutes = minutes

    async def list_rooms(self) -> list[RoomInput]:
        return list(self.rooms)

    async def list_room_bookings(self, first: date, last: date) -> list[RoomBookingInput]:
        return [b for b in self.room_bookings if first <= b.date <= last]
