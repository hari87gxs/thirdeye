import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer, Text, DateTime, ForeignKey,
    JSON, Boolean, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from database import Base
import enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentType(str, enum.Enum):
    LAYOUT = "layout"
    EXTRACTION = "extraction"
    INSIGHTS = "insights"
    TAMPERING = "tampering"
    FRAUD = "fraud"


class AgentStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CheckStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    ERROR = "error"


# ─── Helper ───────────────────────────────────────────────────────────────────

def generate_uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    """Application user."""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")


class Document(Base):
    """Uploaded PDF document metadata."""
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)  # bytes
    page_count = Column(Integer)
    status = Column(String, default=DocumentStatus.UPLOADED.value)
    upload_group_id = Column(String, index=True)  # groups multiple uploads together
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    owner = relationship("User", back_populates="documents")
    raw_transactions = relationship("RawTransaction", back_populates="document", cascade="all, delete-orphan")
    statement_metrics = relationship("StatementMetrics", back_populates="document", cascade="all, delete-orphan", uselist=False)
    agent_results = relationship("AgentResult", back_populates="document", cascade="all, delete-orphan")


class RawTransaction(Base):
    """Individual transactions extracted from a bank statement."""
    __tablename__ = "raw_transactions"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    upload_group_id = Column(String, index=True)

    # Transaction data
    date = Column(String)  # Transaction date as string (formats vary by bank)
    description = Column(Text)
    transaction_type = Column(String)  # credit / debit
    amount = Column(Float)
    balance = Column(Float)  # Running balance after transaction
    reference = Column(String)  # Reference number if available
    category = Column(String)  # Auto-categorized: salary, rent, utilities, etc.
    counterparty = Column(String)  # The other party in the transaction
    channel = Column(String)  # FAST, GIRO, ATM, cheque, etc.
    is_cash = Column(Boolean, default=False)
    is_cheque = Column(Boolean, default=False)
    currency = Column(String, default="SGD")  # SGD, USD, EUR, etc.

    # Metadata
    page_number = Column(Integer)
    raw_text = Column(Text)  # Original text from PDF
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="raw_transactions")


class StatementMetrics(Base):
    """Per-statement computed metrics."""
    __tablename__ = "statement_metrics"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, unique=True, index=True)
    upload_group_id = Column(String, index=True)

    # PII / Account Info
    account_holder = Column(String)
    bank = Column(String)
    account_number = Column(String)
    currency = Column(String, default="SGD")
    statement_period = Column(String)  # e.g., "01/12/2019 - 31/12/2019"
    months_of_statement = Column(String)  # e.g., "[12/2019]"

    # Balance Info
    opening_balance = Column(Float)
    closing_balance = Column(Float)
    max_eod_balance = Column(Float)
    min_eod_balance = Column(Float)
    avg_eod_balance = Column(Float)

    # Transaction Statistics
    total_no_of_credit_transactions = Column(Integer, default=0)
    total_amount_of_credit_transactions = Column(Float, default=0.0)
    total_no_of_debit_transactions = Column(Integer, default=0)
    total_amount_of_debit_transactions = Column(Float, default=0.0)
    average_deposit = Column(Float, default=0.0)
    average_withdrawal = Column(Float, default=0.0)
    max_debit_transaction = Column(Float, default=0.0)
    min_debit_transaction = Column(Float, default=0.0)
    max_credit_transaction = Column(Float, default=0.0)
    min_credit_transaction = Column(Float, default=0.0)

    # Cash & Cheque Info
    total_no_of_cash_deposits = Column(Integer, default=0)
    total_amount_of_cash_deposits = Column(Float, default=0.0)
    total_no_of_cash_withdrawals = Column(Integer, default=0)
    total_amount_of_cash_withdrawals = Column(Float, default=0.0)
    total_no_of_cheque_withdrawals = Column(Integer, default=0)
    total_amount_of_cheque_withdrawals = Column(Float, default=0.0)

    # Fees
    total_fees_charged = Column(Float, default=0.0)

    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="statement_metrics")


class AggregatedMetrics(Base):
    """Cross-statement aggregated metrics for a group of uploaded statements."""
    __tablename__ = "aggregated_metrics"

    id = Column(String, primary_key=True, default=generate_uuid)
    upload_group_id = Column(String, unique=True, nullable=False, index=True)

    # Aggregated across all statements in the group
    account_holder = Column(String)
    bank = Column(String)
    account_number = Column(String)
    currency = Column(String, default="SGD")
    total_statements = Column(Integer, default=0)
    period_covered = Column(String)  # e.g., "Dec 2019 - Mar 2020"

    # Balance Info (across all statements)
    overall_max_eod_balance = Column(Float)
    overall_min_eod_balance = Column(Float)
    overall_avg_eod_balance = Column(Float)
    avg_opening_balance = Column(Float)
    avg_closing_balance = Column(Float)

    # Transaction Stats (across all statements)
    total_credit_transactions = Column(Integer, default=0)
    total_credit_amount = Column(Float, default=0.0)
    total_debit_transactions = Column(Integer, default=0)
    total_debit_amount = Column(Float, default=0.0)
    overall_avg_deposit = Column(Float, default=0.0)
    overall_avg_withdrawal = Column(Float, default=0.0)
    overall_max_debit = Column(Float, default=0.0)
    overall_max_credit = Column(Float, default=0.0)

    # Cash & Cheque (across all statements)
    total_cash_deposits = Column(Integer, default=0)
    total_cash_deposit_amount = Column(Float, default=0.0)
    total_cash_withdrawals = Column(Integer, default=0)
    total_cash_withdrawal_amount = Column(Float, default=0.0)
    total_cheque_withdrawals = Column(Integer, default=0)
    total_cheque_withdrawal_amount = Column(Float, default=0.0)
    total_fees = Column(Float, default=0.0)

    # Trends (stored as JSON arrays for charting)
    monthly_credit_totals = Column(JSON)  # [{month: "Dec 2019", amount: 42848.61}, ...]
    monthly_debit_totals = Column(JSON)
    monthly_balances = Column(JSON)  # [{month: "Dec 2019", opening: x, closing: y}, ...]

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AgentResult(Base):
    """Results from each agent run on a document."""
    __tablename__ = "agent_results"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    upload_group_id = Column(String, index=True)
    agent_type = Column(String, nullable=False)  # extraction, insights, tampering, fraud
    status = Column(String, default=AgentStatus.PENDING.value)

    # Results stored as JSON
    results = Column(JSON)  # Flexible JSON for each agent's output
    summary = Column(Text)  # Human-readable summary
    risk_level = Column(String)  # low, medium, high, critical

    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="agent_results")


class GroupAgentResult(Base):
    """Group-level agent results aggregated across all documents in an upload group."""
    __tablename__ = "group_agent_results"

    id = Column(String, primary_key=True, default=generate_uuid)
    upload_group_id = Column(String, nullable=False, index=True)
    agent_type = Column(String, nullable=False)  # insights, tampering, fraud
    status = Column(String, default=AgentStatus.PENDING.value)

    # Results stored as JSON
    results = Column(JSON)
    summary = Column(Text)
    risk_level = Column(String)

    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    created_at = Column(DateTime, default=utcnow)
