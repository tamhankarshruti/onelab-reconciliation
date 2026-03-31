"""
generate_data.py
Generates synthetic transactions.csv and settlements.csv
with 4 planted gap types for the Onelab reconciliation assessment.
"""

import csv
import random
from datetime import datetime, timedelta

random.seed(42)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rand_id(prefix, n):
    return f"{prefix}{random.randint(10000, 99999)}"

def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def fmt_date(dt):
    return dt.strftime("%Y-%m-%d")

BASE_DATE = datetime(2025, 3, 1, 9, 0, 0)

# ---------------------------------------------------------------------------
# Build transactions (platform side)
# ---------------------------------------------------------------------------

transactions = []
tid_counter = 1000

def make_txn(amount, ts, status="completed", note=""):
    global tid_counter
    tid_counter += 1
    return {
        "transaction_id": f"TXN{tid_counter}",
        "amount": round(amount, 2),
        "currency": "INR",
        "timestamp": fmt(ts),
        "customer_id": f"CUST{random.randint(100,999)}",
        "status": status,
        "note": note,
    }

# 20 normal transactions in March 2025
for i in range(20):
    ts = BASE_DATE + timedelta(hours=i * 7, minutes=random.randint(0, 59))
    txn = make_txn(round(random.uniform(500, 10000), 2), ts)
    transactions.append(txn)

# GAP 1 — Transaction that settles NEXT MONTH (April)
ts_gap1 = BASE_DATE + timedelta(days=28, hours=2)
gap1_txn = make_txn(3500.00, ts_gap1, note="GAP1_NEXT_MONTH")
transactions.append(gap1_txn)

# GAP 2 — Rounding difference (tiny, only visible when summed)
ts_gap2 = BASE_DATE + timedelta(days=5, hours=3)
gap2_txn = make_txn(999.995, ts_gap2, note="GAP2_ROUNDING")
transactions.append(gap2_txn)

# GAP 3 — Will be duplicated on SETTLEMENT side
ts_gap3 = BASE_DATE + timedelta(days=10, hours=1)
gap3_txn = make_txn(2200.00, ts_gap3, note="GAP3_DUPLICATE_IN_SETTLEMENT")
transactions.append(gap3_txn)

# GAP 4 — Normal transaction (the refund will have NO matching txn)
ts_gap4 = BASE_DATE + timedelta(days=15, hours=5)
gap4_txn = make_txn(750.00, ts_gap4, note="GAP4_BASE_FOR_CONTEXT")
transactions.append(gap4_txn)

# ---------------------------------------------------------------------------
# Build settlements (bank side)
# ---------------------------------------------------------------------------

settlements = []
sid_counter = 5000

def make_settlement(txn_id, amount, settle_date, note=""):
    global sid_counter
    sid_counter += 1
    return {
        "settlement_id": f"SET{sid_counter}",
        "transaction_id": txn_id,
        "settled_amount": round(amount, 2),
        "settlement_date": fmt_date(settle_date),
        "status": "settled",
        "note": note,
    }

# Settle the 20 normal transactions 1–2 days after timestamp
for txn in transactions[:20]:
    ts = datetime.strptime(txn["timestamp"], "%Y-%m-%d %H:%M:%S")
    settle_dt = ts + timedelta(days=random.randint(1, 2))
    settlements.append(make_settlement(txn["transaction_id"], txn["amount"], settle_dt))

# GAP 1 — Settled in APRIL (next month)
gap1_settle_dt = datetime(2025, 4, 2, 10, 0, 0)
settlements.append(make_settlement(gap1_txn["transaction_id"], gap1_txn["amount"],
                                   gap1_settle_dt, note="GAP1_NEXT_MONTH"))

# GAP 2 — Rounding: bank rounds differently (999.995 → 1000.00)
ts2 = datetime.strptime(gap2_txn["timestamp"], "%Y-%m-%d %H:%M:%S")
settlements.append(make_settlement(gap2_txn["transaction_id"], 1000.00,
                                   ts2 + timedelta(days=1), note="GAP2_ROUNDING"))

# GAP 3 — DUPLICATE settlement entry for same transaction
ts3 = datetime.strptime(gap3_txn["timestamp"], "%Y-%m-%d %H:%M:%S")
settlements.append(make_settlement(gap3_txn["transaction_id"], gap3_txn["amount"],
                                   ts3 + timedelta(days=1), note="GAP3_ORIGINAL"))
settlements.append(make_settlement(gap3_txn["transaction_id"], gap3_txn["amount"],
                                   ts3 + timedelta(days=1), note="GAP3_DUPLICATE"))

# GAP 4 — REFUND with NO matching original transaction in transactions.csv
settlements.append({
    "settlement_id": "SET_REFUND_99",
    "transaction_id": "TXN_PHANTOM_99",   # does not exist in transactions
    "settled_amount": -500.00,
    "settlement_date": "2025-03-20",
    "status": "refund",
    "note": "GAP4_REFUND_NO_ORIGINAL",
})

# Settle GAP4 base transaction normally
ts4 = datetime.strptime(gap4_txn["timestamp"], "%Y-%m-%d %H:%M:%S")
settlements.append(make_settlement(gap4_txn["transaction_id"], gap4_txn["amount"],
                                   ts4 + timedelta(days=1)))

# ---------------------------------------------------------------------------
# Write CSVs
# ---------------------------------------------------------------------------

TXN_FIELDS  = ["transaction_id", "amount", "currency", "timestamp", "customer_id", "status", "note"]
SET_FIELDS  = ["settlement_id", "transaction_id", "settled_amount", "settlement_date", "status", "note"]

with open("transactions.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=TXN_FIELDS)
    w.writeheader(); w.writerows(transactions)

with open("settlements.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=SET_FIELDS)
    w.writeheader(); w.writerows(settlements)

print("✅  transactions.csv and settlements.csv generated.")
print(f"    Transactions : {len(transactions)}")
print(f"    Settlements  : {len(settlements)}")
print("\nPlanted gaps:")
print("  GAP 1 — Next-month settlement  (TXN settled in April)")
print("  GAP 2 — Rounding difference    (999.995 vs 1000.00)")
print("  GAP 3 — Duplicate settlement   (same TXN settled twice)")
print("  GAP 4 — Refund / phantom TXN   (TXN_PHANTOM_99 has no original)")
