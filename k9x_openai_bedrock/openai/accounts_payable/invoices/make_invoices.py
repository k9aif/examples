# SPDX-License-Identifier: Apache-2.0
"""
Builds the demo's invoice PDFs (fictional vendors and amounts, the same as accounts_payable.runtime.INVOICES) from
HTML with headless Chrome, so no PDF library is needed:

    python accounts_payable/invoices/make_invoices.py [path-to-chrome]

The PDFs are committed; upload_invoices.py puts them in object storage, where K9X HIL fetches them for the reviewer.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

BILL_TO = "K9X Demo Co.<br>Accounts Payable<br>100 Example Way<br>Atlanta, GA 30301"

# invoice_id: vendor, address, date, PO, lines [(description, qty, unit)], remit-to note
INVOICES = {
    "INV-1043": ("Acme Supplies", "12 Industrial Park Rd<br>Columbus, OH 43004", "2026-11-03", "PO-7781",
                 [("Copy paper, A4, case of 10 reams", 6, 52.00), ("Toner cartridge, black", 4, 81.00),
                  ("Desk organisers", 12, 22.00)], "Bank account on file (ending 2210)"),
    "INV-1042": ("Acme Supplies", "12 Industrial Park Rd<br>Columbus, OH 43004", "2026-11-05", "PO-7790",
                 [("Pallet racking bay, 3 m, heavy duty", 20, 1850.00), ("Wire mesh decking", 60, 95.00),
                  ("Installation, 2 crew days", 2, 2900.00)], "Bank account on file (ending 2210)"),
    "INV-2001": ("Globex Logistics", "88 Harbor Blvd<br>Savannah, GA 31401", "2026-11-01", "PO-6620",
                 [("Freight, Savannah to Atlanta, October", 1, 5400.00), ("Fuel surcharge", 1, 520.00),
                  ("Liftgate delivery", 4, 70.00)],
                 "<b>NEW remit-to account, changed 2026-10-28 (ending 9934).</b> Please update your records."),
    "INV-4001": ("Umbrella Corp", "1 Raccoon Plaza<br>Springfield, MO 65801", "2026-11-04", "PO-7801",
                 [("Lab consumables, assorted", 1, 1250.00)], "Bank account on file (ending 5502)"),
}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
  @page {{ size: Letter; margin: 18mm; }}
  body {{ font: 11pt Helvetica, Arial, sans-serif; color: #1f2937; }}
  .top {{ display: flex; justify-content: space-between; align-items: flex-start; }}
  h1 {{ font-size: 26pt; margin: 0; color: #111827; letter-spacing: 1px; }}
  .vendor b {{ font-size: 14pt; }}
  .meta td {{ padding: 2px 0 2px 14px; }}
  .meta td:first-child {{ color: #6b7280; padding-left: 0; }}
  .blocks {{ display: flex; gap: 40px; margin: 28px 0; }}
  .label {{ color: #6b7280; font-size: 9pt; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
  table.lines {{ width: 100%; border-collapse: collapse; }}
  table.lines th {{ text-align: left; border-bottom: 2px solid #111827; padding: 6px 4px; font-size: 9.5pt; }}
  table.lines td {{ border-bottom: 1px solid #e5e7eb; padding: 7px 4px; }}
  .num {{ text-align: right; }}
  .total td {{ border: 0; font-weight: bold; font-size: 13pt; padding-top: 12px; }}
  .remit {{ margin-top: 28px; padding: 10px 12px; background: #f3f4f6; border-radius: 6px; font-size: 10pt; }}
  .foot {{ margin-top: 40px; color: #9ca3af; font-size: 8.5pt; }}
</style></head><body>
<div class="top">
  <div class="vendor"><b>{vendor}</b><br>{address}</div>
  <div><h1>INVOICE</h1>
    <table class="meta"><tr><td>Invoice</td><td><b>{invoice_id}</b></td></tr><tr><td>Date</td><td>{date}</td></tr>
    <tr><td>PO</td><td>{po}</td></tr><tr><td>Terms</td><td>Net 30</td></tr></table></div>
</div>
<div class="blocks"><div><div class="label">Bill to</div>{bill_to}</div></div>
<table class="lines"><tr><th>Description</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Amount</th></tr>
{rows}
<tr class="total"><td colspan="3" class="num">Total due (USD)</td><td class="num">${total:,.2f}</td></tr></table>
<div class="remit"><div class="label">Remit to</div>{remit}</div>
<div class="foot">Demo document for openai.k9x.ai (K9-AIF, K9X HIL). Fictional vendor; not a real invoice.</div>
</body></html>"""


def build(chrome: str = CHROME) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for invoice_id, (vendor, address, date, po, lines, remit) in INVOICES.items():
            rows = "\n".join(f"<tr><td>{d}</td><td class='num'>{q}</td><td class='num'>${u:,.2f}</td>"
                             f"<td class='num'>${q * u:,.2f}</td></tr>" for d, q, u in lines)
            total = sum(q * u for _, q, u in lines)
            html = Path(tmp) / f"{invoice_id}.html"
            html.write_text(PAGE.format(vendor=vendor, address=address, invoice_id=invoice_id, date=date, po=po,
                                        bill_to=BILL_TO, rows=rows, total=total, remit=remit), encoding="utf-8")
            out = HERE / f"{invoice_id}.pdf"
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={out}", html.as_uri()], check=True, capture_output=True)
            print(f"{out.name}: {vendor}, ${total:,.2f}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else CHROME)
