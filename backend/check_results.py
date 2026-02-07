#!/usr/bin/env python3
"""Quick script to check extraction accuracy results."""
import json
import urllib.request

DOC_ID = "38e99482-cc40-40a8-ad7a-b307e51147db"

# Fetch extraction result
url = f"http://127.0.0.1:8000/api/results/{DOC_ID}/extraction"
with urllib.request.urlopen(url) as resp:
    data = json.loads(resp.read())

r = data["results"]
acc = r.get("accuracy", {})

print("=== EXTRACTION RESULTS ===")
print(f"Status: {data['status']}")
print(f"Transactions: {r.get('transaction_count')}")
print(f"Batches: {r.get('pages_processed')}")
print()
print("=== ACCURACY SCORE ===")
print(f"Overall: {acc.get('overall_score')}/100 (Grade: {acc.get('grade')})")
print()
bd = acc.get("breakdown", {})
for name, info in bd.items():
    print(f"  {name}: {info['value']}/100 (weight: {info['weight']}%)")
print()
chain = acc.get("balance_chain_detail", {})
print(f"Balance chain: {chain.get('valid')}/{chain.get('total_checked')} valid ({chain.get('chain_accuracy_pct')}%)")
print(f"Chain breaks: {len(chain.get('breaks', []))}")
if chain.get("breaks"):
    for b in chain["breaks"][:5]:
        print(f"  - idx {b['index']}: {b['date']} | {b['description'][:40]} | exp={b['expected_balance']} act={b['actual_balance']} diff={b['difference']}")

# Fetch metrics
url2 = f"http://127.0.0.1:8000/api/metrics/{DOC_ID}"
with urllib.request.urlopen(url2) as resp:
    metrics = json.loads(resp.read())
print()
print("=== KEY METRICS ===")
print(f"Opening: {metrics.get('opening_balance')}")
print(f"Closing: {metrics.get('closing_balance')}")
print(f"Credits: {metrics.get('total_no_of_credit_transactions')} txns, total {metrics.get('total_amount_of_credit_transactions')}")
print(f"Debits: {metrics.get('total_no_of_debit_transactions')} txns, total {metrics.get('total_amount_of_debit_transactions')}")

# Accounting equation check
opening = metrics.get("opening_balance", 0)
closing = metrics.get("closing_balance", 0)
credits_total = metrics.get("total_amount_of_credit_transactions", 0)
debits_total = metrics.get("total_amount_of_debit_transactions", 0)
expected_closing = round(opening + credits_total - debits_total, 2)
diff = round(expected_closing - closing, 2)
print()
print("=== ACCOUNTING EQUATION ===")
print(f"Opening ({opening}) + Credits ({credits_total}) - Debits ({debits_total}) = {expected_closing}")
print(f"Actual closing: {closing}")
print(f"Difference: {diff}")

# Insights check
url3 = f"http://127.0.0.1:8000/api/results/{DOC_ID}/insights"
with urllib.request.urlopen(url3) as resp:
    insights = json.loads(resp.read())
print()
print("=== INSIGHTS AGENT ===")
print(f"Status: {insights['status']}")
print(f"Risk: {insights['risk_level']}")
ir = insights.get("results", {})
narrative = ir.get("narrative", {})
if narrative:
    print(f"\nExecutive Summary: {narrative.get('executive_summary', 'N/A')}")
    print(f"\nRecommendations:")
    for rec in narrative.get("recommendations", []):
        print(f"  • {rec}")
