"""UAE e-invoicing (PINT AE) readiness rules, applied to an invoice export from any accounting system.

Deterministic. Each rule returns a list of findings: (invoice_no, line_no or '', rule_id, field, value, message, fix).
Rule ids follow the PINT AE identifiers where one exists; R-xx are Finamatik readiness checks that sit in front of them.

Sources (verified 21 Aug 2026 against docs.peppol.eu PINT AE v1.0.3 and mof.gov.ae MD 244 of 2025):
  IBR-128-AE  country AE: subdivision must be one of AUH DXB SHJ UAQ FUJ AJM RAK (not ISO 3166-2 AE-DU etc.)
  IBR-104-AE  where line VAT information is present, line amount in AED (BTAE-10) and VAT line amount in AED (BTAE-08) per line
  IBR-002-AE  currency exchange rate (BTAE-04) to a maximum of 6 decimal places
  IBR-154-AE  invoice transaction type code (BTAE-02): up to 8 characters, only 0 and 1
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

EMIRATES = {"AUH", "DXB", "SHJ", "UAQ", "FUJ", "AJM", "RAK"}
ISO_TO_PINT = {"AE-AZ": "AUH", "AE-DU": "DXB", "AE-SH": "SHJ", "AE-UQ": "UAQ", "AE-FU": "FUJ", "AE-AJ": "AJM", "AE-RK": "RAK",
               "ABU DHABI": "AUH", "DUBAI": "DXB", "SHARJAH": "SHJ", "UMM AL QUWAIN": "UAQ", "FUJAIRAH": "FUJ", "AJMAN": "AJM", "RAS AL KHAIMAH": "RAK"}
TRN_RE = re.compile(r"^\d{15}$")
TXN_RE = re.compile(r"^[01]{1,8}$")
VAT_CATS = {"S", "Z", "E", "O", "AE"}   # standard, zero, exempt, out of scope, reverse charge
TOL = Decimal("0.05")

REQUIRED_HEADER = ["invoice_no", "issue_date", "currency", "seller_trn", "seller_name", "buyer_name",
                   "buyer_country", "buyer_emirate", "txn_type_code", "total_excl_vat", "total_vat", "total_incl_vat"]
REQUIRED_LINE = ["line_no", "description", "qty", "unit_price", "line_amount", "vat_category", "vat_rate", "vat_amount"]


def dec(v):
    try:
        return Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def decimals(v) -> int:
    s = str(v).strip()
    return len(s.split(".")[1]) if "." in s else 0


def check(invoices: list[dict]) -> list[dict]:
    """invoices: [{header fields..., 'lines': [line dicts]}] -> findings list"""
    f = []

    def add(inv, line, rule, field, value, msg, fix):
        f.append({"invoice_no": inv.get("invoice_no", ""), "line_no": line, "rule": rule, "field": field,
                  "value": "" if value is None else str(value), "message": msg, "fix": fix})

    seen = Counter(str(i.get("invoice_no", "")).strip().upper() for i in invoices)
    for inv in invoices:
        no = str(inv.get("invoice_no", "")).strip()
        # R-01 mandatory header fields
        for k in REQUIRED_HEADER:
            if k == "buyer_emirate" and str(inv.get("buyer_country", "")).strip().upper() != "AE":
                continue
            if str(inv.get(k, "")).strip() == "":
                add(inv, "", "R-01", k, "", "Mandatory header field is empty", "Populate the field in the invoice or customer master before export")
        # R-02 duplicate invoice numbers
        if seen[no.upper()] > 1:
            add(inv, "", "R-02", "invoice_no", no, "Invoice number appears more than once in the export", "Invoice numbers must be unique per seller; fix the numbering sequence")
        # R-03 issue date parseable and not in the future
        d = str(inv.get("issue_date", "")).strip()
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            if dt > datetime(2026, 12, 31):
                add(inv, "", "R-03", "issue_date", d, "Issue date is in the future", "Check the date field mapping")
        except ValueError:
            add(inv, "", "R-03", "issue_date", d, "Issue date is not ISO 8601 (YYYY-MM-DD)", "Export dates as YYYY-MM-DD")
        # R-04 seller TRN format
        trn = str(inv.get("seller_trn", "")).strip()
        if trn and not TRN_RE.match(trn):
            add(inv, "", "R-04", "seller_trn", trn, "Seller TRN is not 15 digits", "Correct the TRN in company settings")
        # R-05 buyer TRN format when present, and required for a UAE business buyer
        btrn = str(inv.get("buyer_trn", "")).strip()
        if btrn and not TRN_RE.match(btrn):
            add(inv, "", "R-05", "buyer_trn", btrn, "Buyer TRN is not 15 digits", "Correct the TRN on the customer master")
        if not btrn and str(inv.get("buyer_country", "")).strip().upper() == "AE" and str(inv.get("buyer_type", "B2B")).upper() == "B2B":
            add(inv, "", "R-05", "buyer_trn", "", "UAE business buyer has no TRN on file", "Collect the TRN and store it on the customer master")
        # IBR-128-AE emirate code
        ctry = str(inv.get("buyer_country", "")).strip().upper()
        em = str(inv.get("buyer_emirate", "")).strip().upper()
        if ctry == "AE" and em and em not in EMIRATES:
            sug = ISO_TO_PINT.get(em, "one of AUH DXB SHJ UAQ FUJ AJM RAK")
            add(inv, "", "IBR-128-AE", "buyer_emirate", em, "Emirate is not a PINT AE subdivision code", f"Map to {sug} in the customer master; ISO 3166-2 codes fail validation")
        # IBR-154-AE transaction type code
        tt = str(inv.get("txn_type_code", "")).strip()
        if tt and not TXN_RE.match(tt):
            add(inv, "", "IBR-154-AE", "txn_type_code", tt, "Transaction type code must be up to 8 characters of 0 and 1", "Set the BTAE-02 flags per invoice (position 2 deemed supply, 3 margin scheme, 4 summary invoice)")
        # IBR-002-AE FX rate decimals and presence on non-AED invoices
        cur = str(inv.get("currency", "AED")).strip().upper()
        fx = inv.get("fx_rate", "")
        if cur != "AED":
            if str(fx).strip() == "":
                add(inv, "", "IBR-002-AE", "fx_rate", "", "Foreign currency invoice has no exchange rate to AED", "Store the AED rate on every non-AED invoice")
            elif decimals(fx) > 6:
                add(inv, "", "IBR-002-AE", "fx_rate", fx, "Exchange rate has more than 6 decimal places", "Round the stored rate to 6 decimals")
        # lines
        lines = inv.get("lines", [])
        if not lines:
            add(inv, "", "R-06", "lines", "", "Invoice has no lines", "Every invoice needs at least one line")
        sum_excl = Decimal(0)
        sum_vat = Decimal(0)
        for ln in lines:
            lno = str(ln.get("line_no", ""))
            for k in REQUIRED_LINE:
                if str(ln.get(k, "")).strip() == "":
                    add(inv, lno, "R-07", k, "", "Mandatory line field is empty", "Populate the field on the item or line")
            la, va = dec(ln.get("line_amount")), dec(ln.get("vat_amount"))
            q, up = dec(ln.get("qty")), dec(ln.get("unit_price"))
            if la is not None:
                sum_excl += la
            if va is not None:
                sum_vat += va
            if q is not None and up is not None and la is not None and abs(q * up - la) > TOL:
                add(inv, lno, "R-08", "line_amount", la, f"qty x unit price ({q * up}) does not equal the line amount", "Check discounts are exported as a separate field, not netted silently")
            vc = str(ln.get("vat_category", "")).strip().upper()
            if vc and vc not in VAT_CATS:
                add(inv, lno, "R-09", "vat_category", vc, "VAT category code is not one of S Z E O AE", "Map the tax code on the item to the PINT category")
            vr = dec(ln.get("vat_rate"))
            if vc == "S" and vr is not None and vr != Decimal(5):
                add(inv, lno, "R-09", "vat_rate", vr, "Standard rated line does not carry 5%", "Check the tax code on the item")
            if vc in {"Z", "E", "O"} and vr not in (None, Decimal(0)):
                add(inv, lno, "R-09", "vat_rate", vr, "Zero, exempt or out of scope line carries a non zero rate", "Check the tax code on the item")
            if la is not None and va is not None and vr is not None and abs(la * vr / 100 - va) > TOL:
                add(inv, lno, "R-10", "vat_amount", va, f"VAT amount does not equal line amount x rate ({(la * vr / 100).quantize(Decimal('0.01'))})", "Recalculate the VAT on the line so line VAT and header VAT agree")
            # IBR-104-AE per line AED amounts on non AED invoices
            if cur != "AED":
                if str(ln.get("line_amount_aed", "")).strip() == "" or str(ln.get("vat_amount_aed", "")).strip() == "":
                    add(inv, lno, "IBR-104-AE", "line_amount_aed / vat_amount_aed", "", "Foreign currency line has no AED amounts", "Store AED line amount and AED VAT amount per line (BTAE-10, BTAE-08)")
        # R-11 totals reconcile to lines
        te, tv, ti = dec(inv.get("total_excl_vat")), dec(inv.get("total_vat")), dec(inv.get("total_incl_vat"))
        if te is not None and lines and abs(te - sum_excl) > TOL:
            add(inv, "", "R-11", "total_excl_vat", te, f"Header total excl. VAT differs from the sum of lines ({sum_excl})", "Export header totals from the same source as the lines")
        if tv is not None and lines and abs(tv - sum_vat) > TOL:
            add(inv, "", "R-11", "total_vat", tv, f"Header VAT differs from the sum of line VAT ({sum_vat})", "Recalculate VAT per line and sum")
        if te is not None and tv is not None and ti is not None and abs(te + tv - ti) > TOL:
            add(inv, "", "R-11", "total_incl_vat", ti, "Total incl. VAT is not excl. VAT plus VAT", "Check the totals mapping")
    return f


RULE_TEXT = {
    "R-01": ("Mandatory header fields present", "Finamatik readiness check"),
    "R-02": ("Invoice numbers unique", "Finamatik readiness check"),
    "R-03": ("Issue date valid ISO 8601", "Finamatik readiness check"),
    "R-04": ("Seller TRN is 15 digits", "FTA TRN format"),
    "R-05": ("Buyer TRN present for UAE business buyers and 15 digits", "FTA TRN format"),
    "IBR-128-AE": ("Emirate is a PINT AE subdivision code (AUH DXB SHJ UAQ FUJ AJM RAK)", "PINT AE v1.0.3, IBR-128-AE"),
    "IBR-154-AE": ("Transaction type code is up to 8 characters of 0 and 1", "PINT AE v1.0.3, IBR-154-AE"),
    "IBR-002-AE": ("Exchange rate present on foreign currency invoices, max 6 decimals", "PINT AE v1.0.3, IBR-002-AE"),
    "R-06": ("Invoice has lines", "Finamatik readiness check"),
    "R-07": ("Mandatory line fields present", "Finamatik readiness check"),
    "R-08": ("Quantity x unit price equals line amount", "Finamatik readiness check"),
    "R-09": ("VAT category and rate consistent", "Finamatik readiness check"),
    "R-10": ("VAT amount equals line amount x rate, per line", "Finamatik readiness check"),
    "IBR-104-AE": ("AED line amount and AED VAT amount on every foreign currency line", "PINT AE v1.0.3, IBR-104-AE"),
    "R-11": ("Header totals reconcile to lines", "Finamatik readiness check"),
}


def summarise(invoices, findings):
    by_rule = Counter(x["rule"] for x in findings)
    by_inv = defaultdict(set)
    for x in findings:
        by_inv[x["invoice_no"]].add(x["rule"])
    n = len(invoices)
    failing = len(by_inv)
    return {
        "invoices": n,
        "lines": sum(len(i.get("lines", [])) for i in invoices),
        "invoices_clean": n - failing,
        "invoices_with_findings": failing,
        "readiness_pct": round(100 * (n - failing) / n, 1) if n else 0,
        "findings": len(findings),
        "by_rule": by_rule,
    }
