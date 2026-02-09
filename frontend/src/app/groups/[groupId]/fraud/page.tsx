"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getGroupResults } from "@/lib/api";
import { GroupResults, AgentResult, FraudResults, CheckResult } from "@/lib/types";
import { cn, formatCurrency, riskColor, riskBgColor } from "@/lib/utils";
import {
  ArrowLeft,
  Loader2,
  ShieldCheck,
  AlertTriangle,
  XCircle,
  ChevronRight,
  FileText,
  Layers,
  Search,
  Flag,
  Siren,
} from "lucide-react";

// ─── Fraud Check Card ────────────────────────────────────────────────────────

function FraudCheckCard({ check }: { check: CheckResult }) {
  const isPassed = check.status?.toLowerCase() === "pass";
  const isFailed = check.status?.toLowerCase() === "fail";
  const isWarning = check.status?.toLowerCase() === "warning";
  const flaggedItems = check.flagged_items || [];

  return (
    <div
      className={cn(
        "rounded-xl border p-5 transition-all",
        isPassed
          ? "border-emerald-500/20 bg-emerald-500/5"
          : isFailed
          ? "border-red-500/20 bg-red-500/5"
          : isWarning
          ? "border-amber-500/20 bg-amber-500/5"
          : "border-zinc-800/50 bg-zinc-900/30"
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              isPassed
                ? "bg-emerald-500/10"
                : isFailed
                ? "bg-red-500/10"
                : "bg-amber-500/10"
            )}
          >
            {isPassed && <ShieldCheck className="h-4 w-4 text-emerald-400" />}
            {isFailed && <XCircle className="h-4 w-4 text-red-400" />}
            {isWarning && <AlertTriangle className="h-4 w-4 text-amber-400" />}
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-200">{check.check}</p>
            <p className="mt-1 text-xs leading-relaxed text-zinc-400">{check.details}</p>
          </div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider",
            isPassed
              ? "bg-emerald-500/10 text-emerald-400"
              : isFailed
              ? "bg-red-500/10 text-red-400"
              : "bg-amber-500/10 text-amber-400"
          )}
        >
          {check.status}
        </span>
      </div>

      {/* Flagged Items with transaction details and explanations */}
      {flaggedItems.length > 0 && (
        <div className="mt-3 space-y-2">
          {flaggedItems.slice(0, 10).map((rawItem, idx) => {
            const item = rawItem as Record<string, string | number | undefined>;
            return (
            <div key={idx} className="rounded-lg bg-zinc-800/40 border border-zinc-700/30 px-3 py-2.5">
              {/* Transaction header row */}
              <div className="flex items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  {item.date && (
                    <span className="text-zinc-500 whitespace-nowrap">{String(item.date)}</span>
                  )}
                  {item.description && (
                    <span className="text-zinc-300 truncate">{String(item.description)}</span>
                  )}
                  {item.counterparty && !item.description && (
                    <span className="text-zinc-300 truncate">{String(item.counterparty)}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {item.amount != null && (
                    <span className="font-mono text-red-400 whitespace-nowrap">
                      {formatCurrency(item.amount as number)}
                    </span>
                  )}
                  {item.type && (
                    <span className={cn(
                      "rounded px-1.5 py-0.5 text-[9px] font-bold uppercase",
                      String(item.type) === "credit" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                    )}>
                      {String(item.type)}
                    </span>
                  )}
                  {item.count != null && (
                    <span className="rounded bg-zinc-700/50 px-1.5 py-0.5 text-[9px] font-medium text-zinc-300">
                      {String(item.count)}x
                    </span>
                  )}
                </div>
              </div>
              {/* Explanation */}
              {item.explanation && (
                <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-500 border-t border-zinc-700/30 pt-1.5">
                  {String(item.explanation)}
                </p>
              )}
            </div>
            );
          })}
          {flaggedItems.length > 10 && (
            <p className="text-center text-[10px] text-zinc-600">
              + {flaggedItems.length - 10} more flagged items
            </p>
          )}
        </div>
      )}

      {/* Metadata (fallback for items without flagged_items) */}
      {check.metadata && Object.keys(check.metadata).length > 0 && flaggedItems.length === 0 && (
        <div className="mt-3 rounded-lg bg-zinc-800/30 px-3 py-2">
          <div className="flex flex-wrap gap-3">
            {Object.entries(check.metadata).map(([key, value]) => (
              <div key={key} className="text-[10px]">
                <span className="text-zinc-500">{key.replace(/_/g, " ")}: </span>
                <span className="text-zinc-300">
                  {typeof value === "number" ? value.toLocaleString() : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Per-Document Summary Card ───────────────────────────────────────────────

function DocSummaryCard({
  doc,
}: {
  doc: { document_id: string; filename: string; risk_level: string; pass_count: number; fail_count: number; warning_count: number };
}) {
  const total = doc.pass_count + doc.fail_count + doc.warning_count;
  return (
    <Link
      href={`/documents/${doc.document_id}/fraud`}
      className="group flex items-center justify-between rounded-lg border border-zinc-800/50 bg-zinc-900/30 px-4 py-3 hover:border-zinc-700/50 hover:bg-zinc-900/60 transition-all"
    >
      <div className="flex items-center gap-3 min-w-0">
        <FileText className="h-4 w-4 text-red-400 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-xs font-medium text-zinc-200 truncate">{doc.filename}</p>
          <p className="text-[10px] text-zinc-500">
            {doc.pass_count} passed · {doc.warning_count} warnings · {doc.fail_count} failed — {total} total
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider",
            riskBgColor(doc.risk_level),
            riskColor(doc.risk_level)
          )}
        >
          {doc.risk_level}
        </span>
        <ChevronRight className="h-3.5 w-3.5 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
      </div>
    </Link>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function GroupFraudPage() {
  const params = useParams();
  const groupId = params.groupId as string;
  const [loading, setLoading] = useState(true);
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
  const [perDocSummaries, setPerDocSummaries] = useState<
    { document_id: string; filename: string; risk_level: string; pass_count: number; fail_count: number; warning_count: number }[]
  >([]);

  useEffect(() => {
    if (!groupId) return;
    getGroupResults(groupId)
      .then((gr: GroupResults) => {
        const groupAgent = gr.group_agents?.fraud;
        setAgentResult(groupAgent || null);

        const summaries = gr.documents.map((da) => {
          const r = da.agents?.fraud;
          const res = (r?.results || {}) as FraudResults;
          return {
            document_id: da.document.id,
            filename: da.document.original_filename,
            risk_level: r?.risk_level || "unknown",
            pass_count: res.pass_count ?? res.passed ?? (res.checks || []).filter((c) => c.status === "pass").length,
            fail_count: res.fail_count ?? res.failed ?? (res.checks || []).filter((c) => c.status === "fail").length,
            warning_count: res.warning_count ?? res.warnings ?? (res.checks || []).filter((c) => c.status === "warning").length,
          };
        });
        setPerDocSummaries(summaries);
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

  const results = (agentResult?.results || {}) as FraudResults;
  const checks = results.checks || [];
  const flaggedTxns = results.flagged_transactions || [];
  const overallRisk = results.overall_risk || agentResult?.risk_level || "unknown";
  const passed = results.pass_count ?? results.passed ?? checks.filter((c) => c.status === "pass").length;
  const warnings = results.warning_count ?? results.warnings ?? checks.filter((c) => c.status === "warning").length;
  const failed = results.fail_count ?? results.failed ?? checks.filter((c) => c.status === "fail").length;
  const total = results.total_checks || checks.length;
  const statementsAnalyzed = (results as Record<string, unknown>).statements_analyzed as number | undefined;
  const totalTransactions = (results as Record<string, unknown>).total_transactions as number | undefined;

  const riskScore = overallRisk === "critical" ? 4 : overallRisk === "high" ? 3 : overallRisk === "medium" ? 2 : 1;

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-zinc-800/50 bg-gradient-to-b from-red-500/[0.02] to-transparent">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Link
            href={`/groups/${groupId}`}
            className="mb-4 inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to Group Overview
          </Link>

          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-500/10 border border-red-500/20">
              <AlertTriangle className="h-5 w-5 text-red-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Cross-Statement Fraud Detection</h1>
              <p className="text-sm text-zinc-500">
                <Layers className="inline h-3 w-3 mr-1" />
                Group-level transaction pattern analysis, anomaly detection & cross-statement risk scoring
                {statementsAnalyzed && totalTransactions && (
                  <span className="ml-2 text-zinc-600">
                    · {statementsAnalyzed} statements · {totalTransactions} transactions
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Summary Cards */}
        <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className={cn("rounded-xl border p-5", riskBgColor(overallRisk))}>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <Siren className="h-3 w-3" />
              Fraud Risk
            </div>
            <p className={cn("mt-2 text-2xl font-bold capitalize", riskColor(overallRisk))}>
              {overallRisk}
            </p>
          </div>

          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <ShieldCheck className="h-3 w-3 text-emerald-400" />
              Passed
            </div>
            <p className="mt-2 text-2xl font-bold text-emerald-400">{passed}/{total}</p>
          </div>

          <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <AlertTriangle className="h-3 w-3 text-amber-400" />
              Warnings
            </div>
            <p className="mt-2 text-2xl font-bold text-amber-400">{warnings}</p>
          </div>

          <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <XCircle className="h-3 w-3 text-red-400" />
              Failed
            </div>
            <p className="mt-2 text-2xl font-bold text-red-400">{failed}</p>
          </div>
        </div>

        {/* Risk Level Indicator */}
        <div className="mb-8 rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
          <h3 className="mb-4 text-sm font-semibold text-zinc-300">Risk Severity</h3>
          <div className="flex items-center gap-2">
            {[
              { level: 1, label: "Low", color: "bg-emerald-500" },
              { level: 2, label: "Medium", color: "bg-amber-500" },
              { level: 3, label: "High", color: "bg-orange-500" },
              { level: 4, label: "Critical", color: "bg-red-500" },
            ].map((item) => (
              <div key={item.level} className="flex-1">
                <div
                  className={cn(
                    "h-3 rounded-full transition-all",
                    riskScore >= item.level ? item.color : "bg-zinc-800"
                  )}
                />
                <p className={cn(
                  "mt-1 text-center text-[10px]",
                  riskScore >= item.level ? "text-zinc-300 font-medium" : "text-zinc-600"
                )}>
                  {item.label}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mb-8 rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-zinc-300">Check Results</h3>
            <span className="text-xs text-zinc-500">{passed} of {total} checks passed</span>
          </div>
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-zinc-800/50">
            <div className="bg-emerald-500 transition-all duration-500" style={{ width: `${(passed / Math.max(total, 1)) * 100}%` }} />
            <div className="bg-amber-500 transition-all duration-500" style={{ width: `${(warnings / Math.max(total, 1)) * 100}%` }} />
            <div className="bg-red-500 transition-all duration-500" style={{ width: `${(failed / Math.max(total, 1)) * 100}%` }} />
          </div>
          <div className="mt-2 flex items-center gap-4 text-[10px] text-zinc-500">
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500"></span> Passed</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-500"></span> Warning</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500"></span> Failed</span>
          </div>
        </div>

        {/* Detailed Check Results */}
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
          <Search className="h-4 w-4 text-red-400" />
          Cross-Statement Check Results ({total} checks)
        </h3>
        <div className="space-y-3 mb-8">
          {checks.map((check, i) => (
            <FraudCheckCard key={i} check={check} />
          ))}
          {checks.length === 0 && (
            <p className="text-center text-sm text-zinc-500 py-8">No group-level check results available</p>
          )}
        </div>

        {/* Flagged Transactions */}
        {flaggedTxns.length > 0 && (
          <div className="mb-8 rounded-xl border border-zinc-800/50 bg-zinc-900/30 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-zinc-800/50 px-5 py-4">
              <Flag className="h-4 w-4 text-red-400" />
              <h3 className="text-sm font-semibold text-zinc-300">Flagged Transactions ({flaggedTxns.length})</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-zinc-800/50 text-left text-[10px] uppercase tracking-wider text-zinc-500">
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Description</th>
                    <th className="px-4 py-3 text-right">Amount</th>
                    <th className="px-4 py-3">Flag</th>
                  </tr>
                </thead>
                <tbody>
                  {flaggedTxns.map((txn, i) => (
                    <tr key={i} className="border-b border-zinc-800/30 hover:bg-red-500/5 transition-colors">
                      <td className="whitespace-nowrap px-4 py-2.5 text-zinc-400">{txn.date}</td>
                      <td className="max-w-[300px] truncate px-4 py-2.5 text-zinc-300">{txn.description}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-red-400">
                        {formatCurrency(txn.amount)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-400">
                          {txn.flag}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Agent Summary */}
        {agentResult?.summary && (
          <div className="mb-8 rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <h3 className="mb-3 text-sm font-semibold text-zinc-300">Group Agent Summary</h3>
            <p className="text-sm leading-relaxed text-zinc-400 whitespace-pre-line">{agentResult.summary}</p>
          </div>
        )}

        {/* Per-Document Breakdown */}
        {perDocSummaries.length > 0 && (
          <div>
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
              <FileText className="h-4 w-4 text-red-400" />
              Per-Statement Breakdown ({perDocSummaries.length} statements)
            </h3>
            <div className="space-y-2">
              {perDocSummaries.map((doc) => (
                <DocSummaryCard key={doc.document_id} doc={doc} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
