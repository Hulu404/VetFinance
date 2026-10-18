"""Input rows of the efficiency engine (stage 5): doctors with hours, rooms with schedules and their bookings."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DoctorInput:
    id: str
    code: str  # "D1": the only form of a doctor that may leave the backend towards the AI layer
    name: str
    hours_per_week: Decimal | None  # reception hours per week entered by the owner; None: not set


@dataclass(frozen=True)
class ScheduleSlotInput:
    weekday: int  # 0 = Monday
    from_min: int  # minutes from midnight
    to_min: int


@dataclass(frozen=True)
class RoomInput:
    id: str
    name: str
    schedule: tuple[ScheduleSlotInput, ...] | None  # None: Vetmanager gave no schedule of the room


@dataclass(frozen=True)
class RoomBookingInput:
    date: date
    room_id: str
    minutes: int
