"""Shared domain rules: seat layout, pricing and booking references."""

from __future__ import annotations

import random
import string

SEAT_LETTERS = "ABCDEFGHJK"  # 'I' is skipped in real cabin layouts
CLASS_MULTIPLIER = {"Economy": 1.0, "Business": 2.6}
TIER_DISCOUNT = {"Basic": 1.0, "Silver": 0.95, "Gold": 0.90}


def seat_labels(rows: int, seats_per_row: int, business_rows: int = 0) -> list[tuple[str, str]]:
    """Return [(seat, cabin_class), ...] for the whole aircraft, front to back."""
    letters = SEAT_LETTERS[:seats_per_row]
    seats: list[tuple[str, str]] = []
    for row in range(1, rows + 1):
        cabin = "Business" if row <= business_rows else "Economy"
        for letter in letters:
            seats.append((f"{row}{letter}", cabin))
    return seats


def calc_price(base_price: float, cabin_class: str, tier: str = "Basic") -> float:
    price = base_price * CLASS_MULTIPLIER[cabin_class] * TIER_DISCOUNT[tier]
    return round(price, 2)


def gen_booking_ref(rng: random.Random | None = None) -> str:
    source = rng or random
    alphabet = string.ascii_uppercase + string.digits
    return "ZV" + "".join(source.choice(alphabet) for _ in range(6))
