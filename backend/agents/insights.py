"""
Insights Agent — Generates business intelligence insights from extracted bank statement data.

Analyzes:
1. Spending patterns & categories breakdown
2. Cash flow analysis (inflow vs outflow trends)
3. Top counterparties (vendors, customers)
4. Unusual transactions (large spikes, round numbers)
5. Day-of-month patterns
6. Channel analysis
7. Business health indicators
8. LLM-powered narrative summary with recommendations
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Union

from sqlalchemy.orm import Session

from agents.base import BaseAgent
from models import Document, RawTransaction, StatementMetrics, AggregatedMetrics
from services.llm_client import chat_completion

logger = logging.getLogger("ThirdEye.Agent.Insights")

# ─── Month ordering for Singapore bank statements ─────────────────────────────

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_day(date_str: str) -> Optional[int]:
    """Extract day number from date string like '01 DEC', '15 JAN', '01-Sep-2025', '01/12/2025'."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # Try DD-MMM-YYYY (DBS format: 01-Sep-2025)
    m = re.match(r'(\d{1,2})[\-/][A-Za-z]{3}', date_str)
    if m:
        return int(m.group(1))
    # Try DD MMM (OCBC/UOB format: 01 DEC)
    parts = date_str.split()
    if parts and parts[0].isdigit():
        return int(parts[0])
    # Try DD/MM/YYYY
    m = re.match(r'(\d{1,2})/\d{1,2}', date_str)
    if m:
        return int(m.group(1))
    return None


def _parse_month(date_str: str) -> Optional[str]:
    """Extract month abbreviation from date string."""
    if not date_str:
        return None
    date_str = date_str.strip().upper()
    # Try DD-MMM-YYYY (e.g. 01-SEP-2025)
    m = re.match(r'\d{1,2}[\-/]([A-Z]{3})', date_str)
    if m and m.group(1) in MONTH_MAP:
        return m.group(1)
    # Try DD MMM (e.g. 01 DEC)
    parts = date_str.split()
    for p in parts:
        if p in MONTH_MAP:
            return p
    return None


# ─── Category labels for display ──────────────────────────────────────────────

CATEGORY_LABELS = {
    "salary": "Salary & Wages",
    "revenue": "Business Revenue",
    "rent": "Rent & Lease",
    "utilities": "Utilities",
    "food_beverage": "Food & Beverage",
    "transport": "Transport",
    "supplier": "Supplier Payments",
    "purchase": "Purchases",
    "transfer": "Fund Transfers",
    "loan": "Loan Payments",
    "tax": "Tax & Government",
    "insurance": "Insurance",
    "fees": "Bank Fees & Charges",
    "refund": "Refunds",
    "other": "Other / Uncategorized",
}


