# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Library tour: a small book-lending domain traced through plain dataclasses.

Demonstrates the *value* side of tracing: frozen dataclasses
that render themselves into the trace through ``@narrative_summary`` (``Book`` reads as
"The Pragmatic Programmer by David Thomas & Andrew Hunt", not as a field dump), ``@narrated`` on
the use case, ``@on_error`` on the lookup, and ``@not_traced`` keeping the member's card number
out of the story. Two scenarios: a successful borrow, and a book that is not available. Run it::

    python -m examples.library
    python -m examples.demo --example library
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, ClassVar

from examples.tour import MERMAID, PLANTUML, PROSE, TREE, Scenario, narrated_run, walk
from narrativetrace import (
    NarrativeContext,
    TraceTree,
    narrated,
    narrative_summary,
    not_traced,
    on_error,
    trace_object,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TextIO


# --------------------------------------------------------------------------- #
# Model — values that tell their own story                                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Book:
    isbn: str
    title: str
    author: str
    available: bool

    @narrative_summary
    def summary(self) -> str:
        return f"{self.title} by {self.author}"


@dataclass(frozen=True, slots=True)
class Member:
    id: str
    name: str
    card_number: str

    @narrative_summary
    def summary(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class LoanReceipt:
    book_title: str
    member_name: str
    due_date: date

    @narrative_summary
    def summary(self) -> str:
        return f"{self.book_title} loaned to {self.member_name}, due {self.due_date}"


class BookNotFoundError(LookupError):
    """No book carries that ISBN."""


class BookUnavailableError(RuntimeError):
    """The book exists but is out on loan."""


# --------------------------------------------------------------------------- #
# Services                                                                    #
# --------------------------------------------------------------------------- #
class CatalogService:
    _books: ClassVar[dict[str, Book]] = {
        "978-0-13-468599-1": Book(
            "978-0-13-468599-1", "The Pragmatic Programmer", "David Thomas & Andrew Hunt", True
        ),
        "978-0-201-63361-0": Book("978-0-201-63361-0", "Design Patterns", "Gang of Four", True),
        "978-0-13-235088-4": Book("978-0-13-235088-4", "Clean Code", "Robert C. Martin", False),
    }

    @on_error(BookNotFoundError, "Book {isbn} not found in catalog")
    def find_book(self, isbn: str) -> Book:
        try:
            return self._books[isbn]
        except KeyError:
            raise BookNotFoundError(f"Book not found: {isbn}") from None


class MemberService:
    _members: ClassVar[dict[str, Member]] = {
        "M-001": Member("M-001", "Alice", "4111-XXXX-XXXX-1234"),
        "M-002": Member("M-002", "Bob", "5500-XXXX-XXXX-5678"),
    }

    @not_traced("card_number")
    def lookup_member(self, member_id: str, card_number: str) -> Member:
        try:
            return self._members[member_id]
        except KeyError:
            raise LookupError(f"Member not found: {member_id}") from None


class LendingService:
    def __init__(
        self,
        catalog: CatalogService,
        members: MemberService,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._catalog = catalog
        self._members = members
        self._today = today

    @narrated("Borrowing book {isbn} for member {member_id}")
    def borrow_book(self, member_id: str, isbn: str) -> LoanReceipt:
        book = self._catalog.find_book(isbn)
        if not book.available:
            raise BookUnavailableError(f"Book not available: {isbn}")
        member = self._members.lookup_member(member_id, "CARD-VERIFY")
        return LoanReceipt(book.title, member.name, self._today() + timedelta(weeks=2))


def build_lending(
    context: NarrativeContext, today: Callable[[], date] = date.today
) -> LendingService:
    """Wires the three services, each wrapped once with ``trace_object``."""
    catalog = trace_object(CatalogService(), context)
    members = trace_object(MemberService(), context)
    return trace_object(LendingService(catalog, members, today), context)


# --------------------------------------------------------------------------- #
# Scenarios                                                                   #
# --------------------------------------------------------------------------- #
def capture_successful_borrow(context: NarrativeContext) -> TraceTree:
    build_lending(context).borrow_book("M-001", "978-0-13-468599-1")
    return context.capture_trace()


def capture_book_unavailable(context: NarrativeContext) -> TraceTree:
    try:
        build_lending(context).borrow_book("M-001", "978-0-13-235088-4")
    except BookUnavailableError:
        pass  # expected
    return context.capture_trace()


def scenarios() -> list[Scenario]:
    """The two scenarios in tour order."""
    return [
        Scenario(
            "Scenario 1: Successful Book Borrow",
            "Wiring: no container — trace_object(...) around CatalogService, MemberService and "
            "LendingService. @narrated on LendingService.borrow_book supplies the // line; "
            "card_number prints as [REDACTED] from @not_traced on MemberService.lookup_member; "
            "Book, Member and LoanReceipt render through their @narrative_summary method.",
            capture_successful_borrow,
            sections=(TREE, PROSE, MERMAID, PLANTUML),
        ),
        Scenario(
            "Scenario 2: Book Unavailable",
            "Wiring: the same three wrappers after context.reset(). BookUnavailableError is "
            "raised by LendingService itself and the wrapper records it on the way out — there "
            "is no error-handling code in this path, and nothing to keep in sync when it changes.",
            capture_book_unavailable,
            sections=(TREE, PROSE),
        ),
    ]


def run_example(out: TextIO, *, classic: bool = False) -> None:
    """Walks both scenarios, printing the sections to ``out``."""
    with narrated_run(out, classic=classic) as context:
        walk(scenarios(), out, context)


def main(argv: Sequence[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)
    run_example(sys.stdout, classic="--classic" in args)


if __name__ == "__main__":
    main()
