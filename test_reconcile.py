"""
test_reconcile.py
Verifies all 4 planted gap types are correctly detected.
Run with: python test_reconcile.py
"""

import sys
sys.path.insert(0, ".")

from reconcile import reconcile, totals_check, cast_transactions, cast_settlements

# ---------------------------------------------------------------------------
# Minimal inline datasets (no CSV files needed for unit tests)
# ---------------------------------------------------------------------------

MARCH_TS = "2025-03-15 10:00:00"
APRIL_TS = "2025-04-02"

BASE_TXNS = [
    {"transaction_id": "TXN_NORMAL",    "amount": 1000.00, "currency": "INR",
     "timestamp": MARCH_TS, "customer_id": "C1", "status": "completed", "note": ""},
    {"transaction_id": "TXN_GAP1",      "amount": 3500.00, "currency": "INR",
     "timestamp": "2025-03-30 22:00:00", "customer_id": "C2", "status": "completed", "note": "GAP1"},
    {"transaction_id": "TXN_GAP2",      "amount": 999.995, "currency": "INR",
     "timestamp": MARCH_TS, "customer_id": "C3", "status": "completed", "note": "GAP2"},
    {"transaction_id": "TXN_GAP3",      "amount": 2200.00, "currency": "INR",
     "timestamp": MARCH_TS, "customer_id": "C4", "status": "completed", "note": "GAP3"},
]

BASE_SETS = [
    # Normal — matches TXN_NORMAL exactly
    {"settlement_id": "SET1", "transaction_id": "TXN_NORMAL",
     "settled_amount": 1000.00, "settlement_date": "2025-03-16", "status": "settled", "note": ""},
    # GAP 1 — Settled in April
    {"settlement_id": "SET2", "transaction_id": "TXN_GAP1",
     "settled_amount": 3500.00, "settlement_date": APRIL_TS, "status": "settled", "note": "GAP1"},
    # GAP 2 — Rounding difference
    {"settlement_id": "SET3", "transaction_id": "TXN_GAP2",
     "settled_amount": 1000.00, "settlement_date": "2025-03-16", "status": "settled", "note": "GAP2"},
    # GAP 3 — Duplicate
    {"settlement_id": "SET4A", "transaction_id": "TXN_GAP3",
     "settled_amount": 2200.00, "settlement_date": "2025-03-16", "status": "settled", "note": "GAP3_orig"},
    {"settlement_id": "SET4B", "transaction_id": "TXN_GAP3",
     "settled_amount": 2200.00, "settlement_date": "2025-03-16", "status": "settled", "note": "GAP3_dup"},
    # GAP 4 — Phantom refund
    {"settlement_id": "SET_REF", "transaction_id": "TXN_PHANTOM",
     "settled_amount": -500.00, "settlement_date": "2025-03-20", "status": "refund", "note": "GAP4"},
]

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def check(condition, name):
    result = PASS if condition else FAIL
    print(f"  {result}  {name}")
    return condition


def run_tests():
    print("=" * 60)
    print("  Reconciliation Engine — Unit Tests")
    print("=" * 60)

    txns = cast_transactions(BASE_TXNS)
    sets = cast_settlements(BASE_SETS)
    issues, summary = reconcile(txns, sets)

    gap_types = [i["gap_type"] for i in issues]

    all_passed = True

    print("\n--- GAP TYPE DETECTION ---")

    # Test 1: Next-month settlement detected
    ok = check("NEXT_MONTH_SETTLEMENT" in gap_types,
               "GAP 1: Next-month settlement detected")
    all_passed &= ok

    # Test 2: Rounding difference detected
    ok = check("ROUNDING_DIFFERENCE" in gap_types,
               "GAP 2: Rounding difference detected")
    all_passed &= ok

    # Test 3: Duplicate settlement detected
    ok = check("DUPLICATE_SETTLEMENT" in gap_types,
               "GAP 3: Duplicate settlement detected")
    all_passed &= ok

    # Test 4: Phantom refund detected
    ok = check("PHANTOM_REFUND" in gap_types,
               "GAP 4: Phantom refund detected")
    all_passed &= ok

    print("\n--- ROUNDING DETAILS ---")

    rounding_issues = [i for i in issues if i["gap_type"] == "ROUNDING_DIFFERENCE"]
    if rounding_issues:
        r = rounding_issues[0]
        ok = check(r["txn_amount"] == 999.995 and r["settled_amount"] == 1000.0,
                   "GAP 2: Correct amounts recorded (999.995 vs 1000.00)")
        all_passed &= ok
        ok = check(r["difference"] == round(abs(999.995 - 1000.0), 4),
                   "GAP 2: Difference field is accurate")
        all_passed &= ok

    print("\n--- DUPLICATE DETAILS ---")

    dup_issues = [i for i in issues if i["gap_type"] == "DUPLICATE_SETTLEMENT"]
    if dup_issues:
        d = dup_issues[0]
        ok = check(d["transaction_id"] == "TXN_GAP3",
                   "GAP 3: Correct transaction flagged as duplicate")
        all_passed &= ok
        ok = check(set(d["settlement_ids"]) == {"SET4A", "SET4B"},
                   "GAP 3: Both duplicate settlement IDs captured")
        all_passed &= ok

    print("\n--- NORMAL MATCH ---")

    ok = check(summary["matched"] >= 1,
               "Normal transaction (TXN_NORMAL) counted as matched")
    all_passed &= ok

    print("\n--- TOTALS CHECK ---")

    totals = totals_check(txns, sets)
    ok = check(not totals["match"],
               "Totals do NOT match (gaps exist) — correctly detected")
    all_passed &= ok
    print(f"       Txn total: ₹{totals['march_transaction_total']}")
    print(f"       Set total: ₹{totals['march_settlement_total']}")
    print(f"       Difference: ₹{totals['difference']}")

    print("\n" + "=" * 60)
    if all_passed:
        print("  🎉  ALL TESTS PASSED")
    else:
        print("  ⚠️   SOME TESTS FAILED — check output above")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    passed = run_tests()
    sys.exit(0 if passed else 1)
