from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ─── Document Schemas ─────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    status: str
    upload_group_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    upload_group_id: str
    documents: list[DocumentResponse]
    message: str


# ─── Transaction Schemas ──────────────────────────────────────────────────────

class TransactionResponse(BaseModel):
    id: str
    date: Optional[str] = None
    description: Optional[str] = None
    transaction_type: Optional[str] = None
    amount: Optional[float] = None
    balance: Optional[float] = None
    reference: Optional[str] = None
    category: Optional[str] = None
    counterparty: Optional[str] = None
    channel: Optional[str] = None
    is_cash: bool = False
    is_cheque: bool = False
    page_number: Optional[int] = None

    class Config:
        from_attributes = True


# ─── Metrics Schemas ──────────────────────────────────────────────────────────

class StatementMetricsResponse(BaseModel):
    account_holder: Optional[str] = None
    bank: Optional[str] = None
    account_number: Optional[str] = None
    currency: Optional[str] = None
    statement_period: Optional[str] = None
    months_of_statement: Optional[str] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    max_eod_balance: Optional[float] = None
    min_eod_balance: Optional[float] = None
    avg_eod_balance: Optional[float] = None
    total_no_of_credit_transactions: int = 0
    total_amount_of_credit_transactions: float = 0.0
    total_no_of_debit_transactions: int = 0
    total_amount_of_debit_transactions: float = 0.0
    average_deposit: float = 0.0
    average_withdrawal: float = 0.0
    max_debit_transaction: float = 0.0
    min_debit_transaction: float = 0.0
    max_credit_transaction: float = 0.0
    min_credit_transaction: float = 0.0
    total_no_of_cash_deposits: int = 0
    total_amount_of_cash_deposits: float = 0.0
    total_no_of_cash_withdrawals: int = 0
    total_amount_of_cash_withdrawals: float = 0.0
    total_no_of_cheque_withdrawals: int = 0
    total_amount_of_cheque_withdrawals: float = 0.0
    total_fees_charged: float = 0.0

    class Config:
        from_attributes = True


class AggregatedMetricsResponse(BaseModel):
    account_holder: Optional[str] = None
    bank: Optional[str] = None
    account_number: Optional[str] = None
    currency: Optional[str] = None
    total_statements: int = 0
    period_covered: Optional[str] = None
    overall_max_eod_balance: Optional[float] = None
    overall_min_eod_balance: Optional[float] = None
    overall_avg_eod_balance: Optional[float] = None
    total_credit_transactions: int = 0
    total_credit_amount: float = 0.0
    total_debit_transactions: int = 0
    total_debit_amount: float = 0.0
    overall_avg_deposit: float = 0.0
    overall_avg_withdrawal: float = 0.0
    overall_max_debit: float = 0.0
    overall_max_credit: float = 0.0
    monthly_credit_totals: Optional[list] = None
    monthly_debit_totals: Optional[list] = None
    monthly_balances: Optional[list] = None

    class Config:
        from_attributes = True


# ─── Agent Result Schemas ─────────────────────────────────────────────────────

class AgentResultResponse(BaseModel):
    id: str
    agent_type: str
    status: str
    results: Optional[dict] = None
    summary: Optional[str] = None
    risk_level: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class CheckResult(BaseModel):
    check: str
    status: str  # pass, fail, warning
    details: str
    metadata: Optional[dict] = None


# ─── Combined Response ────────────────────────────────────────────────────────

class DocumentAnalysisResponse(BaseModel):
    document: DocumentResponse
    agents: dict[str, AgentResultResponse]


class GroupAnalysisResponse(BaseModel):
    upload_group_id: str
    documents: list[DocumentAnalysisResponse]
    aggregated_metrics: Optional[AggregatedMetricsResponse] = None
