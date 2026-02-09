"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getGroupResults, getGroupMetrics } from "@/lib/api";
import {
  GroupResults,
  ExtractionResults,
  StatementMetrics,
  AggregatedMetrics,
} from "@/lib/types";
import { cn, formatCurrency, formatNumber } from "@/lib/utils";
import {
  ArrowLeft,
  Loader2,
  FileText,
  Target,
  Database,
  Link2,
  Layers,
  CheckCircle2,
  XCircle,
  ChevronRight,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

// ─── Grade helper ────────────────────────────────────────────────────────────

function getGrade(score: number): { grade: string; color: string } {
  if (score >= 95) return { grade: "A+", color: "text-emerald-400" };
  if (score >= 90) return { grade: "A", color: "text-emerald-400" };
  if (score >= 85) return { grade: "B+", color: "text-green-400" };
  if (score >= 80) return { grade: "B", color: "text-green-400" };
  if (score >= 70) return { grade: "C", color: "text-amber-400" };
  if (score >= 60) return { grade: "D", color: "text-orange-400" };
  return { grade: "F", color: "text-red-400" };
}

// ─── Per-Document Extraction Row ─────────────────────────────────────────────

interface DocExtraction {
  document_id: string;
  filename: string;
  accuracy: number;
  grade: string;
  gradeColor: string;
  txnCount: number;
  balanceChainValid: boolean;
  method: string;
}

function DocExtractionRow({ doc }: { doc: DocExtraction }) {
  return (
    <Link
      href={`/documents/${doc.document_id}/extraction`}
      className="group flex items-center gap-4 rounded-lg border border-zinc-800/50 bg-zinc-900/30 px-4 py-3 hover:border-zinc-700/50 hover:bg-zinc-900/60 transition-all"
    >
      <FileText className="h-4 w-4 text-blue-400 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-zinc-200 truncate">{doc.filename}</p>
        <p className="text-[10px] text-zinc-500">
          {doc.method} · {formatNumber(doc.txnCount)} transactions
        </p>
      </div>
      <div className="flex items-center gap-4 flex-shrink-0">
        <div className="text-right">
          <span className={cn("text-sm font-bold", doc.gradeColor)}>{doc.accuracy.toFixed(1)}%</span>
          <span className={cn("ml-1 text-xs font-bold", doc.gradeColor)}>{doc.grade}</span>
        </div>
        <div className="flex items-center gap-1">
          {doc.balanceChainValid ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-red-400" />
          )}
          <span className={cn("text-[10px]", doc.balanceChainValid ? "text-emerald-400" : "text-red-400")}>
            Chain
          </span>
        </div>
        <ChevronRight className="h-3.5 w-3.5 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
      </div>
    </Link>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function GroupExtractionPage() {
  const params = useParams();
  const groupId = params.groupId as string;
  const [loading, setLoading] = useState(true);
  const [docExtractions, setDocExtractions] = useState<DocExtraction[]>([]);
  const [aggMetrics, setAggMetrics] = useState<AggregatedMetrics | null>(null);
  const [perStatementMetrics, setPerStatementMetrics] = useState<StatementMetrics[]>([]);

  useEffect(() => {
    if (!groupId) return;
    Promise.all([
      getGroupResults(groupId),
      getGroupMetrics(groupId).catch(() => null),
    ])
      .then(([gr, metrics]: [GroupResults, { aggregated: AggregatedMetrics | null; per_statement: StatementMetrics[] } | null]) => {
        const extractions = gr.documents.map((da) => {
          const r = da.agents?.extraction;
          const res = (r?.results || {}) as ExtractionResults;
          const acc = res.accuracy?.overall_score ?? res.accuracy_score ?? 0;
          const g = res.accuracy?.grade ?? res.accuracy_grade ?? getGrade(acc).grade;
          const color = getGrade(acc).color;
          return {
            document_id: da.document.id,
            filename: da.document.original_filename,
            accuracy: acc,
            grade: g,
            gradeColor: color,
            txnCount: res.transaction_count ?? res.total_transactions ?? 0,
            balanceChainValid: res.balance_chain_valid ?? (res.accuracy?.balance_chain_detail ? res.accuracy.balance_chain_detail.invalid === 0 : true),
            method: res.extraction_method || "—",
          };
        });
        setDocExtractions(extractions);
        if (metrics) {
          setAggMetrics(metrics.aggregated);
          setPerStatementMetrics(metrics.per_statement);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [groupId]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  const totalTxns = docExtractions.reduce((s, d) => s + d.txnCount, 0);
  const avgAccuracy =
    docExtractions.length > 0
      ? docExtractions.reduce((s, d) => s + d.accuracy, 0) / docExtractions.length
      : 0;
  const allChainsValid = docExtractions.every((d) => d.balanceChainValid);
  const avgGrade = getGrade(avgAccuracy);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-zinc-800/50 bg-gradient-to-b from-blue-500/[0.02] to-transparent">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Link
            href={`/groups/${groupId}`}
            className="mb-4 inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to Group Overview
          </Link>

          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 border border-blue-500/20">
              <FileText className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Extraction Summary</h1>
              <p className="text-sm text-zinc-500">
                <Layers className="inline h-3 w-3 mr-1" />
                Across {docExtractions.length} statements · {formatNumber(totalTxns)} total transactions
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-8 space-y-8">

        {/* Summary Cards */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Target className="h-3 w-3" />
              Avg Accuracy
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className={cn("text-3xl font-bold", avgGrade.color)}>{avgAccuracy.toFixed(1)}%</span>
              <span className={cn("text-lg font-bold", avgGrade.color)}>{avgGrade.grade}</span>
            </div>
          </div>

          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Database className="h-3 w-3" />
              Total Transactions
            </div>
            <p className="mt-2 text-3xl font-bold text-zinc-200">{formatNumber(totalTxns)}</p>
          </div>

          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Layers className="h-3 w-3" />
              Statements
            </div>
            <p className="mt-2 text-3xl font-bold text-zinc-200">{docExtractions.length}</p>
          </div>

          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Link2 className="h-3 w-3" />
              Balance Chains
            </div>
            <div className="mt-2 flex items-center gap-2">
              {allChainsValid ? (
                <CheckCircle2 className="h-5 w-5 text-emerald-400" />
              ) : (
                <XCircle className="h-5 w-5 text-red-400" />
              )}
              <span className={cn("text-sm font-semibold", allChainsValid ? "text-emerald-400" : "text-red-400")}>
                {allChainsValid ? "All Valid" : `${docExtractions.filter((d) => !d.balanceChainValid).length} broken`}
              </span>
            </div>
          </div>
        </div>

        {/* Aggregated Metrics */}
        {aggMetrics && (
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
              <Layers className="h-4 w-4 text-blue-400" />
              Aggregated Statement Metrics
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {[
                { label: "Total Credits", amount: aggMetrics.total_credit_amount, count: aggMetrics.total_credit_transactions, icon: TrendingUp, color: "text-emerald-400" },
                { label: "Total Debits", amount: aggMetrics.total_debit_amount, count: aggMetrics.total_debit_transactions, icon: TrendingDown, color: "text-red-400" },
                { label: "Avg Deposit", amount: aggMetrics.overall_avg_deposit, count: null, icon: TrendingUp, color: "text-emerald-400" },
                { label: "Avg Withdrawal", amount: aggMetrics.overall_avg_withdrawal, count: null, icon: TrendingDown, color: "text-red-400" },
                { label: "Max EOD Balance", amount: aggMetrics.overall_max_eod_balance, count: null, icon: TrendingUp, color: "text-indigo-400" },
                { label: "Min EOD Balance", amount: aggMetrics.overall_min_eod_balance, count: null, icon: TrendingDown, color: "text-amber-400" },
                { label: "Avg EOD Balance", amount: aggMetrics.overall_avg_eod_balance, count: null, icon: Database, color: "text-zinc-300" },
                { label: "Max Credit", amount: aggMetrics.overall_max_credit, count: null, icon: TrendingUp, color: "text-emerald-400" },
              ].map((item) => (
                <div key={item.label} className="rounded-lg border border-zinc-800/50 bg-zinc-900/30 px-4 py-3">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-500">
                    <item.icon className={cn("h-3 w-3", item.color)} />
                    {item.label}
                  </div>
                  <p className={cn("mt-1 text-lg font-bold", item.color)}>
                    {formatCurrency(item.amount, aggMetrics.currency || "SGD")}
                  </p>
                  {item.count != null && (
                    <p className="text-[10px] text-zinc-500">{item.count} transactions</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Per-Document Extraction Results */}
        <div>
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
            <FileText className="h-4 w-4 text-blue-400" />
            Per-Statement Extraction Results
          </h3>
          <div className="space-y-2">
            {docExtractions.map((doc) => (
              <DocExtractionRow key={doc.document_id} doc={doc} />
            ))}
          </div>
        </div>

        {/* Per-Statement Metrics Table */}
        {perStatementMetrics.length > 0 && (
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-zinc-800/50 px-5 py-4">
              <Database className="h-4 w-4 text-blue-400" />
              <h3 className="text-sm font-semibold text-zinc-300">Per-Statement Financial Summary</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-zinc-800/50 text-left text-[10px] uppercase tracking-wider text-zinc-500">
                    <th className="px-4 py-3">Period</th>
                    <th className="px-4 py-3">Bank</th>
                    <th className="px-4 py-3 text-right">Opening</th>
                    <th className="px-4 py-3 text-right">Closing</th>
                    <th className="px-4 py-3 text-right">Credits</th>
                    <th className="px-4 py-3 text-right">Debits</th>
                    <th className="px-4 py-3 text-right">Credit Txns</th>
                    <th className="px-4 py-3 text-right">Debit Txns</th>
                  </tr>
                </thead>
                <tbody>
                  {perStatementMetrics.map((m, i) => (
                    <tr key={i} className="border-b border-zinc-800/30 hover:bg-zinc-800/20 transition-colors">
                      <td className="whitespace-nowrap px-4 py-2.5 text-zinc-300 font-medium">{m.statement_period || "—"}</td>
                      <td className="px-4 py-2.5 text-zinc-400">{m.bank || "—"}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-zinc-300">
                        {formatCurrency(m.opening_balance, m.currency || "SGD")}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-zinc-300">
                        {formatCurrency(m.closing_balance, m.currency || "SGD")}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-emerald-400">
                        {formatCurrency(m.total_amount_of_credit_transactions, m.currency || "SGD")}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-red-400">
                        {formatCurrency(m.total_amount_of_debit_transactions, m.currency || "SGD")}
                      </td>
                      <td className="px-4 py-2.5 text-right text-zinc-500">{m.total_no_of_credit_transactions}</td>
                      <td className="px-4 py-2.5 text-right text-zinc-500">{m.total_no_of_debit_transactions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
