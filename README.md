# E-invoicing readiness checker (UAE, PINT AE)

Runs a flat invoice export from any accounting system against the UAE e-invoicing rules and lists exactly which master data fields to fix before an accredited service provider is appointed. Built and tested on sample data by [Finamatik](https://finamatik.com/work/einvoicing-readiness-checker).

## Rules

Fifteen checks. Where a PINT AE rule exists it is named: IBR-128-AE (emirate subdivision codes AUH DXB SHJ UAQ FUJ AJM RAK, not ISO 3166-2), IBR-104-AE (AED line amount and AED VAT amount on every foreign currency line), IBR-002-AE (exchange rate to a maximum of six decimals), IBR-154-AE (transaction type code, up to eight characters of 0 and 1). Readiness checks R-01 to R-11 cover mandatory header fields, duplicate invoice numbers, ISO dates, seller and buyer TRN format, lines present, mandatory line fields, quantity times price, VAT category and rate consistency, line VAT arithmetic and header totals reconciling to lines.

## Run

```
python3 checker/sample_data.py     # 60 invoices, 146 lines, 29 planted defects, manifest.json
python3 checker/report.py          # out/einvoicing-readiness.xlsx
python3 checker/verify.py          # every planted defect found, no false positives
```

Python 3.11, openpyxl. Input is one CSV with header fields repeated per line (the shape most systems export). Output workbook: readiness percentage, findings by rule with severity and source, every exception with the value as exported and the fix, and a fix list grouped by the master data field that causes it.

## Deadlines the rules are written against

Revenue AED 50m and above: appoint a provider by 30 October 2026, go live 1 January 2027. Below AED 50m: appoint by 31 March 2027, go live 1 July 2027 (Ministerial Decision 244 of 2025 as amended 10 May 2026). Specification: PINT AE v1.0.3.

MIT licence, copyright Finamatik Business Solutions FZE LLC. Questions and production use: info@finamatik.com.
