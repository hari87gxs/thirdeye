// ─── Document Types ──────────────────────────────────────────────────────────

export interface DocumentResponse {
  id: string;
  filename: string;
  original_filename: string;
  file_size: number | null;
  page_count: number | null;
  status: string;
  upload_group_id: string | null;
  created_at: string;
}

export interface UploadResponse {
  upload_group_id: string;
  documents: DocumentResponse[];
  message: string;
}

// ─── Transaction Types ───────────────────────────────────────────────────────

export interface Transaction {
  id: string;
  date: string | null;
  description: string | null;
  transaction_type: string | null;
  amount: number | null;
  balance: number | null;
  reference: string | null;
  category: string | null;
  counterparty: string | null;
  channel: string | null;
  is_cash: boolean;
  is_cheque: boolean;
  page_number: number | null;
}

export interface TransactionsResponse {
  total: number;
  limit: number;
  offset: number;
  transactions: Transaction[];
}

// ─── Metrics Types ───────────────────────────────────────────────────────────

export interface StatementMetrics {
  account_holder: string | null;
  bank: string | null;
  account_number: string | null;
  currency: string | null;
  statement_period: string | null;
  months_of_statement: string | null;
  opening_balance: number | null;
  closing_balance: number | null;
  max_eod_balance: number | null;
  min_eod_balance: number | null;
  avg_eod_balance: number | null;
  total_no_of_credit_transactions: number;
  total_amount_of_credit_transactions: number;
  total_no_of_debit_transactions: number;
  total_amount_of_debit_transactions: number;
  average_deposit: number;
  average_withdrawal: number;
  max_debit_transaction: number;
  min_debit_transaction: number;
  max_credit_transaction: number;
  min_credit_transaction: number;
  total_no_of_cash_deposits: number;
  total_amount_of_cash_deposits: number;
  total_no_of_cash_withdrawals: number;
  total_amount_of_cash_withdrawals: number;
  total_no_of_cheque_withdrawals: number;
  total_amount_of_cheque_withdrawals: number;
  total_fees_charged: number;
}

// ─── Agent Result Types ──────────────────────────────────────────────────────

export interface AgentResult {
  id: string;
  agent_type: string;
  status: string;
  results: Record<string, unknown> | null;
  summary: string | null;
  risk_level: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

// ─── Combined Types ──────────────────────────────────────────────────────────

export interface DocumentAnalysis {
  document: DocumentResponse;
  agents: Record<string, AgentResult>;
}

// ─── Check Result Type ───────────────────────────────────────────────────────

export interface CheckResult {
  check: string;
  status: string; // pass, fail, warning
  details: string;
  metadata?: Record<string, unknown>;
}

// ─── Extraction Results Shape ────────────────────────────────────────────────

export interface ExtractionAccuracy {
  overall_score: number;
  grade: string;
  breakdown?: Record<string, { value: number; weight: number }>;
  balance_chain_detail?: {
    total_checked: number;
    valid: number;
    invalid: number;
    chain_accuracy_pct: number;
    breaks: unknown[];
    sections?: number;
  };
}

export interface ExtractionResults {
  extraction_method?: string;
  transaction_count?: number;
  pages_processed?: number;
  accuracy?: ExtractionAccuracy;
  account_info?: {
    account_holder?: string;
    bank?: string;
    account_number?: string;
    currency?: string;
    statement_period?: string;
    account_type?: string;
  };
  metrics?: Record<string, unknown>;
  // Legacy flat keys (keep for backward compat)
  accuracy_score?: number;
  accuracy_grade?: string;
  total_transactions?: number;
  balance_chain_valid?: boolean;
  balance_chain_breaks?: number;
}

// ─── Insights Results Shape ──────────────────────────────────────────────────

export interface CategoryItem {
  category: string;
  label: string;
  count: number;
  total: number;
  percentage: number;
}

export interface InsightsResults {
  category_breakdown?: {
    debit_categories?: CategoryItem[];
    credit_categories?: CategoryItem[];
    total_debit_amount?: number;
    total_credit_amount?: number;
    top_debit_category?: string;
    top_credit_category?: string;
    debit_category_count?: number;
    credit_category_count?: number;
  } | Record<string, { count: number; total: number }>;
  cash_flow?: {
    total_inflow: number;
    total_outflow: number;
    net_flow: number;
    net_flow_direction?: string;
    burn_rate?: number;
    peak_inflow_day?: unknown;
    peak_outflow_day?: unknown;
    monthly_flows?: Array<{ month: string; inflow: number; outflow: number; net: number }>;
    weekly_breakdown?: Array<{ week: string; inflow: number; outflow: number; net: number }>;
    daily_flow?: Array<{ day: number; inflow: number; outflow: number; net: number }>;
  };
  top_counterparties?: {
    by_credit?: Array<{ name: string; count: number; total: number }>;
    by_debit?: Array<{ name: string; count: number; total: number }>;
    top_vendors?: Array<{ name: string; count: number; total: number }>;
    top_customers?: Array<{ name: string; count: number; total: number }>;
    recurring_vendors?: unknown[];
    unique_vendor_count?: number;
    unique_customer_count?: number;
  };
  unusual_transactions?: {
    large_transactions?: Array<{ type: string; date: string; description: string; amount: number; reason: string }>;
    round_number_transactions?: Array<{ type: string; date: string; description: string; amount: number; transaction_type?: string }>;
    same_day_large_movements?: Array<{ type: string; date: string; credits: number; debits: number; reason: string }>;
    low_balance_events?: Array<{ type: string; date: string; balance: number; description: string }>;
    total_flags?: number;
  } | Array<{ date: string; description: string; amount: number; reason: string }>;
  day_of_week_patterns?: Record<string, number>;
  day_of_month_patterns?: {
    daily_pattern?: Array<{ day: number; count: number }> | Record<string, unknown>;
    busiest_day?: unknown;
    quietest_day?: unknown;
    highest_value_day?: unknown;
    active_days?: number;
  };
  channel_analysis?: {
    channels?: Array<{ channel: string; count: number; total: number; percentage: number }>;
    dominant_channel?: string;
    total_channels?: number;
  } | Record<string, number>;
  business_health?: {
    score: number;
    grade?: string;
    assessment?: string;
    factors?: Array<{ factor: string; impact: string; details: string }>;
    indicators?: Record<string, unknown> | Array<{ factor: string; impact: string; details: string }>;
  };
  narrative?: string | {
    executive_summary?: string;
    spending_analysis?: string;
    income_analysis?: string;
    cash_flow_assessment?: string;
    risk_observations?: string;
    recommendations?: string[] | string;
  };
}

// ─── Tampering Results Shape ─────────────────────────────────────────────────

export interface TamperingResults {
  checks?: CheckResult[];
  overall_risk?: string;
  risk_score?: number;
  total_checks?: number;
  passed?: number;
  pass_count?: number;
  warnings?: number;
  warning_count?: number;
  failed?: number;
  fail_count?: number;
}

// ─── Fraud Results Shape ─────────────────────────────────────────────────────

export interface FraudResults {
  checks?: CheckResult[];
  overall_risk?: string;
  risk_score?: number;
  total_checks?: number;
  passed?: number;
  pass_count?: number;
  warnings?: number;
  warning_count?: number;
  failed?: number;
  fail_count?: number;
  flagged_transactions?: Array<{
    date: string;
    description: string;
    amount: number;
    flag: string;
  }>;
}
