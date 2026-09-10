"""Assert the checker finds every planted defect in sample/manifest.json and raises nothing else on clean invoices."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checker.report import check, load  # noqa: E402

HERE = Path(__file__).resolve().parents[1]
manifest = json.load(open(HERE / "sample/manifest.json"))
invoices = load(HERE / "sample/invoice_export.csv")
findings = check(invoices)
found = {(f["invoice_no"], f["rule"]) for f in findings}
missed = [m for m in manifest if (m["invoice_no"], m["rule"]) not in found]
planted_invoices = {m["invoice_no"] for m in manifest}
extra = sorted({f["invoice_no"] for f in findings} - planted_invoices)
print(f"planted {len(manifest)}, found {len(manifest) - len(missed)}, invoices with findings but nothing planted: {len(extra)}")
for m in missed:
    print("  MISSED", m)
for x in extra:
    print("  EXTRA", x)
sys.exit(0 if not missed and not extra else 1)
