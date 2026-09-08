# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Clarity tour: what the clarity analyzer rewards and penalizes, on a hotel-reservation domain.

Four scenarios, each at a different naming-quality tier, wired identically — the only variable
is the vocabulary:

1. **Guest books a room** — excellent, domain-specific naming (``ReservationService``).
2. **Booking via manager** — adequate but less expressive naming (``BookingManager``).
3. **Legacy data processing** — intentionally weak naming (``DataProcessor``) that the analyzer
   should penalize.
4. **Guest repository operations** — a cohesion mismatch: one class, three unrelated jobs.

After the four traces the example feeds them to :func:`narrativetrace_clarity.analyze` and prints
the per-scenario reports plus the suite summary, so every score connects back to the names that
caused it. Run it::

    python -m examples.hotel_booking
    python -m examples.demo --example hotel_booking
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from narrativetrace_clarity import analyze, render, render_suite_report

from examples.tour import TREE, Scenario, narrated_run, walk
from narrativetrace import NarrativeContext, TraceTree, trace_object

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

REPORT_BANNER = "CLARITY ANALYSIS REPORT"
_RULE = "=" * 40

# Notes for sections the launcher prints that are not scenario headers.
EXTRA_WIRING = {
    REPORT_BANNER: (
        "Wiring: the four trees captured above are passed to analyze(), and render() / "
        "render_suite_report() print a report per scenario plus the suite summary. The analysis "
        "reads captured traces — no extra instrumentation, no second run of the code."
    ),
}


# --------------------------------------------------------------------------- #
# Tier 1 — excellent naming                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class DateRange:
    check_in: date
    check_out: date


@dataclass(frozen=True, slots=True)
class Room:
    room_number: str
    category: str
    price_per_night: float


@dataclass(frozen=True, slots=True)
class Reservation:
    reservation_id: str
    guest_id: str
    room_number: str
    check_in_date: date
    check_out_date: date


class AvailabilityChecker:
    def find_available_rooms(self, room_category: str, date_range: DateRange) -> list[Room]:
        return [Room("301", room_category, 189.00), Room("405", room_category, 219.00)]


class PaymentGateway:
    def authorize_payment(self, reservation_id: str, amount: float) -> bool:
        return True


class ReservationService:
    def __init__(self, availability: AvailabilityChecker, payments: PaymentGateway) -> None:
        self._availability = availability
        self._payments = payments

    def confirm_reservation(
        self, guest_id: str, room_category: str, check_in_date: date, check_out_date: date
    ) -> Reservation:
        rooms = self._availability.find_available_rooms(
            room_category, DateRange(check_in_date, check_out_date)
        )
        selected_room = rooms[0]
        reservation_id = f"RES-{uuid.uuid4().hex[:8]}"
        self._payments.authorize_payment(reservation_id, selected_room.price_per_night)
        return Reservation(
            reservation_id, guest_id, selected_room.room_number, check_in_date, check_out_date
        )


# --------------------------------------------------------------------------- #
# Tier 2 — adequate naming                                                    #
# --------------------------------------------------------------------------- #
class BookingManager:
    def handle_booking(self, name: str, category: str, d1: str, d2: str) -> str:
        return f"Booking confirmed for {name} ({category}) {d1} to {d2}"


# --------------------------------------------------------------------------- #
# Tier 3 — poor naming                                                        #
# --------------------------------------------------------------------------- #
class DataProcessor:
    def execute(self, data: str, val: int) -> str:
        return f"processed:{data}:{val}"


# --------------------------------------------------------------------------- #
# Tier 4 — cohesion mismatch                                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Guest:
    guest_id: str
    name: str
    email: str


class GuestRepository:
    def find_guest_by_id(self, guest_id: str) -> Guest:
        return Guest(guest_id, "Jane Smith", "jane@example.com")

    def render_report(self) -> str:
        return "<html><body>Guest Report</body></html>"

    def dispatch_email(self, guest_id: str, message: str) -> bool:
        return True


