"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAgentResult } from "@/lib/api";
import { AgentResult, TamperingResults, CheckResult } from "@/lib/types";
import { cn, riskColor, riskBgColor } from "@/lib/utils";
import {
  ArrowLeft,
  Shield,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileSearch,
  ShieldCheck,
  ShieldAlert,
  Info,
} from "lucide-react";

function CheckCard({ check }: { check: CheckResult }) {
  const isPassed = check.status?.toLowerCase() === "pass";
  const isFailed = check.status?.toLowerCase() === "fail";
  const isWarning = check.status?.toLowerCase() === "warning";

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
            {isPassed && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
            {isFailed && <XCircle className="h-4 w-4 text-red-400" />}
            {isWarning && <AlertTriangle className="h-4 w-4 text-amber-400" />}
            {!isPassed && !isFailed && !isWarning && <Info className="h-4 w-4 text-zinc-400" />}
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

      {/* Metadata */}
      {check.metadata && Object.keys(check.metadata).length > 0 && (
        <div className="mt-3 rounded-lg bg-zinc-800/30 px-3 py-2">
          <div className="flex flex-wrap gap-3">
            {Object.entries(check.metadata).map(([key, value]) => (
              <div key={key} className="text-[10px]">
                <span className="text-zinc-500">{key.replace(/_/g, " ")}: </span>
                <span className="text-zinc-300">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function TamperingPage() {
  const params = useParams();
  const documentId = params.id as string;
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!documentId) return;
    getAgentResult(documentId, "tampering")
      .then((r) => {
        setAgentResult(r);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [documentId]);

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
            href={`/documents/${documentId}`}
            className="mb-4 inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to Overview
          </Link>

          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20">
              <Shield className="h-5 w-5 text-amber-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Tampering Detection Agent</h1>
              <p className="text-sm text-zinc-500">
                PDF metadata integrity, font consistency, visual tampering & structural checks
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Summary Cards */}
        <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {/* Overall Risk */}
          <div className={cn("rounded-xl border p-5", riskBgColor(overallRisk))}>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <ShieldAlert className="h-3 w-3" />
              Overall Risk
            </div>
            <p className={cn("mt-2 text-2xl font-bold capitalize", riskColor(overallRisk))}>
              {overallRisk}
            </p>
          </div>

          {/* Passed */}
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <ShieldCheck className="h-3 w-3 text-emerald-400" />
              Passed
            </div>
            <p className="mt-2 text-2xl font-bold text-emerald-400">{passed}/{total}</p>
          </div>

          {/* Warnings */}
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
              <AlertTriangle className="h-3 w-3 text-amber-400" />
              Warnings
            </div>
            <p className="mt-2 text-2xl font-bold text-amber-400">{warnings}</p>
          </div>

          {/* Failed */}
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
            <div
              className="bg-emerald-500 transition-all duration-500"
              style={{ width: `${(passed / Math.max(total, 1)) * 100}%` }}
            />
            <div
              className="bg-amber-500 transition-all duration-500"
              style={{ width: `${(warnings / Math.max(total, 1)) * 100}%` }}
            />
            <div
              className="bg-red-500 transition-all duration-500"
              style={{ width: `${(failed / Math.max(total, 1)) * 100}%` }}
            />
          </div>
          <div className="mt-2 flex items-center gap-4 text-[10px] text-zinc-500">
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500"></span> Passed</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-500"></span> Warning</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500"></span> Failed</span>
          </div>
        </div>

        {/* Individual Checks */}
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
          <FileSearch className="h-4 w-4 text-amber-400" />
          Detailed Check Results ({total} checks)
        </h3>
        <div className="space-y-3">
          {checks.map((check, i) => (
            <CheckCard key={i} check={check} />
          ))}
          {checks.length === 0 && (
            <p className="text-center text-sm text-zinc-500 py-8">No check results available</p>
          )}
        </div>

        {/* Summary */}
        {agentResult?.summary && (
          <div className="mt-8 rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <h3 className="mb-3 text-sm font-semibold text-zinc-300">Agent Summary</h3>
            <p className="text-sm leading-relaxed text-zinc-400 whitespace-pre-line">{agentResult.summary}</p>
          </div>
        )}
      </div>
    </div>
  );
}
