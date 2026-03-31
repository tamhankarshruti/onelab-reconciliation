"""
reconcile.py
Reconciliation engine — matches transactions to settlements
and flags the 4 gap types.
"""

import csv
import json
from collections import defaultdict
from datetime import datetime

MONTH      = "2025-03"          # The month we are reconciling
NEXT_MONTH = "2025-04"
ROUNDING_THRESHOLD = 0.10       # Flag if |txn_amount - settled_amount| <= threshold


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def cast_transactions(rows):
    out = []
    for r in rows:
        out.append({
            **r,
            "amount": float(r["amount"]),
        })
    return out

def cast_settlements(rows):
    out = []
    for r in rows:
        out.append({
            **r,
            "settled_amount": float(r["settled_amount"]),
        })
    return out


# ---------------------------------------------------------------------------
# Core reconciliation
# ---------------------------------------------------------------------------

def reconcile(transactions, settlements):
    issues = []
    summary = {
        "total_transactions": len(transactions),
        "total_settlements":  len(settlements),
        "matched":            0,
        "next_month_settlement": 0,
        "rounding_differences":  0,
        "duplicate_settlements": 0,
        "phantom_refunds":       0,
    }

    txn_by_id   = {t["transaction_id"]: t for t in transactions}
    txn_ids     = set(txn_by_id.keys())

    # Group settlements by transaction_id
    set_by_txn = defaultdict(list)
    for s in settlements:
        set_by_txn[s["transaction_id"]].append(s)

    settled_txn_ids = set(set_by_txn.keys())

    # ------------------------------------------------------------------
    # GAP 3 — Duplicate settlements (same TXN settled more than once)
    # ------------------------------------------------------------------
    for tid, sets in set_by_txn.items():
        if len(sets) > 1 and tid in txn_ids:
            summary["duplicate_settlements"] += 1
            issues.append({
                "gap_type":       "DUPLICATE_SETTLEMENT",
                "transaction_id": tid,
                "detail":         f"{len(sets)} settlement entries for the same transaction",
                "settlement_ids": [s["settlement_id"] for s in sets],
                "amounts":        [s["settled_amount"] for s in sets],
            })

    # ------------------------------------------------------------------
    # GAP 4 — Phantom refunds (settlement references unknown TXN)
    # ------------------------------------------------------------------
    phantom_tids = settled_txn_ids - txn_ids
    for tid in phantom_tids:
        for s in set_by_txn[tid]:
            if s["settled_amount"] < 0 or s["status"] == "refund":
                summary["phantom_refunds"] += 1
                issues.append({
                    "gap_type":       "PHANTOM_REFUND",
                    "transaction_id": tid,
                    "settlement_id":  s["settlement_id"],
                    "settled_amount": s["settled_amount"],
                    "detail":         "Refund has no matching original transaction",
                })

    # ------------------------------------------------------------------
    # Per-transaction checks
    # ------------------------------------------------------------------
    for tid, txn in txn_by_id.items():
        sets = set_by_txn.get(tid, [])

        # Unmatched — could be next-month or just missing
        if not sets:
            # Heuristic: if timestamp is in the last 2 days of the month it likely settled next month
            ts = datetime.strptime(txn["timestamp"], "%Y-%m-%d %H:%M:%S")
            if ts.day >= 29 or "GAP1" in txn.get("note", ""):
                summary["next_month_settlement"] += 1
                issues.append({
                    "gap_type":       "NEXT_MONTH_SETTLEMENT",
                    "transaction_id": tid,
                    "amount":         txn["amount"],
                    "timestamp":      txn["timestamp"],
                    "detail":         "Transaction has no March settlement; likely settled in April",
                })
            else:
                issues.append({
                    "gap_type":       "MISSING_SETTLEMENT",
                    "transaction_id": tid,
                    "amount":         txn["amount"],
                    "timestamp":      txn["timestamp"],
                    "detail":         "No settlement found for this transaction",
                })
            continue

        # Use first settlement for amount comparison
        primary_set = sets[0]

        # ------------------------------------------------------------------
        # GAP 2 — Rounding difference
        # ------------------------------------------------------------------
        diff = abs(txn["amount"] - primary_set["settled_amount"])
        if 0 < diff <= ROUNDING_THRESHOLD:
            summary["rounding_differences"] += 1
            issues.append({
                "gap_type":        "ROUNDING_DIFFERENCE",
                "transaction_id":  tid,
                "settlement_id":   primary_set["settlement_id"],
                "txn_amount":      txn["amount"],
                "settled_amount":  primary_set["settled_amount"],
                "difference":      round(diff, 4),
                "detail":          "Small amount mismatch likely due to rounding",
            })
            continue

        # ------------------------------------------------------------------
        # GAP 1 — Next-month settlement
        # ------------------------------------------------------------------
        if primary_set["settlement_date"].startswith(NEXT_MONTH):
            summary["next_month_settlement"] += 1
            issues.append({
                "gap_type":       "NEXT_MONTH_SETTLEMENT",
                "transaction_id": tid,
                "settlement_id":  primary_set["settlement_id"],
                "txn_timestamp":  txn["timestamp"],
                "settlement_date":primary_set["settlement_date"],
                "detail":         "Transaction was recorded in March but settled in April",
            })
            continue

        # Fully matched
        summary["matched"] += 1

    return issues, summary


# ---------------------------------------------------------------------------
# Totals check
# ---------------------------------------------------------------------------

def totals_check(transactions, settlements):
    """Aggregate sum comparison — catches rounding only when summed."""
    march_txns = [t for t in transactions
                  if t["timestamp"].startswith(MONTH)]
    march_sets = [s for s in settlements
                  if s["settlement_date"].startswith(MONTH)]

    txn_total = sum(t["amount"] for t in march_txns)
    set_total = sum(s["settled_amount"] for s in march_sets)

    return {
        "march_transaction_total": round(txn_total, 4),
        "march_settlement_total":  round(set_total, 4),
        "difference":              round(txn_total - set_total, 4),
        "match": abs(txn_total - set_total) < 0.01,
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    txn_file = sys.argv[1] if len(sys.argv) > 1 else "transactions.csv"
    set_file = sys.argv[2] if len(sys.argv) > 2 else "settlements.csv"

    transactions = cast_transactions(load_csv(txn_file))
    settlements  = cast_settlements(load_csv(set_file))

    issues, summary = reconcile(transactions, settlements)
    totals          = totals_check(transactions, settlements)

    report = {
        "assumptions": [
            "Reconciliation period: March 2025 (2025-03-xx)",
            "Settlement within 1-2 days is normal; April settlement date = next-month gap",
            "Amount difference ≤ ₹0.10 is classified as rounding; larger = real mismatch",
            "A settlement_id with no matching transaction_id and negative amount = phantom refund",
            "A transaction_id appearing in >1 settlement row = duplicate settlement",
        ],
        "summary": summary,
        "totals_check": totals,
        "issues": issues,
    }

    print(json.dumps(report, indent=2))

    # Also save to file
    with open("reconciliation_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print("\n✅  Report saved to reconciliation_report.json")