# --------------------------------------------------------------------------- #
# Scenarios                                                                   #
# --------------------------------------------------------------------------- #
def capture_reservation(context: NarrativeContext) -> TraceTree:
    reservations = trace_object(
        ReservationService(
            trace_object(AvailabilityChecker(), context), trace_object(PaymentGateway(), context)
        ),
        context,
    )
    reservations.confirm_reservation("G-1001", "deluxe", date(2025, 6, 15), date(2025, 6, 18))
    return context.capture_trace()


def capture_booking_manager(context: NarrativeContext) -> TraceTree:
    trace_object(BookingManager(), context).handle_booking(
        "Jane Smith", "suite", "2025-07-01", "2025-07-05"
    )
    return context.capture_trace()


def capture_legacy_processing(context: NarrativeContext) -> TraceTree:
    trace_object(DataProcessor(), context).execute("room-data", 42)
    return context.capture_trace()


def capture_guest_repository(context: NarrativeContext) -> TraceTree:
    guests = trace_object(GuestRepository(), context)
    guests.find_guest_by_id("G-1001")
    guests.render_report()
    guests.dispatch_email("G-1001", "Your reservation is confirmed")
    return context.capture_trace()


_SAME_SETUP = (
    "Wiring: the same trace_object setup after context.reset() — one traced class this time. "
    "Nothing in the configuration changed between scenarios; the names did."
)


def scenarios() -> list[Scenario]:
    """The four naming tiers in tour order."""
    return [
        Scenario(
            "Scenario 1: Guest Books a Room (Excellent Naming)",
            "Wiring: no container, no decorators — trace_object(service, context) around each "
            "collaborator, and the tree is what the analyzer will score. All four scenarios are "
            "wired identically; only the naming quality changes.",
            capture_reservation,
            sections=(TREE,),
        ),
        Scenario(
            "Scenario 2: Booking via Manager (Adequate Naming)",
            _SAME_SETUP,
            capture_booking_manager,
            sections=(TREE,),
        ),
        Scenario(
            "Scenario 3: Legacy Data Processing (Poor Naming)",
            "Wiring: the same trace_object setup again. A tracer can only report what the code "
            "calls itself, so generic names in, generic trace out — no configuration rescues "
            "this one.",
            capture_legacy_processing,
            sections=(TREE,),
        ),
        Scenario(
            "Scenario 4: Guest Repository (Cohesion Mismatch)",
            "Wiring: the same trace_object setup, one repository class. Cohesion is judged "
            "afterwards from the captured tree, so the unrelated calls below are all the analyzer "
            "has to go on.",
            capture_guest_repository,
            sections=(TREE,),
        ),
    ]


REPORT_LABELS = {
    "Scenario 1: Guest Books a Room (Excellent Naming)": "Guest books a room",
    "Scenario 2: Booking via Manager (Adequate Naming)": "Booking via manager",
    "Scenario 3: Legacy Data Processing (Poor Naming)": "Legacy data processing",
    "Scenario 4: Guest Repository (Cohesion Mismatch)": "Guest repository operations",
}


def print_clarity_report(captured: Sequence[tuple[Scenario, TraceTree]], out: TextIO) -> None:
    """Scores every captured tree and prints the per-scenario reports plus the suite summary."""
    out.write(f"\n\n{_RULE}\n         {REPORT_BANNER}\n{_RULE}\n\n")
    results = [(REPORT_LABELS[scenario.title], analyze(tree)) for scenario, tree in captured]
    for label, result in results:
        out.write(f"\n{render(label, result)}\n")
    out.write(f"\n\n{render_suite_report(results)}\n")


def run_example(out: TextIO, *, classic: bool = False) -> None:
    """Walks the four scenarios, then prints the clarity report over all of them."""
    with narrated_run(out, classic=classic) as context:
        print_clarity_report(walk(scenarios(), out, context), out)


def main(argv: Sequence[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)
    run_example(sys.stdout, classic="--classic" in args)


if __name__ == "__main__":
    main()
