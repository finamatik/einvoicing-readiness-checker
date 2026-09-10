"""Generate a realistic invoice export (as a typical accounting system would give it) with planted defects,
plus a manifest of what was planted so the checker can be tested against it."""
from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

random.seed(11)
OUT = Path(__file__).resolve().parent.parent / "sample"
OUT.mkdir(exist_ok=True)

CUSTOMERS = [
    ("Al Noor Trading LLC", "AE", "DXB", "100234567800003", "B2B"),
    ("Sharjah Textiles FZE", "AE", "SHJ", "100987654300003", "B2B"),
    ("Gulf Marine Services", "AE", "AUH", "100456789100003", "B2B"),
    ("Ajman Foods Co", "AE", "AJM", "100112233400003", "B2B"),
    ("RAK Ceramics Distribution", "AE", "RAK", "100556677800003", "B2B"),
    ("Fujairah Logistics", "AE", "FUJ", "100998877600003", "B2B"),
    ("Blue Coast Cafe", "AE", "DXB", "", "B2C"),
    ("Nordic Imports AB", "SE", "", "", "B2B"),
    ("Mumbai Spice House", "IN", "", "", "B2B"),
    ("Riyadh Build Co", "SA", "", "", "B2B"),
]
ITEMS = [("Consulting day", 2500), ("Power BI dashboard build", 12000), ("Monthly reporting pack", 3500),
         ("Reconciliation setup", 6500), ("Data migration", 9000), ("Training session", 1800), ("Support hours", 450)]


def money(x):
    return str(Decimal(x).quantize(Decimal("0.01")))


