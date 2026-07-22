"""
Payment authorization — fixed protocol against a fixed API (project.md §3).

This is a deterministic simulation, not a real payment gateway integration —
appropriate for a reference implementation whose thesis is architectural,
not "how to integrate Stripe." A real deployment would swap this module's
internals for an actual gateway call; the function signature and
deterministic nature of the decision (same inputs -> same outcome) stays
the same either way, which is the property this project's claims depend on.
"""

from __future__ import annotations

import hashlib

from petstore.services.models import PaymentResult

# Deliberately fixed, deterministic decline rule for demo/testing --
# a payment_method value ending in this suffix always declines, so the
# decline path is exercisable without depending on any external state.
_DEMO_DECLINE_SUFFIX = "0000"


def authorize_payment(order_id: str, amount_cents: int, payment_method: str) -> PaymentResult:
    if amount_cents <= 0:
        return PaymentResult(authorized=False, authorization_code=None, reason="Non-positive amount")

    if payment_method.endswith(_DEMO_DECLINE_SUFFIX):
        return PaymentResult(authorized=False, authorization_code=None, reason="Card declined")

    digest = hashlib.sha256(f"{order_id}:{amount_cents}:{payment_method}".encode()).hexdigest()
    return PaymentResult(authorized=True, authorization_code=digest[:12].upper())
