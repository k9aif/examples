# SPDX-License-Identifier: Apache-2.0
"""
The accounts payable tools. The vendor and invoice records are fixed demo data (K9X Streams is off for this demo;
with it on, these facts would be live and carry their source and age). pay_invoice is simulated: nothing is paid.

The facts the rules decide on (vendor status, a changed bank account, a matching PO, a duplicate) come from the
records (record_facts, called by the rules step), never from the model: the model only reads the invoice.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from k9_aif_abb.k9_adapters.tool_capability import ToolCapability

VENDORS: Dict[str, Dict[str, Any]] = {
    "acme supplies": {"vendor": "Acme Supplies", "vendor_status": "approved", "bank_changed": False},
    "globex logistics": {"vendor": "Globex Logistics", "vendor_status": "approved", "bank_changed": True},
    "initech": {"vendor": "Initech", "vendor_status": "new", "bank_changed": False},
    "umbrella corp": {"vendor": "Umbrella Corp", "vendor_status": "blocked", "bank_changed": False},
}
PAID_INVOICES = {"INV-0999"}                                   # already paid: a resubmission is a duplicate
PO_MATCHED = {"INV-1042", "INV-1043", "INV-2001", "INV-3001", "INV-4001", "INV-0999",
              "INV-6001", "INV-6002", "INV-6003", "INV-6004", "INV-6005", "INV-6006", "INV-6007", "INV-6009",
              "INV-6010", "INV-5009"}                         # the batch's invoices (and INV-5009) have purchase orders


def _vendor(name: str) -> Dict[str, Any]:
    key = (name or "").strip().lower()
    for known, record in VENDORS.items():
        if known in key or key in known:
            return record
    return {"vendor": name, "vendor_status": "new", "bank_changed": False}


def record_facts(vendor: str, invoice_id: str, amount: Any) -> Dict[str, Any]:
    """The facts the rules decide on, from the records (deterministic): the model only read vendor, invoice and amount."""
    invoice_id = str(invoice_id or "").strip().upper()
    record = _vendor(str(vendor or ""))
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
    return {"vendor": record["vendor"], "invoice_id": invoice_id, "amount": amount,
            "vendor_status": record["vendor_status"], "bank_changed": record["bank_changed"],
            "duplicate": invoice_id in PAID_INVOICES, "po_matched": invoice_id in PO_MATCHED}


async def pay_invoice(args: Dict[str, Any]) -> Dict[str, Any]:
    ref = "PAY-" + hashlib.sha256(f"{args.get('invoice_id')}|{args.get('amount')}".encode()).hexdigest()[:8].upper()
    return {"status": "paid (simulated)", "payment_ref": ref, "vendor": args.get("vendor"),
            "invoice_id": args.get("invoice_id"), "amount": args.get("amount")}


CAPABILITIES = [
    ToolCapability(
        name="pay_invoice", description="Pay an invoice (simulated). Returns the payment reference.",
        input_schema={"type": "object", "properties": {"vendor": {"type": "string"}, "invoice_id": {"type": "string"},
                                                        "amount": {"type": "number"}},
                      "required": ["vendor", "invoice_id", "amount"], "additionalProperties": False},
        handler=pay_invoice),
]