def build():
    invoices, manifest = [], []
    start = date(2026, 6, 1)
    for k in range(60):
        cust = random.choice(CUSTOMERS)
        name, ctry, em, trn, btype = cust
        cur = "AED"
        fx = ""
        if ctry != "AE":
            cur = random.choice(["USD", "EUR", "SAR"])
            fx = {"USD": "3.6725", "EUR": "4.02351", "SAR": "0.979333"}[cur]
        inv = {"invoice_no": f"INV-2026-{1001 + k}", "issue_date": (start + timedelta(days=k + random.randint(0, 3))).isoformat(),
               "currency": cur, "fx_rate": fx, "seller_trn": "100321654900003", "seller_name": "Sample Seller FZE",
               "buyer_name": name, "buyer_trn": trn, "buyer_country": ctry, "buyer_emirate": em, "buyer_type": btype,
               "txn_type_code": "1000", "lines": []}
        nlines = random.randint(1, 4)
        for j in range(nlines):
            desc, price = random.choice(ITEMS)
            qty = random.randint(1, 5)
            cat = "S" if ctry == "AE" else "Z"
            rate = 5 if cat == "S" else 0
            la = Decimal(qty * price)
            va = (la * rate / 100).quantize(Decimal("0.01"))
            ln = {"line_no": j + 1, "description": desc, "qty": qty, "unit_price": money(price), "line_amount": money(la),
                  "vat_category": cat, "vat_rate": rate, "vat_amount": money(va),
                  "line_amount_aed": money(la * Decimal(fx)) if fx else money(la),
                  "vat_amount_aed": money(va * Decimal(fx)) if fx else money(va)}
            inv["lines"].append(ln)
        inv["total_excl_vat"] = money(sum(Decimal(l["line_amount"]) for l in inv["lines"]))
        inv["total_vat"] = money(sum(Decimal(l["vat_amount"]) for l in inv["lines"]))
        inv["total_incl_vat"] = money(Decimal(inv["total_excl_vat"]) + Decimal(inv["total_vat"]))
        invoices.append(inv)

    # ---- planted defects (the things a real export shows)
    def plant(idx, rule, what, mutate):
        mutate(invoices[idx])
        manifest.append({"invoice_no": invoices[idx]["invoice_no"], "rule": rule, "what": what})

    # 1. ISO emirate codes instead of PINT codes on the Dubai and Sharjah customers (the classic one)
    for idx in [i for i, v in enumerate(invoices) if v["buyer_emirate"] == "DXB"][:5]:
        plant(idx, "IBR-128-AE", "emirate stored as ISO AE-DU", lambda v: v.update(buyer_emirate="AE-DU"))
    for idx in [i for i, v in enumerate(invoices) if v["buyer_emirate"] == "SHJ"][:3]:
        plant(idx, "IBR-128-AE", "emirate stored as ISO AE-SH", lambda v: v.update(buyer_emirate="AE-SH"))
    for idx in [i for i, v in enumerate(invoices) if v["buyer_emirate"] == "AUH"][:2]:
        plant(idx, "IBR-128-AE", "emirate stored as a name", lambda v: v.update(buyer_emirate="Abu Dhabi"))
    # 2. FX rate with 8 decimals, and one missing
    fxs = [i for i, v in enumerate(invoices) if v["currency"] != "AED"]
    plant(fxs[0], "IBR-002-AE", "fx rate stored to 8 decimals", lambda v: v.update(fx_rate="4.02351287"))
    plant(fxs[1], "IBR-002-AE", "fx rate missing", lambda v: v.update(fx_rate=""))
    # 3. foreign currency lines without AED amounts
    for idx in fxs[2:5]:
        def m(v):
            for l in v["lines"]:
                l["line_amount_aed"] = ""
                l["vat_amount_aed"] = ""
        plant(idx, "IBR-104-AE", "no AED amounts on foreign currency lines", m)
    # 4. seller TRN 14 digits on a batch (a typo in company settings would hit every invoice; here a subset)
    for idx in range(20, 23):
        plant(idx, "R-04", "seller TRN 14 digits", lambda v: v.update(seller_trn="10032165490003"))
    # 5. UAE B2B buyer with no TRN
    for idx in [i for i, v in enumerate(invoices) if v["buyer_name"] == "Ajman Foods Co"][:2]:
        plant(idx, "R-05", "UAE business buyer without TRN", lambda v: v.update(buyer_trn=""))
    # 6. duplicate invoice number
    plant(30, "R-02", "duplicate invoice number", lambda v: v.update(invoice_no=invoices[29]["invoice_no"]))
    manifest.append({"invoice_no": invoices[29]["invoice_no"], "rule": "R-02", "what": "duplicate invoice number (pair)"})
    # 7. transaction type code missing or wrong shape
    plant(33, "IBR-154-AE", "transaction type code has letters", lambda v: v.update(txn_type_code="STD"))
    plant(34, "R-01", "transaction type code empty", lambda v: v.update(txn_type_code=""))
    # 8. VAT rounded at invoice level, not per line (line VAT off by rounding)
    def m8(v):
        v["lines"][0]["vat_amount"] = money(Decimal(v["lines"][0]["vat_amount"]) + Decimal("0.37"))
    plant(40, "R-10", "VAT not calculated per line", m8)
    # 9. discount netted into unit price without a discount field (qty x price != line amount)
    def m9(v):
        v["lines"][0]["line_amount"] = money(Decimal(v["lines"][0]["line_amount"]) - Decimal("250"))
    plant(41, "R-08", "discount netted silently", m9)
    # 10. header total does not match lines
    plant(45, "R-11", "header total excl VAT differs from lines", lambda v: v.update(total_excl_vat=money(Decimal(v["total_excl_vat"]) + 100)))
    # 11. date in DD/MM/YYYY
    plant(50, "R-03", "date exported as DD/MM/YYYY", lambda v: v.update(issue_date="12/07/2026"))
    # 12. wrong VAT category code from the ERP tax code
    def m12(v):
        v["lines"][0]["vat_category"] = "VAT5"
    plant(52, "R-09", "ERP tax code instead of PINT category", m12)

    # ---- write the export the way a system would: one flat CSV, header fields repeated per line
    hdr = ["invoice_no", "issue_date", "currency", "fx_rate", "seller_trn", "seller_name", "buyer_name", "buyer_trn", "buyer_country",
           "buyer_emirate", "buyer_type", "txn_type_code", "total_excl_vat", "total_vat", "total_incl_vat",
           "line_no", "description", "qty", "unit_price", "line_amount", "vat_category", "vat_rate", "vat_amount", "line_amount_aed", "vat_amount_aed"]
    with open(OUT / "invoice_export.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        for inv in invoices:
            for ln in inv["lines"]:
                row = {k: inv.get(k, "") for k in hdr[:15]}
                row.update({k: ln.get(k, "") for k in hdr[15:]})
                w.writerow(row)
    with open(OUT / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=1)
    print("invoices", len(invoices), "lines", sum(len(i["lines"]) for i in invoices), "planted", len(manifest))


if __name__ == "__main__":
    build()
