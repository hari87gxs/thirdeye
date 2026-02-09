"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getGroupResults } from "@/lib/api";
import { GroupResults, AgentResult, TamperingResults, CheckResult } from "@/lib/types";
import { cn, riskColor, riskBgColor } from "@/lib/utils";
import {
  ArrowLeft,
  Loader2,
  Shield,
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  XCircle,
  FileSearch,
  ChevronDown,
  ChevronRight,
  FileText,
  Layers,
} from "lucide-react";

// ─── Check Card ──────────────────────────────────────────────────────────────

function CheckCard({ check }: { check: CheckResult }) {
  const [open, setOpen] = useState(check.status !== "pass");
  const icon =
    check.status === "pass" ? (
      <ShieldCheck className="h-4 w-4 text-emerald-400" />
    ) : check.status === "warning" ? (
      <AlertTriangle className="h-4 w-4 text-amber-400" />
    ) : (
      <XCircle className="h-4 w-4 text-red-400" />
    );

  const borderColor =
    check.status === "pass"
      ? "border-emerald-500/20"
      : check.status === "warning"
      ? "border-amber-500/20"
      : "border-red-500/20";

  return (
    <div className={cn("rounded-lg border bg-zinc-900/30 transition-all", borderColor)}>
      <button
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={() => setOpen(!open)}
      >
        {icon}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-zinc-200">{check.check}</p>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider",
            check.status === "pass"
              ? "bg-emerald-500/10 text-emerald-400"
              : check.status === "warning"
              ? "bg-amber-500/10 text-amber-400"
              : "bg-red-500/10 text-red-400"
          )}
        >
          {check.status}
        </span>
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-zinc-500" />
        )}
      </button>
      {open && (
        <div className="border-t border-zinc-800/50 px-4 py-3">
          <p className="text-xs leading-relaxed text-zinc-400 whitespace-pre-line">
            {check.details}
          </p>
          {check.metadata && Object.keys(check.metadata).length > 0 && (
            <div className="mt-2 space-y-1">
              {Object.entries(check.metadata).map(([key, value]) => (
                <div key={key} className="flex items-start gap-2 text-[10px]">
                  <span className="font-medium text-zinc-500 whitespace-nowrap">
                    {key.replace(/_/g, " ")}:
                  </span>
                  <span className="text-zinc-400 break-all">
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          )}
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
      href={`/documents/${doc.document_id}/tampering`}
      className="group flex items-center justify-between rounded-lg border border-zinc-800/50 bg-zinc-900/30 px-4 py-3 hover:border-zinc-700/50 hover:bg-zinc-900/60 transition-all"
    >
      <div className="flex items-center gap-3 min-w-0">
        <FileText className="h-4 w-4 text-amber-400 flex-shrink-0" />
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

export default function GroupTamperingPage() {
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
        const groupAgent = gr.group_agents?.tampering;
        setAgentResult(groupAgent || null);

        // Build per-doc summaries from individual agent results
        const summaries = gr.documents.map((da) => {
          const r = da.agents?.tampering;
          const res = (r?.results || {}) as TamperingResults;
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

  const results = (agentResult?.results || {}) as TamperingResults;
  const checks = results.checks || [];
  const overallRisk = results.overall_risk || agentResult?.risk_level || "unknown";
  const passed = results.pass_count ?? results.passed ?? checks.filter((c) => c.status === "pass").length;
  const warnings = results.warning_count ?? results.warnings ?? checks.filter((c) => c.status === "warning").length;
  const failed = results.fail_count ?? results.failed ?? checks.filter((c) => c.status === "fail").length;
  const total = results.total_checks || checks.length;

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-zinc-800/50 bg-gradient-to-b from-amber-500/[0.02] to-transparent">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Link
            href={`/groups/${groupId}`}
            className="mb-4 inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to Group Overview
          </Link>

          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20">
              <Shield className="h-5 w-5 text-amber-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Cross-Statement Tampering Detection</h1>
              <p className="text-sm text-zinc-500">
                <Layers className="inline h-3 w-3 mr-1" />
                Group-level PDF integrity, consistency & cross-document tampering checks
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
              <ShieldAlert className="h-3 w-3" />
              Overall Risk
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
          <FileSearch className="h-4 w-4 text-amber-400" />
          Cross-Statement Check Results ({total} checks)
        </h3>
        <div className="space-y-3 mb-8">
          {checks.map((check, i) => (
            <CheckCard key={i} check={check} />
          ))}
          {checks.length === 0 && (
            <p className="text-center text-sm text-zinc-500 py-8">No group-level check results available</p>
          )}
        </div>

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
              <FileText className="h-4 w-4 text-amber-400" />
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
