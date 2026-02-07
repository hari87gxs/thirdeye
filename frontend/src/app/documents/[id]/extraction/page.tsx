"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAgentResult, getTransactions, getMetrics } from "@/lib/api";
import { AgentResult, Transaction, StatementMetrics, ExtractionResults } from "@/lib/types";
import {
  cn,
  formatCurrency,
  formatNumber,
  gradeFromScore,
} from "@/lib/utils";
import {
  ArrowLeft,
  FileText,
  CheckCircle2,
  XCircle,
  TrendingUp,
  TrendingDown,
  Loader2,
  Database,
  Target,
  Link2,
  Layers,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";

const PAGE_SIZE = 50;

export default function ExtractionPage() {
  const params = useParams();
  const documentId = params.id as string;
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [metrics, setMetrics] = useState<StatementMetrics | null>(null);
  const [totalTxns, setTotalTxns] = useState(0);
  const [page, setPage] = useState(0);
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!documentId) return;
    Promise.all([
      getAgentResult(documentId, "extraction"),
      getMetrics(documentId).catch(() => null),
    ]).then(([result, met]) => {
      setAgentResult(result);
      setMetrics(met);
      setLoading(false);
    });
  }, [documentId]);

  useEffect(() => {
    if (!documentId) return;
    getTransactions(documentId, {
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      transaction_type: typeFilter || undefined,
    }).then((res) => {
      setTransactions(res.transactions);
      setTotalTxns(res.total);
    });
  }, [documentId, page, typeFilter]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  const results = (agentResult?.results || {}) as ExtractionResults;
  // Support both nested accuracy object and legacy flat keys
  const accuracyObj = results.accuracy;
  const accuracy = accuracyObj?.overall_score ?? results.accuracy_score ?? 0;
  const accuracyGrade = accuracyObj?.grade ?? results.accuracy_grade;
  const grade = accuracyGrade ? { grade: accuracyGrade, color: gradeFromScore(accuracy).color } : gradeFromScore(accuracy);
  const totalTxnCount = results.transaction_count ?? results.total_transactions;
  const chainDetail = accuracyObj?.balance_chain_detail;
  const balanceChainValid = chainDetail ? chainDetail.invalid === 0 : results.balance_chain_valid;
  const balanceChainBreaks = chainDetail?.invalid ?? results.balance_chain_breaks ?? 0;
  const totalPages = Math.ceil(totalTxns / PAGE_SIZE);

  // Build balance chart data from transactions
  const balanceData = transactions
    .filter((t) => t.balance != null)
    .map((t, i) => ({
      index: i,
      date: t.date || `#${i + 1}`,
      balance: t.balance!,
      type: t.transaction_type,
    }));

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-zinc-800/50 bg-gradient-to-b from-blue-500/[0.02] to-transparent">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Link
            href={`/documents/${documentId}`}
            className="mb-4 inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to Overview
          </Link>

          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 border border-blue-500/20">
              <FileText className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Extraction Agent</h1>
              <p className="text-sm text-zinc-500">
                PDF parsing, transaction extraction & accuracy validation
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Score Cards Row */}
        <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {/* Accuracy Score */}
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Target className="h-3 w-3" />
              Accuracy Score
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className={cn("text-3xl font-bold", grade.color)}>{accuracy.toFixed(1)}%</span>
              <span className={cn("text-lg font-bold", grade.color)}>{grade.grade}</span>
            </div>
          </div>

          {/* Total Transactions */}
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Database className="h-3 w-3" />
              Transactions
            </div>
            <p className="mt-2 text-3xl font-bold text-zinc-200">
              {formatNumber(totalTxnCount)}
            </p>
          </div>

          {/* Balance Chain */}
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Link2 className="h-3 w-3" />
              Balance Chain
            </div>
            <div className="mt-2 flex items-center gap-2">
              {balanceChainValid ? (
                <CheckCircle2 className="h-5 w-5 text-emerald-400" />
              ) : (
                <XCircle className="h-5 w-5 text-red-400" />
              )}
              <span className={cn("text-sm font-semibold", balanceChainValid ? "text-emerald-400" : "text-red-400")}>
                {balanceChainValid ? "Valid" : `${balanceChainBreaks} breaks`}
              </span>
            </div>
          </div>

          {/* Extraction Method */}
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Layers className="h-3 w-3" />
              Method
            </div>
            <p className="mt-2 text-sm font-semibold text-zinc-200 capitalize">
              {results.extraction_method || "—"}
            </p>
          </div>
        </div>

        {/* Metrics Summary */}
        {metrics && (
          <div className="mb-8">
            <h3 className="mb-3 text-sm font-semibold text-zinc-300">Statement Summary</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {[
                { label: "Credits", count: metrics.total_no_of_credit_transactions, amount: metrics.total_amount_of_credit_transactions, icon: TrendingUp, color: "text-emerald-400" },
                { label: "Debits", count: metrics.total_no_of_debit_transactions, amount: metrics.total_amount_of_debit_transactions, icon: TrendingDown, color: "text-red-400" },
                { label: "Avg Deposit", count: null, amount: metrics.average_deposit, icon: TrendingUp, color: "text-emerald-400" },
                { label: "Avg Withdrawal", count: null, amount: metrics.average_withdrawal, icon: TrendingDown, color: "text-red-400" },
              ].map((item) => (
                <div key={item.label} className="rounded-lg border border-zinc-800/50 bg-zinc-900/30 px-4 py-3">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-500">
                    <item.icon className={cn("h-3 w-3", item.color)} />
                    {item.label}
                  </div>
                  <p className={cn("mt-1 text-lg font-bold", item.color)}>
                    {formatCurrency(item.amount, metrics.currency || "SGD")}
                  </p>
                  {item.count != null && (
                    <p className="text-[10px] text-zinc-500">{item.count} transactions</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Balance Chart */}
        {balanceData.length > 0 && (
          <div className="mb-8 rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <h3 className="mb-4 text-sm font-semibold text-zinc-300">Balance Progression</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={balanceData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: "#71717a" }}
                    interval={Math.max(Math.floor(balanceData.length / 10), 0)}
                    axisLine={{ stroke: "#27272a" }}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: "#71717a" }}
                    axisLine={{ stroke: "#27272a" }}
                    tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#111118", border: "1px solid #27272a", borderRadius: "8px", fontSize: 12 }}
                    labelStyle={{ color: "#a1a1aa" }}
                    formatter={(value) => [formatCurrency(value as number), "Balance"]}
                  />
                  <Bar dataKey="balance" radius={[2, 2, 0, 0]}>
                    {balanceData.map((entry, i) => (
                      <Cell key={i} fill={entry.balance >= 0 ? "#6366f1" : "#ef4444"} fillOpacity={0.7} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Transaction Table */}
        <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 overflow-hidden">
          <div className="flex items-center justify-between border-b border-zinc-800/50 px-5 py-4">
            <h3 className="text-sm font-semibold text-zinc-300">
              Transactions ({formatNumber(totalTxns)})
            </h3>
            <div className="flex items-center gap-2">
              <select
                value={typeFilter}
                onChange={(e) => {
                  setTypeFilter(e.target.value);
                  setPage(0);
                }}
                className="rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 outline-none"
              >
                <option value="">All Types</option>
                <option value="credit">Credits</option>
                <option value="debit">Debits</option>
              </select>
              <div className="flex items-center gap-1 text-xs text-zinc-500">
                <ArrowUpDown className="h-3 w-3" />
                Page {page + 1} of {totalPages || 1}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800/50 text-left text-[10px] uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3 text-right">Amount</th>
                  <th className="px-4 py-3 text-right">Balance</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">Channel</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((txn) => (
                  <tr key={txn.id} className="border-b border-zinc-800/30 hover:bg-zinc-800/20 transition-colors">
                    <td className="whitespace-nowrap px-4 py-2.5 text-zinc-400">{txn.date || "—"}</td>
                    <td className="max-w-[250px] truncate px-4 py-2.5 text-zinc-300">{txn.description || "—"}</td>
                    <td className="px-4 py-2.5">
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                          txn.transaction_type === "credit"
                            ? "bg-emerald-500/10 text-emerald-400"
                            : "bg-red-500/10 text-red-400"
                        )}
                      >
                        {txn.transaction_type || "—"}
                      </span>
                    </td>
                    <td className={cn("whitespace-nowrap px-4 py-2.5 text-right font-mono", txn.transaction_type === "credit" ? "text-emerald-400" : "text-red-400")}>
                      {txn.amount != null ? formatCurrency(txn.amount) : "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-zinc-300">
                      {txn.balance != null ? formatCurrency(txn.balance) : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-zinc-500">{txn.category || "—"}</td>
                    <td className="px-4 py-2.5 text-zinc-500">{txn.channel || "—"}</td>
                  </tr>
                ))}
                {transactions.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-zinc-500">No transactions found</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-zinc-800/50 px-5 py-3">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 disabled:opacity-30"
              >
                <ChevronLeft className="h-3 w-3" /> Previous
              </button>
              <div className="flex gap-1">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  const p = page < 3 ? i : page - 2 + i;
                  if (p >= totalPages) return null;
                  return (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={cn(
                        "h-7 w-7 rounded text-xs",
                        p === page ? "bg-indigo-600 text-white" : "text-zinc-400 hover:bg-zinc-800"
                      )}
                    >
                      {p + 1}
                    </button>
                  );
                })}
              </div>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 disabled:opacity-30"
              >
                Next <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