class InsightsAgent(BaseAgent):
    """Generates business intelligence insights from extracted transaction data."""

    def run(self, document_id: str, db: Session) -> dict:
        logger.info(f"Insights agent running for document {document_id}")

        # ── Fetch extracted data ──────────────────────────────────────────
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return self._error("Document not found")

        transactions = (
            db.query(RawTransaction)
            .filter(RawTransaction.document_id == document_id)
            .all()
        )
        metrics = (
            db.query(StatementMetrics)
            .filter(StatementMetrics.document_id == document_id)
            .first()
        )

        if not transactions:
            return self._error("No transactions found — run extraction first")

        logger.info(f"  📊 Analyzing {len(transactions)} transactions...")

        # ── Build all insight sections ────────────────────────────────────
        category_breakdown = self._category_analysis(transactions)
        cash_flow = self._cash_flow_analysis(transactions, metrics)
        top_counterparties = self._counterparty_analysis(transactions)
        unusual_txns = self._unusual_transaction_detection(transactions, metrics)
        day_patterns = self._day_of_month_patterns(transactions)
        channel_analysis = self._channel_analysis(transactions)
        business_health = self._business_health_indicators(transactions, metrics)

        # ── Prepare data for LLM narrative ────────────────────────────────
        insights_data = {
            "account_holder": metrics.account_holder if metrics else "Unknown",
            "bank": metrics.bank if metrics else "Unknown",
            "period": metrics.statement_period if metrics else "Unknown",
            "opening_balance": metrics.opening_balance if metrics else 0,
            "closing_balance": metrics.closing_balance if metrics else 0,
            "total_transactions": len(transactions),
            "category_breakdown": category_breakdown,
            "cash_flow": cash_flow,
            "top_counterparties": top_counterparties,
            "unusual_transactions": unusual_txns,
            "day_patterns": day_patterns,
            "channel_analysis": channel_analysis,
            "business_health": business_health,
        }

        # ── LLM narrative summary ─────────────────────────────────────────
        logger.info("  🤖 Generating LLM narrative...")
        narrative = self._generate_llm_narrative(insights_data)

        # ── Determine risk level ──────────────────────────────────────────
        risk_level = self._assess_risk(insights_data)

        # ── Build final results ───────────────────────────────────────────
        results = {
            "category_breakdown": category_breakdown,
            "cash_flow": cash_flow,
            "top_counterparties": top_counterparties,
            "unusual_transactions": unusual_txns,
            "day_of_month_patterns": day_patterns,
            "channel_analysis": channel_analysis,
            "business_health": business_health,
            "narrative": narrative,
        }

        summary_parts = [
            f"Period: {metrics.statement_period}" if metrics else "",
            f"Transactions: {len(transactions)}",
            f"Net cash flow: {(cash_flow.get('net_flow') or 0):,.2f}",
            f"Top category: {category_breakdown.get('top_debit_category', 'N/A')}",
            f"Risk: {risk_level}",
        ]
        summary = " | ".join(p for p in summary_parts if p)

        logger.info(f"  ✅ Insights complete — risk: {risk_level}")

        return {
            "results": results,
            "summary": summary,
            "risk_level": risk_level,
        }

    def run_group(self, upload_group_id: str, db: Session) -> dict:
        """Run group-level insights across ALL statements in an upload group.

        Aggregates transactions from all documents, computes cross-statement
        trends (monthly flows, balance trajectory), and generates a combined
        LLM narrative covering the full statement period.
        """
        logger.info(f"📊 Group insights agent running for group {upload_group_id}")

        # ── Fetch ALL transactions across the group ──
        transactions = (
            db.query(RawTransaction)
            .filter(RawTransaction.upload_group_id == upload_group_id)
            .all()
        )
        all_metrics = (
            db.query(StatementMetrics)
            .filter(StatementMetrics.upload_group_id == upload_group_id)
            .order_by(StatementMetrics.statement_period)
            .all()
        )
        agg_metrics = (
            db.query(AggregatedMetrics)
            .filter(AggregatedMetrics.upload_group_id == upload_group_id)
            .first()
        )

        if not transactions:
            return self._error("No transactions found across group — run extraction first")

        total_docs = len(all_metrics)
        logger.info(
            f"  📊 Analyzing {len(transactions)} transactions across {total_docs} statements..."
        )

        # ── Build all insight sections (using all transactions) ──
        combined_metrics = all_metrics[0] if all_metrics else None
        category_breakdown = self._category_analysis(transactions)
        cash_flow = self._cash_flow_analysis(transactions, combined_metrics)
        top_counterparties = self._counterparty_analysis(transactions)
        unusual_txns = self._unusual_transaction_detection(transactions, combined_metrics)
        day_patterns = self._day_of_month_patterns(transactions)
        channel_analysis = self._channel_analysis(transactions)

        # ── Monthly trends across statements ──
        monthly_trends = self._monthly_trends(transactions, all_metrics)

        # ── Combined business health (use aggregated metrics) ──
        business_health = self._group_business_health(transactions, all_metrics, agg_metrics)

        # ── Per-statement summary ──
        per_statement = []
        for m in all_metrics:
            per_statement.append({
                "document_id": m.document_id,
                "period": m.statement_period,
                "bank": m.bank,
                "opening_balance": m.opening_balance,
                "closing_balance": m.closing_balance,
                "total_credits": m.total_amount_of_credit_transactions,
                "total_debits": m.total_amount_of_debit_transactions,
                "credit_count": m.total_no_of_credit_transactions,
                "debit_count": m.total_no_of_debit_transactions,
            })

        # ── LLM narrative ──
        insights_data = {
            "account_holder": agg_metrics.account_holder if agg_metrics else (
                all_metrics[0].account_holder if all_metrics else "Unknown"
            ),
            "bank": agg_metrics.bank if agg_metrics else (
                all_metrics[0].bank if all_metrics else "Unknown"
            ),
            "period": agg_metrics.period_covered if agg_metrics else "Multiple statements",
            "opening_balance": all_metrics[0].opening_balance if all_metrics else 0,
            "closing_balance": all_metrics[-1].closing_balance if all_metrics else 0,
            "total_transactions": len(transactions),
            "total_statements": total_docs,
            "category_breakdown": category_breakdown,
            "cash_flow": cash_flow,
            "top_counterparties": top_counterparties,
            "unusual_transactions": unusual_txns,
            "day_patterns": day_patterns,
            "channel_analysis": channel_analysis,
            "business_health": business_health,
            "monthly_trends": monthly_trends,
        }

        logger.info("  🤖 Generating group LLM narrative...")
        narrative = self._generate_group_narrative(insights_data)

        risk_level = self._assess_risk(insights_data)

        results = {
            "total_statements": total_docs,
            "total_transactions": len(transactions),
            "per_statement_summary": per_statement,
            "category_breakdown": category_breakdown,
            "cash_flow": cash_flow,
            "top_counterparties": top_counterparties,
            "unusual_transactions": unusual_txns,
            "day_of_month_patterns": day_patterns,
            "channel_analysis": channel_analysis,
            "business_health": business_health,
            "monthly_trends": monthly_trends,
            "narrative": narrative,
        }

        summary_parts = [
            f"Statements: {total_docs}",
            f"Transactions: {len(transactions)}",
            f"Net cash flow: {(cash_flow.get('net_flow') or 0):,.2f}",
            f"Top category: {category_breakdown.get('top_debit_category', 'N/A')}",
            f"Risk: {risk_level}",
        ]
        summary = " | ".join(p for p in summary_parts if p)

        logger.info(f"  ✅ Group insights complete — risk: {risk_level}")

        return {
            "results": results,
            "summary": summary,
            "risk_level": risk_level,
        }

    def _monthly_trends(self, transactions: List[RawTransaction], all_metrics: list) -> dict:
        """Compute monthly trends across multiple statements."""
        monthly_data = defaultdict(lambda: {
            "credits": 0.0, "debits": 0.0, "credit_count": 0, "debit_count": 0,
        })

        for t in transactions:
            month = _parse_month(t.date)
            if not month:
                continue
            if t.transaction_type == "credit":
                monthly_data[month]["credits"] += t.amount or 0
                monthly_data[month]["credit_count"] += 1
            elif t.transaction_type == "debit":
                monthly_data[month]["debits"] += t.amount or 0
                monthly_data[month]["debit_count"] += 1

        # Sort by month order
        sorted_months = sorted(monthly_data.keys(), key=lambda m: MONTH_MAP.get(m, 0))
        monthly_flow = []
        for month in sorted_months:
            d = monthly_data[month]
            monthly_flow.append({
                "month": month,
                "total_credits": round(d["credits"], 2),
                "total_debits": round(d["debits"], 2),
                "net_flow": round(d["credits"] - d["debits"], 2),
                "credit_count": d["credit_count"],
                "debit_count": d["debit_count"],
            })

        # Balance trajectory from per-statement metrics
        balance_trajectory = []
        for m in all_metrics:
            balance_trajectory.append({
                "period": m.statement_period,
                "opening_balance": m.opening_balance,
                "closing_balance": m.closing_balance,
                "max_balance": m.max_eod_balance,
                "min_balance": m.min_eod_balance,
            })

        return {
            "monthly_flow": monthly_flow,
            "balance_trajectory": balance_trajectory,
            "total_months": len(sorted_months),
        }

    def _group_business_health(
        self,
        transactions: List[RawTransaction],
        all_metrics: list,
        agg_metrics,
    ) -> dict:
        """Compute business health indicators across all statements."""
        if not all_metrics:
            return {"score": 0, "indicators": {}, "assessment": "Insufficient data"}

        indicators = {}

        # Overall balance trend
        first_opening = all_metrics[0].opening_balance or 0
        last_closing = all_metrics[-1].closing_balance or 0
        balance_change = last_closing - first_opening
        indicators["overall_balance_change"] = round(balance_change, 2)
        indicators["overall_balance_change_pct"] = (
            round(balance_change / first_opening * 100, 1) if first_opening else 0
        )
        indicators["balance_trend"] = "growing" if balance_change > 0 else "declining"

        # Total volume across all statements
        total_in = sum(m.total_amount_of_credit_transactions or 0 for m in all_metrics)
        total_out = sum(m.total_amount_of_debit_transactions or 0 for m in all_metrics)
        indicators["total_credits_all"] = round(total_in, 2)
        indicators["total_debits_all"] = round(total_out, 2)
        indicators["revenue_coverage_ratio"] = round(total_in / total_out, 3) if total_out else 0

        # Monthly average
        num_months = len(all_metrics) or 1
        indicators["avg_monthly_credits"] = round(total_in / num_months, 2)
        indicators["avg_monthly_debits"] = round(total_out / num_months, 2)
        indicators["avg_monthly_net"] = round((total_in - total_out) / num_months, 2)

        # Cash runway
        avg_monthly_out = total_out / num_months if num_months else 0
        runway = last_closing / avg_monthly_out if avg_monthly_out > 0 else 0
        indicators["cash_runway_months"] = round(runway, 2)

        # Balance volatility
        closings = [m.closing_balance or 0 for m in all_metrics]
        if len(closings) > 1:
            import statistics as stats
            indicators["balance_std_dev"] = round(stats.stdev(closings), 2)
            indicators["balance_cv"] = round(
                stats.stdev(closings) / stats.mean(closings) * 100, 1
            ) if stats.mean(closings) > 0 else 0
        else:
            indicators["balance_std_dev"] = 0
            indicators["balance_cv"] = 0

        # Score
        score = 50
        coverage = indicators["revenue_coverage_ratio"]
        if coverage >= 1.0:
            score += 10
        if coverage >= 0.8:
            score += 5
        if balance_change > 0:
            score += 10
        if runway >= 1.0:
            score += 10
        elif runway >= 0.5:
            score += 5
        if coverage < 0.5:
            score -= 15
        if balance_change < -first_opening * 0.3:
            score -= 10
        if runway < 0.2:
            score -= 10

        score = max(0, min(100, score))

        if score >= 80:
            assessment = "Strong — healthy cash flows across the analysis period"
        elif score >= 60:
            assessment = "Moderate — stable with some areas to watch"
        elif score >= 40:
            assessment = "Caution — cash flow strain detected across statements"
        else:
            assessment = "Concern — significant cash flow issues across the period"

        return {
            "score": score,
            "assessment": assessment,
            "indicators": indicators,
            "statements_analyzed": len(all_metrics),
        }

    def _generate_group_narrative(self, data: dict) -> dict:
        """Generate LLM narrative for group-level insights."""
        prompt = f"""You are a senior financial analyst reviewing MULTIPLE bank statements for the same customer.
Generate a comprehensive narrative analysis covering the full period.

**Account**: {data['account_holder']} at {data['bank']}
**Period**: {data['period']}
**Total Statements**: {data['total_statements']}
**Total Transactions**: {data['total_transactions']}
**Opening Balance (first statement)**: {(data['opening_balance'] or 0):,.2f}
**Closing Balance (last statement)**: {(data['closing_balance'] or 0):,.2f}

**Category Breakdown (Top Debits)**:
{json.dumps(data['category_breakdown']['debit_categories'][:5], indent=2)}

**Top Vendors**:
{json.dumps(data['top_counterparties']['top_vendors'][:8], indent=2)}

**Cash Flow**:
- Total Inflow: {(data['cash_flow'].get('total_inflow') or 0):,.2f}
- Total Outflow: {(data['cash_flow'].get('total_outflow') or 0):,.2f}
- Net Flow: {(data['cash_flow'].get('net_flow') or 0):,.2f}

**Monthly Trends**:
{json.dumps(data.get('monthly_trends', {}).get('monthly_flow', []), indent=2)}

**Business Health Score**: {data['business_health']['score']}/100 — {data['business_health']['assessment']}

Return a JSON object with these keys:
{{
  "executive_summary": "3-4 sentence high-level summary covering the full period",
  "spending_analysis": "3-4 sentences on spending patterns and trends across months",
  "income_analysis": "2-3 sentences on income stability and sources",
  "cash_flow_assessment": "3-4 sentences on cash flow trajectory and sustainability",
  "trend_analysis": "2-3 sentences on month-over-month trends and patterns",
  "risk_observations": "2-3 sentences on concerning patterns across statements",
  "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3", "recommendation 4"]
}}
"""
        try:
            response = chat_completion(
                messages=[
                    {"role": "system", "content": "You are a senior financial analyst. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2500,
                response_format={"type": "json_object"},
            )
            return json.loads(response)
        except Exception as e:
            logger.error(f"Group LLM narrative failed: {e}")
            return {
                "executive_summary": "Group narrative generation failed — see structured data.",
                "spending_analysis": "",
                "income_analysis": "",
                "cash_flow_assessment": "",
                "trend_analysis": "",
                "risk_observations": "",
                "recommendations": [],
            }

    # ═══════════════════════════════════════════════════════════════════════════
    #  Insight Generators
    # ═══════════════════════════════════════════════════════════════════════════

    def _category_analysis(self, transactions: List[RawTransaction]) -> dict:
        """Break down spending and income by category."""
        debit_by_cat = defaultdict(lambda: {"count": 0, "total": 0.0})
        credit_by_cat = defaultdict(lambda: {"count": 0, "total": 0.0})

        for t in transactions:
            cat = t.category or "other"
            if t.transaction_type == "debit":
                debit_by_cat[cat]["count"] += 1
                debit_by_cat[cat]["total"] += t.amount or 0
            elif t.transaction_type == "credit":
                credit_by_cat[cat]["count"] += 1
                credit_by_cat[cat]["total"] += t.amount or 0

        # Format debit categories sorted by total
        debit_categories = []
        total_debits = sum(d["total"] for d in debit_by_cat.values())
        for cat, data in sorted(debit_by_cat.items(), key=lambda x: x[1]["total"], reverse=True):
            pct = (data["total"] / total_debits * 100) if total_debits > 0 else 0
            debit_categories.append({
                "category": cat,
                "label": CATEGORY_LABELS.get(cat, cat.title()),
                "count": data["count"],
                "total": round(data["total"], 2),
                "percentage": round(pct, 1),
            })

        # Format credit categories sorted by total
        credit_categories = []
        total_credits = sum(d["total"] for d in credit_by_cat.values())
        for cat, data in sorted(credit_by_cat.items(), key=lambda x: x[1]["total"], reverse=True):
            pct = (data["total"] / total_credits * 100) if total_credits > 0 else 0
            credit_categories.append({
                "category": cat,
                "label": CATEGORY_LABELS.get(cat, cat.title()),
                "count": data["count"],
                "total": round(data["total"], 2),
                "percentage": round(pct, 1),
            })

        top_debit_cat = debit_categories[0]["label"] if debit_categories else "N/A"
        top_credit_cat = credit_categories[0]["label"] if credit_categories else "N/A"

        return {
            "debit_categories": debit_categories,
            "credit_categories": credit_categories,
            "total_debit_amount": round(total_debits, 2),
            "total_credit_amount": round(total_credits, 2),
            "top_debit_category": top_debit_cat,
            "top_credit_category": top_credit_cat,
            "debit_category_count": len(debit_categories),
            "credit_category_count": len(credit_categories),
        }

    def _cash_flow_analysis(self, transactions: List[RawTransaction], metrics: Optional[StatementMetrics]) -> dict:
        """Analyze cash flow by day of month."""
        daily_inflow = defaultdict(float)
        daily_outflow = defaultdict(float)
        daily_net = defaultdict(float)

        for t in transactions:
            day = _parse_day(t.date)
            if day is None:
                continue
            if t.transaction_type == "credit":
                daily_inflow[day] += t.amount or 0
                daily_net[day] += t.amount or 0
            elif t.transaction_type == "debit":
                daily_outflow[day] += t.amount or 0
                daily_net[day] -= t.amount or 0

        all_days = sorted(set(list(daily_inflow.keys()) + list(daily_outflow.keys())))
        daily_flow = []
        for day in all_days:
            daily_flow.append({
                "day": day,
                "inflow": round(daily_inflow.get(day, 0), 2),
                "outflow": round(daily_outflow.get(day, 0), 2),
                "net": round(daily_net.get(day, 0), 2),
            })

        total_inflow = sum(daily_inflow.values())
        total_outflow = sum(daily_outflow.values())
        net_flow = total_inflow - total_outflow

        # Find peak inflow / outflow days
        peak_inflow_day = max(daily_inflow, key=daily_inflow.get) if daily_inflow else None
        peak_outflow_day = max(daily_outflow, key=daily_outflow.get) if daily_outflow else None

        # Week breakdown (1-7, 8-14, 15-21, 22-31)
        week_flows = {
            "week_1 (1-7)": {"inflow": 0, "outflow": 0},
            "week_2 (8-14)": {"inflow": 0, "outflow": 0},
            "week_3 (15-21)": {"inflow": 0, "outflow": 0},
            "week_4 (22-31)": {"inflow": 0, "outflow": 0},
        }
        for day in all_days:
            if day <= 7:
                key = "week_1 (1-7)"
            elif day <= 14:
                key = "week_2 (8-14)"
            elif day <= 21:
                key = "week_3 (15-21)"
            else:
                key = "week_4 (22-31)"
            week_flows[key]["inflow"] += daily_inflow.get(day, 0)
            week_flows[key]["outflow"] += daily_outflow.get(day, 0)

        weekly_breakdown = []
        for week, data in week_flows.items():
            weekly_breakdown.append({
                "week": week,
                "inflow": round(data["inflow"], 2),
                "outflow": round(data["outflow"], 2),
                "net": round(data["inflow"] - data["outflow"], 2),
            })

        return {
            "total_inflow": round(total_inflow, 2),
            "total_outflow": round(total_outflow, 2),
            "net_flow": round(net_flow, 2),
            "net_flow_direction": "positive" if net_flow >= 0 else "negative",
            "burn_rate": round(total_outflow, 2),
            "peak_inflow_day": peak_inflow_day,
            "peak_outflow_day": peak_outflow_day,
            "daily_flow": daily_flow,
            "weekly_breakdown": weekly_breakdown,
        }

    def _counterparty_analysis(self, transactions: List[RawTransaction]) -> dict:
        """Identify top senders and receivers."""
        vendor_totals = defaultdict(lambda: {"count": 0, "total": 0.0})
        customer_totals = defaultdict(lambda: {"count": 0, "total": 0.0})

        for t in transactions:
            cp = (t.counterparty or "").strip()
            if not cp or cp.lower() in ("unknown", "n/a", ""):
                continue
            if t.transaction_type == "debit":
                vendor_totals[cp]["count"] += 1
                vendor_totals[cp]["total"] += t.amount or 0
            elif t.transaction_type == "credit":
                customer_totals[cp]["count"] += 1
                customer_totals[cp]["total"] += t.amount or 0

        top_vendors = sorted(vendor_totals.items(), key=lambda x: x[1]["total"], reverse=True)[:15]
        top_customers = sorted(customer_totals.items(), key=lambda x: x[1]["total"], reverse=True)[:15]

        # Recurring vendors (appeared more than 3 times)
        recurring_vendors = [
            {"name": name, "count": data["count"], "total": round(data["total"], 2)}
            for name, data in sorted(vendor_totals.items(), key=lambda x: x[1]["count"], reverse=True)
            if data["count"] >= 3
        ][:10]

        return {
            "top_vendors": [
                {"name": name, "count": data["count"], "total": round(data["total"], 2)}
                for name, data in top_vendors
            ],
            "top_customers": [
                {"name": name, "count": data["count"], "total": round(data["total"], 2)}
                for name, data in top_customers
            ],
            "recurring_vendors": recurring_vendors,
            "unique_vendor_count": len(vendor_totals),
            "unique_customer_count": len(customer_totals),
        }

    def _unusual_transaction_detection(
        self, transactions: List[RawTransaction], metrics: Optional[StatementMetrics]
    ) -> dict:
        """Detect unusual or noteworthy transactions."""
        debits = [t for t in transactions if t.transaction_type == "debit" and t.amount]
        credits = [t for t in transactions if t.transaction_type == "credit" and t.amount]

        unusual = []

        # 1. Large transactions (>3x average)
        if debits:
            avg_debit = sum(t.amount for t in debits) / len(debits)
            threshold = avg_debit * 3
            for t in debits:
                if t.amount >= threshold:
                    multiple = t.amount / avg_debit
                    unusual.append({
                        "type": "large_debit",
                        "date": t.date,
                        "description": t.description,
                        "amount": t.amount,
                        "reason": f"Amount ({t.amount:,.2f}) is >3x the average debit ({avg_debit:,.2f})",
                        "explanation": f"This outgoing payment of {t.amount:,.2f} is {multiple:.1f}x the average "
                                       f"debit of {avg_debit:,.2f}. Transactions significantly above the account's "
                                       f"typical spending pattern may indicate bulk payments, one-off capital "
                                       f"expenditures, or potentially unauthorized large withdrawals.",
                    })

        if credits:
            avg_credit = sum(t.amount for t in credits) / len(credits)
            threshold = avg_credit * 3
            for t in credits:
                if t.amount >= threshold:
                    multiple = t.amount / avg_credit
                    unusual.append({
                        "type": "large_credit",
                        "date": t.date,
                        "description": t.description,
                        "amount": t.amount,
                        "reason": f"Amount ({t.amount:,.2f}) is >3x the average credit ({avg_credit:,.2f})",
                        "explanation": f"This incoming payment of {t.amount:,.2f} is {multiple:.1f}x the average "
                                       f"credit of {avg_credit:,.2f}. Unusually large inflows may represent "
                                       f"one-off settlements, large client payments, loan disbursements, or "
                                       f"irregular deposits that merit source verification.",
                    })

        # 2. Round number transactions (exact thousands — could indicate manual transfers)
        round_txns = []
        for t in transactions:
            if t.amount and t.amount >= 1000 and t.amount == int(t.amount):
                round_txns.append({
                    "type": "round_number",
                    "date": t.date,
                    "description": t.description,
                    "amount": t.amount,
                    "transaction_type": t.transaction_type,
                    "reason": f"Exact round amount of {t.amount:,.0f} — may indicate a manual or structured transfer rather than an organic payment",
                    "explanation": f"This {t.transaction_type or 'transaction'} of {t.amount:,.2f} is an exact multiple of 1,000. "
                                   f"Round-number transactions can signal manual transfers, loan repayments, or "
                                   f"structured deposits that warrant closer review.",
                })

        # 3. Same-day large movements (both in and out on same day)
        day_movements = defaultdict(lambda: {"credits": 0.0, "debits": 0.0})
        for t in transactions:
            if t.date and t.amount:
                if t.transaction_type == "credit":
                    day_movements[t.date]["credits"] += t.amount
                else:
                    day_movements[t.date]["debits"] += t.amount

        same_day_flags = []
        for day, mv in day_movements.items():
            if mv["credits"] > 5000 and mv["debits"] > 5000:
                net = round(mv["credits"] - mv["debits"], 2)
                same_day_flags.append({
                    "type": "same_day_large_movement",
                    "date": day,
                    "credits": round(mv["credits"], 2),
                    "debits": round(mv["debits"], 2),
                    "amount": round(mv["credits"] + mv["debits"], 2),
                    "reason": "Both large credits and debits on the same day",
                    "description": f"Credits: {mv['credits']:,.2f} | Debits: {mv['debits']:,.2f} | Net: {net:,.2f}",
                    "explanation": f"On {day}, the account received {mv['credits']:,.2f} in credits and "
                                   f"sent out {mv['debits']:,.2f} in debits (net: {net:,.2f}). "
                                   f"Same-day large bi-directional flows can indicate pass-through activity, "
                                   f"money laundering layering, or fund restructuring.",
                })

        # 4. Low balance alerts
        low_balance_events = []
        seen_dates = set()
        for t in transactions:
            if t.balance is not None and t.balance < 10000 and t.date not in seen_dates:
                low_balance_events.append({
                    "type": "low_balance",
                    "date": t.date,
                    "balance": t.balance,
                    "amount": t.balance,
                    "description": t.description,
                    "reason": f"Account balance dropped to {t.balance:,.2f}",
                    "explanation": f"After transaction '{(t.description or 'N/A')[:60]}', the account balance "
                                   f"fell to {t.balance:,.2f}. Low balances may indicate cash flow stress, "
                                   f"over-commitment, or an impending overdraft.",
                })
                seen_dates.add(t.date)

        return {
            "large_transactions": unusual[:20],
            "round_number_transactions": round_txns[:20],
            "same_day_large_movements": same_day_flags,
            "low_balance_events": low_balance_events[:10],
            "total_flags": len(unusual) + len(same_day_flags) + len(low_balance_events),
        }

    def _day_of_month_patterns(self, transactions: List[RawTransaction]) -> dict:
        """Analyze transaction density by day of month."""
        day_counts = Counter()
        day_amounts = defaultdict(float)

        for t in transactions:
            day = _parse_day(t.date)
            if day:
                day_counts[day] += 1
                day_amounts[day] += t.amount or 0

        pattern = []
        for day in sorted(set(day_counts.keys())):
            pattern.append({
                "day": day,
                "transaction_count": day_counts[day],
                "total_amount": round(day_amounts[day], 2),
            })

        busiest_day = max(day_counts, key=day_counts.get) if day_counts else None
        quietest_day = min(day_counts, key=day_counts.get) if day_counts else None
        highest_value_day = max(day_amounts, key=day_amounts.get) if day_amounts else None

        return {
            "daily_pattern": pattern,
            "busiest_day": busiest_day,
            "quietest_day": quietest_day,
            "highest_value_day": highest_value_day,
            "active_days": len(day_counts),
        }

    def _channel_analysis(self, transactions: List[RawTransaction]) -> dict:
        """Break down transactions by payment channel."""
        channel_data = defaultdict(lambda: {"count": 0, "total": 0.0})

        for t in transactions:
            ch = (t.channel or "Unknown").strip()
            channel_data[ch]["count"] += 1
            channel_data[ch]["total"] += t.amount or 0

        channels = sorted(channel_data.items(), key=lambda x: x[1]["total"], reverse=True)
        total_amount = sum(d["total"] for _, d in channels)

        return {
            "channels": [
                {
                    "channel": name,
                    "count": data["count"],
                    "total": round(data["total"], 2),
                    "percentage": round(data["total"] / total_amount * 100, 1) if total_amount > 0 else 0,
                }
                for name, data in channels
            ],
            "dominant_channel": channels[0][0] if channels else "N/A",
            "total_channels": len(channels),
        }

    def _business_health_indicators(
        self, transactions: List[RawTransaction], metrics: Optional[StatementMetrics]
    ) -> dict:
        """Compute business health score and indicators."""
        indicators = {}

        if not metrics:
            return {"score": 0, "indicators": {}, "assessment": "Insufficient data"}

        # 1. Liquidity — closing balance vs average monthly outflow
        opening = metrics.opening_balance or 0
        closing = metrics.closing_balance or 0
        total_out = metrics.total_amount_of_debit_transactions or 0
        total_in = metrics.total_amount_of_credit_transactions or 0

        # Cash runway (how many months of expenses the closing balance covers)
        runway_months = closing / total_out if total_out > 0 else 0
        indicators["cash_runway_months"] = round(runway_months, 2)

        # 2. Revenue coverage (credits vs debits ratio)
        coverage = total_in / total_out if total_out > 0 else 0
        indicators["revenue_coverage_ratio"] = round(coverage, 3)

        # 3. Balance trend
        balance_change = closing - opening
        balance_change_pct = (balance_change / opening * 100) if opening > 0 else 0
        indicators["balance_change"] = round(balance_change, 2)
        indicators["balance_change_pct"] = round(balance_change_pct, 1)
        indicators["balance_trend"] = "growing" if balance_change > 0 else "declining"

        # 4. Cash deposit ratio (cash deposits / total credits — high ratio is suspicious)
        cash_dep_amount = metrics.total_amount_of_cash_deposits or 0
        cash_ratio = (cash_dep_amount / total_in * 100) if total_in > 0 else 0
        indicators["cash_deposit_ratio_pct"] = round(cash_ratio, 1)

        # 5. Fee burden
        fees = metrics.total_fees_charged or 0
        fee_burden = (fees / total_out * 100) if total_out > 0 else 0
        indicators["fee_burden_pct"] = round(fee_burden, 3)
        indicators["total_fees"] = round(fees, 2)

        # 6. Transaction velocity (transactions per active day)
        days_active = len(set(_parse_day(t.date) for t in transactions if _parse_day(t.date)))
        velocity = len(transactions) / days_active if days_active > 0 else 0
        indicators["daily_transaction_velocity"] = round(velocity, 1)
        indicators["active_days"] = days_active

        # 7. Min balance risk
        min_bal = metrics.min_eod_balance or 0
        avg_daily_spend = total_out / days_active if days_active > 0 else 0
        min_balance_cover_days = min_bal / avg_daily_spend if avg_daily_spend > 0 else 0
        indicators["min_balance_cover_days"] = round(min_balance_cover_days, 1)

        # ── Compute composite score (0-100) ──────────────────────────────
        score = 50  # start at neutral

        # Positive signals
        if coverage >= 1.0:
            score += 10
        if coverage >= 0.8:
            score += 5
        if closing >= opening:
            score += 10
        if runway_months >= 0.5:
            score += 5
        if runway_months >= 1.0:
            score += 5
        if min_balance_cover_days >= 3:
            score += 5

        # Negative signals
        if coverage < 0.5:
            score -= 15
        if closing < opening * 0.5:
            score -= 10
        if min_bal < 5000:
            score -= 10
        if cash_ratio > 30:
            score -= 5
        if runway_months < 0.1:
            score -= 10

        score = max(0, min(100, score))

        if score >= 80:
            assessment = "Strong — healthy cash flows with positive trajectory"
        elif score >= 60:
            assessment = "Moderate — stable but watch for declining balances"
        elif score >= 40:
            assessment = "Caution — cash flow strain detected"
        else:
            assessment = "Concern — significant cash flow issues observed"

        return {
            "score": score,
            "assessment": assessment,
            "indicators": indicators,
        }

    # ═══════════════════════════════════════════════════════════════════════════
    #  LLM Narrative
    # ═══════════════════════════════════════════════════════════════════════════

    def _generate_llm_narrative(self, data: dict) -> dict:
        """Use Azure OpenAI to generate a human-readable narrative summary."""
        prompt = f"""You are a senior financial analyst reviewing a business bank statement.
Generate a concise but insightful narrative analysis based on the data below.

**Account**: {data['account_holder']} at {data['bank']}
**Period**: {data['period']}
**Opening Balance**: {(data['opening_balance'] or 0):,.2f}
**Closing Balance**: {(data['closing_balance'] or 0):,.2f}
**Total Transactions**: {data['total_transactions']}

**Category Breakdown (Top Debits)**:
{json.dumps(data['category_breakdown']['debit_categories'][:5], indent=2)}

**Top Vendors**:
{json.dumps(data['top_counterparties']['top_vendors'][:8], indent=2)}

**Top Customers/Senders**:
{json.dumps(data['top_counterparties']['top_customers'][:5], indent=2)}

**Cash Flow**:
- Total Inflow: {(data['cash_flow'].get('total_inflow') or 0):,.2f}
- Total Outflow: {(data['cash_flow'].get('total_outflow') or 0):,.2f}
- Net Flow: {(data['cash_flow'].get('net_flow') or 0):,.2f}
- Peak Inflow Day: {data['cash_flow'].get('peak_inflow_day')}
- Peak Outflow Day: {data['cash_flow'].get('peak_outflow_day')}

**Business Health Score**: {data['business_health']['score']}/100 — {data['business_health']['assessment']}
**Key Indicators**: {json.dumps(data['business_health']['indicators'], indent=2)}

**Unusual Transactions**: {data['unusual_transactions']['total_flags']} flags detected
- Large transactions: {len(data['unusual_transactions']['large_transactions'])}
- Same-day large movements: {len(data['unusual_transactions']['same_day_large_movements'])}
- Low balance events: {len(data['unusual_transactions']['low_balance_events'])}

Return a JSON object with these keys:
{{
  "executive_summary": "2-3 sentence high-level summary",
  "spending_analysis": "3-4 sentences on spending patterns and major expense categories",
  "income_analysis": "2-3 sentences on income sources and patterns",
  "cash_flow_assessment": "2-3 sentences on cash flow health, burn rate, and trajectory",
  "risk_observations": "2-3 sentences on any concerning patterns or red flags",
  "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]
}}
"""
        try:
            response = chat_completion(
                messages=[
                    {"role": "system", "content": "You are a senior financial analyst. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            narrative = json.loads(response)
            return narrative
        except Exception as e:
            logger.error(f"LLM narrative generation failed: {e}")
            return {
                "executive_summary": "Narrative generation failed — see structured data for insights.",
                "spending_analysis": "",
                "income_analysis": "",
                "cash_flow_assessment": "",
                "risk_observations": "",
                "recommendations": [],
            }

    # ═══════════════════════════════════════════════════════════════════════════
    #  Risk Assessment
    # ═══════════════════════════════════════════════════════════════════════════

    def _assess_risk(self, data: dict) -> str:
        """Determine overall risk level from insights data."""
        score = data["business_health"]["score"]
        flags = data["unusual_transactions"]["total_flags"]

        if score >= 70 and flags < 5:
            return "low"
        elif score >= 50 and flags < 15:
            return "medium"
        elif score >= 30:
            return "high"
        else:
            return "critical"

    def _error(self, message: str) -> dict:
        return {
            "results": {"error": message},
            "summary": f"Insights failed: {message}",
            "risk_level": "low",
        }
