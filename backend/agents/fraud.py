"""
Fraud Detection Agent — Step 6.

Analyses extracted transactions for fraud signals using rule-based checks
plus an LLM-powered narrative assessment.

Checks:
  1. Round-Amount Transactions    — large round-number amounts (structuring)
  2. Duplicate / Near-Duplicate   — same amount + date + counterparty
  3. Rapid Succession             — many transactions in same day
  4. Large Outlier Transactions   — amounts > 3 std-dev above mean
  5. Balance Anomalies            — sudden large swings in running balance
  6. Cash-Heavy Activity          — disproportionate cash deposits / withdrawals
  7. Unusual Timing Patterns      — concentration at start/end of month
  8. Counterparty Risk            — LLM assessment of counterparty names
"""

from __future__ import annotations

import json
import logging
import math
import re
import statistics
from collections import Counter, defaultdict
from typing import List, Optional

from sqlalchemy.orm import Session

from agents.base import BaseAgent
from models import Document, RawTransaction, StatementMetrics
from services.llm_client import chat_completion

logger = logging.getLogger("ThirdEye.Agent.Fraud")

# ─── Thresholds ───────────────────────────────────────────────────────────────

ROUND_AMOUNT_THRESHOLD = 5_000       # flag round amounts ≥ this
ROUND_MODULO = 1_000                 # "round" = divisible by this
DUPLICATE_WINDOW_DAYS = 1            # same day = potential duplicate
RAPID_TXN_THRESHOLD = 10            # ≥ N txns in one day = flag
OUTLIER_STD_DEVS = 3.0              # amounts > mean + 3σ
BALANCE_SWING_RATIO = 0.5           # balance changes > 50% of max balance
CASH_RATIO_THRESHOLD = 0.30          # cash > 30% of total = flag
MONTH_EDGE_DAYS = {1, 2, 3, 28, 29, 30, 31}  # start / end of month


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_day(date_str: str) -> Optional[int]:
    """Extract day-of-month from various date formats."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # DD-MMM-YYYY or DD/MMM
    m = re.match(r"(\d{1,2})[\-/]", date_str)
    if m:
        return int(m.group(1))
    # DD MMM
    parts = date_str.split()
    if parts and parts[0].isdigit():
        return int(parts[0])
    return None


def _date_key(date_str: str) -> str:
    """Normalise a date string to a sortable key for grouping by day."""
    if not date_str:
        return ""
    return re.sub(r"\s+", " ", date_str.strip().upper())


# ─── Individual Fraud Checks ─────────────────────────────────────────────────

def check_round_amounts(txns: List[RawTransaction]) -> dict:
    """Check 1: Flag large round-number transactions (structuring signal)."""
    name = "Round-Amount Transactions"
    flagged = []
    for t in txns:
        amt = t.amount or 0
        if amt >= ROUND_AMOUNT_THRESHOLD and amt % ROUND_MODULO == 0:
            flagged.append({
                "date": t.date,
                "amount": amt,
                "type": t.transaction_type,
                "description": (t.description or "")[:80],
            })

    if not flagged:
        return {"check": name, "status": "pass",
                "details": f"No round amounts ≥ {ROUND_AMOUNT_THRESHOLD:,} found.",
                "flagged_items": []}

    return {"check": name, "status": "fail" if len(flagged) >= 5 else "warning",
            "details": f"{len(flagged)} transactions with round amounts ≥ "
                       f"{ROUND_AMOUNT_THRESHOLD:,} (divisible by {ROUND_MODULO:,}).",
            "flagged_items": flagged[:20]}


def check_duplicates(txns: List[RawTransaction]) -> dict:
    """Check 2: Flag potential duplicate transactions (same date+amount+counterparty)."""
    name = "Duplicate / Near-Duplicate Transactions"
    seen: dict[str, list] = defaultdict(list)

    for t in txns:
        key = f"{_date_key(t.date)}|{t.amount or 0:.2f}|{(t.counterparty or '').upper()[:30]}"
        seen[key].append(t)

    dupes = []
    for key, group in seen.items():
        if len(group) >= 2:
            dupes.append({
                "count": len(group),
                "date": group[0].date,
                "amount": group[0].amount,
                "counterparty": group[0].counterparty or "",
                "description": (group[0].description or "")[:80],
            })

    if not dupes:
        return {"check": name, "status": "pass",
                "details": "No duplicate transactions detected.",
                "flagged_items": []}

    total_dupe_txns = sum(d["count"] for d in dupes)
    return {"check": name, "status": "fail" if total_dupe_txns >= 6 else "warning",
            "details": f"{len(dupes)} groups of duplicate transactions "
                       f"({total_dupe_txns} total transactions).",
            "flagged_items": dupes[:20]}


def check_rapid_succession(txns: List[RawTransaction]) -> dict:
    """Check 3: Flag days with unusually high transaction counts."""
    name = "Rapid Succession Transactions"
    by_day: dict[str, int] = Counter()
    for t in txns:
        dk = _date_key(t.date)
        if dk:
            by_day[dk] += 1

    busy_days = [(day, cnt) for day, cnt in by_day.items() if cnt >= RAPID_TXN_THRESHOLD]
    busy_days.sort(key=lambda x: x[1], reverse=True)

    if not busy_days:
        return {"check": name, "status": "pass",
                "details": f"No days with ≥ {RAPID_TXN_THRESHOLD} transactions.",
                "flagged_items": []}

    items = [{"date": d, "count": c} for d, c in busy_days[:10]]
    return {"check": name, "status": "warning",
            "details": f"{len(busy_days)} days with ≥ {RAPID_TXN_THRESHOLD} "
                       f"transactions (max {busy_days[0][1]} on {busy_days[0][0]}).",
            "flagged_items": items}


def check_large_outliers(txns: List[RawTransaction]) -> dict:
    """Check 4: Flag amounts > mean + 3σ (statistical outliers)."""
    name = "Large Outlier Transactions"
    amounts = [t.amount for t in txns if t.amount and t.amount > 0]

    if len(amounts) < 5:
        return {"check": name, "status": "pass",
                "details": "Too few transactions for outlier analysis.",
                "flagged_items": []}

    mean = statistics.mean(amounts)
    stdev = statistics.stdev(amounts)
    threshold = mean + OUTLIER_STD_DEVS * stdev

    flagged = []
    for t in txns:
        if (t.amount or 0) > threshold:
            flagged.append({
                "date": t.date,
                "amount": t.amount,
                "type": t.transaction_type,
                "description": (t.description or "")[:80],
                "std_devs": round((t.amount - mean) / stdev, 1) if stdev > 0 else 0,
            })

    flagged.sort(key=lambda x: x["amount"], reverse=True)

    if not flagged:
        return {"check": name, "status": "pass",
                "details": f"No outliers (threshold: {threshold:,.2f}, "
                           f"mean: {mean:,.2f}, σ: {stdev:,.2f}).",
                "flagged_items": []}

    return {"check": name, "status": "fail" if len(flagged) >= 3 else "warning",
            "details": f"{len(flagged)} transactions exceed {OUTLIER_STD_DEVS}σ above mean "
                       f"(threshold: {threshold:,.2f}).",
            "flagged_items": flagged[:15]}


def check_balance_anomalies(txns: List[RawTransaction]) -> dict:
    """Check 5: Flag large sudden balance swings."""
    name = "Balance Anomalies"
    balances = [(t.date, t.balance) for t in txns if t.balance is not None]

    if len(balances) < 3:
        return {"check": name, "status": "pass",
                "details": "Too few balance data points for analysis.",
                "flagged_items": []}

    bal_values = [b for _, b in balances]
    max_bal = max(abs(b) for b in bal_values) if bal_values else 1
    if max_bal == 0:
        max_bal = 1

    flagged = []
    for i in range(1, len(balances)):
        prev_bal = balances[i - 1][1]
        curr_bal = balances[i][1]
        swing = abs(curr_bal - prev_bal)
        if swing > BALANCE_SWING_RATIO * max_bal and swing > 10_000:
            flagged.append({
                "date": balances[i][0],
                "previous_balance": round(prev_bal, 2),
                "new_balance": round(curr_bal, 2),
                "swing": round(swing, 2),
                "swing_pct": round(swing / max_bal * 100, 1),
            })

    if not flagged:
        return {"check": name, "status": "pass",
                "details": "No large balance swings detected.",
                "flagged_items": []}

    return {"check": name, "status": "fail" if len(flagged) >= 3 else "warning",
            "details": f"{len(flagged)} large balance swings (> {BALANCE_SWING_RATIO*100:.0f}% "
                       f"of max balance {max_bal:,.2f}).",
            "flagged_items": flagged[:15]}


def check_cash_heavy(txns: List[RawTransaction], metrics: Optional[StatementMetrics]) -> dict:
    """Check 6: Flag disproportionate cash activity."""
    name = "Cash-Heavy Activity"
    total_credits = sum((t.amount or 0) for t in txns if t.transaction_type == "credit")
    total_debits = sum((t.amount or 0) for t in txns if t.transaction_type == "debit")
    total_volume = total_credits + total_debits

    cash_deposits = 0.0
    cash_withdrawals = 0.0
    cash_count = 0

    if metrics:
        cash_deposits = metrics.total_amount_of_cash_deposits or 0
        cash_withdrawals = metrics.total_amount_of_cash_withdrawals or 0
        cash_count = (metrics.total_no_of_cash_deposits or 0) + (metrics.total_no_of_cash_withdrawals or 0)
    else:
        for t in txns:
            if t.is_cash:
                cash_count += 1
                if t.transaction_type == "credit":
                    cash_deposits += t.amount or 0
                else:
                    cash_withdrawals += t.amount or 0

    cash_total = cash_deposits + cash_withdrawals
    ratio = cash_total / total_volume if total_volume > 0 else 0

    if ratio < CASH_RATIO_THRESHOLD:
        return {"check": name, "status": "pass",
                "details": f"Cash activity: {ratio*100:.1f}% of total volume "
                           f"({cash_count} cash transactions, "
                           f"deposits: {cash_deposits:,.2f}, withdrawals: {cash_withdrawals:,.2f}).",
                "flagged_items": []}

    return {"check": name, "status": "fail" if ratio > 0.5 else "warning",
            "details": f"Cash activity: {ratio*100:.1f}% of total volume "
                       f"(threshold: {CASH_RATIO_THRESHOLD*100:.0f}%). "
                       f"{cash_count} cash transactions, "
                       f"deposits: {cash_deposits:,.2f}, withdrawals: {cash_withdrawals:,.2f}.",
            "flagged_items": [{"cash_ratio": round(ratio, 3),
                               "cash_deposits": cash_deposits,
                               "cash_withdrawals": cash_withdrawals,
                               "cash_count": cash_count}]}


def check_timing_patterns(txns: List[RawTransaction]) -> dict:
    """Check 7: Flag unusual concentration at month edges."""
    name = "Unusual Timing Patterns"
    edge_count = 0
    mid_count = 0

    for t in txns:
        day = _parse_day(t.date)
        if day is None:
            continue
        if day in MONTH_EDGE_DAYS:
            edge_count += 1
        else:
            mid_count += 1

    total = edge_count + mid_count
    if total < 10:
        return {"check": name, "status": "pass",
                "details": "Too few dated transactions for timing analysis.",
                "flagged_items": []}

    edge_ratio = edge_count / total
    # With 7 edge days out of ~30, expected ratio ≈ 23%.  Flag if > 60%.
    if edge_ratio <= 0.60:
        return {"check": name, "status": "pass",
                "details": f"{edge_count}/{total} ({edge_ratio*100:.0f}%) transactions "
                           f"at month start/end — within normal range.",
                "flagged_items": []}

    return {"check": name, "status": "warning",
            "details": f"{edge_count}/{total} ({edge_ratio*100:.0f}%) transactions "
                       f"concentrated at month start/end (days {sorted(MONTH_EDGE_DAYS)}).",
            "flagged_items": [{"edge_count": edge_count, "mid_count": mid_count,
                               "edge_ratio": round(edge_ratio, 3)}]}


def check_counterparty_risk(txns: List[RawTransaction]) -> dict:
    """Check 8: LLM assessment of counterparty names for suspicious entities."""
    name = "Counterparty Risk Assessment"
    # Gather unique counterparties with their total volume
    cp_volume: dict[str, float] = defaultdict(float)
    cp_count: dict[str, int] = Counter()

    for t in txns:
        cp = (t.counterparty or t.description or "").strip()
        if not cp or len(cp) < 3:
            continue
        cp_key = cp[:60].upper()
        cp_volume[cp_key] += t.amount or 0
        cp_count[cp_key] += 1

    if not cp_volume:
        return {"check": name, "status": "pass",
                "details": "No counterparty data available.",
                "flagged_items": []}

    # Top 30 counterparties by volume
    top_cps = sorted(cp_volume.items(), key=lambda x: x[1], reverse=True)[:30]
    cp_list = "\n".join(
        f"  {i+1}. {cp} — {cp_count[cp]} txn(s), total {vol:,.2f}"
        for i, (cp, vol) in enumerate(top_cps)
    )

    prompt = (
        "You are a fraud analyst reviewing bank statement counterparties. "
        "Below are the top counterparties by transaction volume.\n\n"
        f"{cp_list}\n\n"
        "Identify any suspicious patterns:\n"
        "- Shell company names (random letters, no real business name)\n"
        "- Money service businesses or remittance companies\n"
        "- Gambling or high-risk merchants\n"
        "- Counterparties that appear to be personal accounts in a business statement\n"
        "- Any other red flags\n\n"
        "Respond ONLY with valid JSON (no markdown fences):\n"
        '{"status": "pass" or "fail" or "warning", '
        '"details": "brief assessment of counterparty risk", '
        '"flagged_counterparties": ["name1", "name2"]}'
    )

    try:
        raw = chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        raw = re.sub(r"^```json\s*|```\s*$", "", raw.strip()).strip()
        parsed = json.loads(raw)

        return {
            "check": name,
            "status": parsed.get("status", "warning"),
            "details": parsed.get("details", raw[:300]),
            "flagged_items": [{"counterparty": c} for c in parsed.get("flagged_counterparties", [])],
        }
    except Exception as e:
        return {"check": name, "status": "warning",
                "details": f"Could not run counterparty analysis: {e}",
                "flagged_items": []}


# ─── Risk Assessment ──────────────────────────────────────────────────────────

def _compute_risk(checks: list[dict]) -> tuple[str, int, str]:
    """
    Compute overall fraud risk from individual check results.
    Returns (risk_level, risk_score, summary_text).
    """
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    warn_count = sum(1 for c in checks if c["status"] == "warning")
    pass_count = sum(1 for c in checks if c["status"] == "pass")
    total = len(checks)

    # Score: fail=3, warning=1, pass=0
    score = fail_count * 3 + warn_count * 1

    if fail_count >= 4:
        risk = "critical"
    elif fail_count >= 2:
        risk = "high"
    elif fail_count >= 1 or warn_count >= 3:
        risk = "medium"
    elif warn_count >= 1:
        risk = "low"
    else:
        risk = "low"

    summary_parts = []
    summary_parts.append(f"{pass_count}/{total} checks passed")
    if fail_count:
        failed = [c["check"] for c in checks if c["status"] == "fail"]
        summary_parts.append(f"{fail_count} failed: {', '.join(failed)}")
    if warn_count:
        warned = [c["check"] for c in checks if c["status"] == "warning"]
        summary_parts.append(f"{warn_count} warnings: {', '.join(warned)}")

    summary = ". ".join(summary_parts) + "."
    return risk, score, summary


# ─── Agent Class ──────────────────────────────────────────────────────────────

class FraudAgent(BaseAgent):
    """
    Analyses extracted transactions for fraud indicators and produces
    structured results with an overall risk assessment.
    """

    def run(self, document_id: str, db: Session) -> dict:
        logger.info(f"🕵️  Fraud agent starting for document {document_id}")

        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return {
                "results": {"error": "Document not found"},
                "summary": "Document not found",
                "risk_level": "low",
            }

        # ── Fetch extracted transactions ──────────────────────────────────
        txns = (
            db.query(RawTransaction)
            .filter(RawTransaction.document_id == document_id)
            .all()
        )
        metrics = (
            db.query(StatementMetrics)
            .filter(StatementMetrics.document_id == document_id)
            .first()
        )

        if not txns:
            logger.warning("  No transactions found — skipping fraud checks")
            return {
                "results": {"checks": [], "total_checks": 0},
                "summary": "No transactions available for fraud analysis.",
                "risk_level": "low",
            }

        logger.info(f"  📊 Analysing {len(txns)} transactions for fraud signals...")

        # ── Run all checks ────────────────────────────────────────────────
        checks: list[dict] = []

        # Rule-based checks (fast, no LLM)
        logger.info("  🔢 Running rule-based fraud checks...")
        checks.append(check_round_amounts(txns))
        checks.append(check_duplicates(txns))
        checks.append(check_rapid_succession(txns))
        checks.append(check_large_outliers(txns))
        checks.append(check_balance_anomalies(txns))
        checks.append(check_cash_heavy(txns, metrics))
        checks.append(check_timing_patterns(txns))

        # LLM-powered check (last)
        logger.info("  🤖 Running counterparty risk assessment (LLM)...")
        checks.append(check_counterparty_risk(txns))

        # ── Compute risk ──────────────────────────────────────────────────
        risk_level, risk_score, summary = _compute_risk(checks)

        logger.info(f"  🕵️  Fraud result: {risk_level} (score={risk_score}) — {summary}")

        return {
            "results": {
                "checks": checks,
                "risk_score": risk_score,
                "pass_count": sum(1 for c in checks if c["status"] == "pass"),
                "fail_count": sum(1 for c in checks if c["status"] == "fail"),
                "warning_count": sum(1 for c in checks if c["status"] == "warning"),
                "total_checks": len(checks),
            },
            "summary": summary,
            "risk_level": risk_level,
        }
