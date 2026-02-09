"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getGroupResults,
  getGroupStatus,
  getGroupMetrics,
} from "@/lib/api";
import {
  GroupResults,
  GroupStatus,
  AggregatedMetrics,
  StatementMetrics,
  AgentResult,
} from "@/lib/types";
import {
  cn,
  formatCurrency,
  formatFileSize,
  riskColor,
  riskBgColor,
  statusColor,
} from "@/lib/utils";
import {
  ArrowLeft,
  FileText,
  BarChart3,
  Shield,
  AlertTriangle,
  ChevronRight,
  User,
  Building,
  CreditCard,
  Calendar,
  Loader2,
  CheckCircle2,
  XCircle,
  TrendingUp,
  TrendingDown,
  Layers,
  FileStack,
} from "lucide-react";

// ─── Agent Config ────────────────────────────────────────────────────────────

const AGENT_CONFIG: Record<
  string,
  { icon: typeof FileText; label: string; color: string; bgColor: string; description: string }
> = {
  extraction: {
    icon: FileText,
    label: "Extraction Agent",
    color: "text-blue-400",
    bgColor: "bg-blue-500/10 border-blue-500/20",
    description: "PDF parsing, transaction extraction & accuracy scoring",
  },
  insights: {
    icon: BarChart3,
    label: "Insights Agent",
    color: "text-purple-400",
    bgColor: "bg-purple-500/10 border-purple-500/20",
    description: "Cash flow analysis, categories, counterparties & health scoring",
  },
  tampering: {
    icon: Shield,
    label: "Tampering Agent",
    color: "text-amber-400",
    bgColor: "bg-amber-500/10 border-amber-500/20",
    description: "PDF metadata, font, dimension & visual integrity checks",
  },
  fraud: {
    icon: AlertTriangle,
    label: "Fraud Agent",
    color: "text-red-400",
    bgColor: "bg-red-500/10 border-red-500/20",
    description: "Transaction pattern analysis, anomaly & risk detection",
  },
};

// ─── Per-Document Agent Card ─────────────────────────────────────────────────

function AgentCard({
  agentType,
  result,
  documentId,
}: {
  agentType: string;
  result: AgentResult | undefined;
  documentId: string;
}) {
  const config = AGENT_CONFIG[agentType];
  if (!config) return null;
  const Icon = config.icon;
  const isCompleted = result?.status === "completed";
  const isFailed = result?.status === "failed";
  const isRunning = result?.status === "running" || result?.status === "pending";

  let scoreLabel = "";
  let scoreValue = "";
  if (agentType === "extraction" && result?.results) {
    const r = result.results as Record<string, unknown>;
    const acc = r.accuracy as Record<string, unknown> | undefined;
    const score = acc?.overall_score ?? r.accuracy_score;
    const grade = acc?.grade ?? r.accuracy_grade;
    if (score != null) {
      scoreLabel = "Accuracy";
      scoreValue = `${score}% ${grade || ""}`;
    }
  } else if ((agentType === "tampering" || agentType === "fraud") && result?.results) {
    const r = result.results as Record<string, unknown>;
    const passed = r.pass_count ?? r.passed;
    const total = r.total_checks;
    if (passed != null && total != null) {
      scoreLabel = "Checks Passed";
      scoreValue = `${passed}/${total}`;
    }
  } else if (agentType === "insights" && result?.results) {
    const r = result.results as Record<string, unknown>;
    const bh = r.business_health as Record<string, unknown> | undefined;
    if (bh?.score != null) {
      scoreLabel = "Health Score";
      scoreValue = `${bh.score}/100 ${bh.grade || bh.assessment || ""}`;
    }
  }

  return (
    <Link
      href={isCompleted ? `/documents/${documentId}/${agentType}` : "#"}
      className={cn(
        "group relative flex flex-col rounded-lg border p-3.5 transition-all duration-300",
        isCompleted
          ? "border-zinc-800/50 bg-zinc-900/30 hover:border-zinc-700/50 hover:bg-zinc-900/60 cursor-pointer"
          : "border-zinc-800/30 bg-zinc-900/20 cursor-default"
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg border", config.bgColor)}>
            <Icon className={cn("h-4 w-4", config.color)} />
          </div>
          <div>
            <p className="text-xs font-semibold text-zinc-300">{config.label}</p>
          </div>
        </div>
        {isCompleted && (
          <ChevronRight className="h-3.5 w-3.5 text-zinc-600 transition-transform group-hover:translate-x-1 group-hover:text-zinc-400" />
        )}
      </div>

      <div className="mt-2.5 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {isRunning && <Loader2 className="h-3 w-3 animate-spin text-blue-400" />}
          {isCompleted && <CheckCircle2 className="h-3 w-3 text-emerald-400" />}
          {isFailed && <XCircle className="h-3 w-3 text-red-400" />}
          <span className={cn("text-[10px] font-medium", statusColor(result?.status || "pending"))}>
            {result?.status ? result.status.charAt(0).toUpperCase() + result.status.slice(1) : "Pending"}
          </span>
        </div>
        {result?.risk_level && (
          <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider", riskBgColor(result.risk_level), riskColor(result.risk_level))}>
            {result.risk_level}
          </span>
        )}
      </div>

      {scoreLabel && scoreValue && (
        <div className="mt-2 rounded bg-zinc-800/30 px-2.5 py-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[9px] uppercase tracking-wider text-zinc-500">{scoreLabel}</span>
            <span className="text-xs font-bold text-zinc-200">{scoreValue}</span>
          </div>
        </div>
      )}
    </Link>
  );
}

// ─── Group Agent Card ────────────────────────────────────────────────────────

function GroupAgentCard({
  agentType,
  result,
  groupId,
}: {
  agentType: string;
  result: AgentResult | undefined;
  groupId: string;
}) {
  const config = AGENT_CONFIG[agentType];
  if (!config) return null;
  const Icon = config.icon;
  const isCompleted = result?.status === "completed";
  const isFailed = result?.status === "failed";
  const isRunning = result?.status === "running" || result?.status === "pending";

  const content = (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg border", config.bgColor)}>
            <Icon className={cn("h-5 w-5", config.color)} />
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-200">{config.label}</p>
            <p className="text-[10px] text-zinc-500">Cross-statement analysis</p>
          </div>
        </div>
        {isCompleted && (
          <ChevronRight className="h-4 w-4 text-zinc-600 transition-transform group-hover:translate-x-1 group-hover:text-zinc-400" />
        )}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />}
          {isCompleted && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />}
          {isFailed && <XCircle className="h-3.5 w-3.5 text-red-400" />}
          <span className={cn("text-xs font-medium", statusColor(result?.status || "pending"))}>
            {result?.status ? result.status.charAt(0).toUpperCase() + result.status.slice(1) : "Pending"}
          </span>
        </div>
        {result?.risk_level && (
          <span className={cn("rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider", riskBgColor(result.risk_level), riskColor(result.risk_level))}>
            {result.risk_level} risk
          </span>
        )}
      </div>

      {result?.summary && (
        <p className="mt-3 text-xs leading-relaxed text-zinc-500 line-clamp-3">{result.summary}</p>
      )}
    </>
  );

  if (isCompleted) {
    return (
      <Link
        href={`/groups/${groupId}/${agentType}`}
        className={cn(
          "group relative flex flex-col rounded-xl border p-5 transition-all duration-300",
          "border-zinc-800/50 bg-zinc-900/30 hover:border-zinc-700/50 hover:bg-zinc-900/60 cursor-pointer"
        )}
      >
        {content}
      </Link>
    );
  }

  return (
    <div
      className={cn(
        "relative flex flex-col rounded-xl border p-5 transition-all duration-300",
        "border-zinc-800/30 bg-zinc-900/20"
      )}
    >
      {content}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function GroupOverviewPage() {
  const params = useParams();
  const groupId = params.groupId as string;

  const [groupResults, setGroupResults] = useState<GroupResults | null>(null);
  const [groupStatus, setGroupStatus] = useState<GroupStatus | null>(null);
  const [groupMetrics, setGroupMetrics] = useState<{
    aggregated: AggregatedMetrics | null;
    per_statement: StatementMetrics[];
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!groupId) return;
    let cancelled = false;

    const fetchData = async () => {
      try {
        const [results, status, metrics] = await Promise.all([
          getGroupResults(groupId),
          getGroupStatus(groupId),
          getGroupMetrics(groupId).catch(() => null),
        ]);
        if (!cancelled) {
          setGroupResults(results);
          setGroupStatus(status);
          setGroupMetrics(metrics);
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();
    // Poll while not completed
    const interval = setInterval(fetchData, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [groupId]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  if (!groupResults || !groupStatus) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-zinc-400">Upload group not found</p>
        <Link href="/" className="text-sm text-indigo-400 hover:underline">← Back to Home</Link>
      </div>
    );
  }

  const docs = groupResults.documents;
  const isSingleDoc = docs.length === 1;
  const isAllCompleted = groupStatus.overall_status === "completed";
  const agg = groupMetrics?.aggregated;

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-zinc-800/50 bg-gradient-to-b from-indigo-500/[0.02] to-transparent">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Link href="/" className="mb-4 inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
            <ArrowLeft className="h-3 w-3" />
            Back to Documents
          </Link>

          <div className="flex items-start justify-between">
            <div>
              <div className="mb-2 flex items-center gap-2">
                <Layers className="h-5 w-5 text-indigo-400" />
                <h1 className="text-2xl font-bold text-white">
                  {isSingleDoc
                    ? docs[0].document.original_filename
                    : `Batch Analysis · ${docs.length} Statements`}
                </h1>
              </div>
              <div className="flex flex-wrap items-center gap-4 text-xs text-zinc-500">
                <span className="flex items-center gap-1">
                  <FileStack className="h-3 w-3" />
                  {docs.length} document{docs.length !== 1 ? "s" : ""}
                </span>
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                  isAllCompleted ? "bg-emerald-500/10 text-emerald-400" : "bg-blue-500/10 text-blue-400"
                )}>
                  {groupStatus.overall_status}
                </span>
                {groupStatus.overall_status === "processing" && (
                  <span className="text-blue-400">
                    {groupStatus.completed}/{groupStatus.total_documents} completed
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Aggregated Account Info */}
          {agg && (
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {[
                { icon: User, label: "Account Holder", value: agg.account_holder },
                { icon: Building, label: "Bank", value: agg.bank },
                { icon: CreditCard, label: "Account No", value: agg.account_number },
                { icon: Calendar, label: "Period", value: agg.period_covered },
                { icon: TrendingUp, label: "Total Credits", value: formatCurrency(agg.total_credit_amount, agg.currency || "SGD") },
                { icon: TrendingDown, label: "Total Debits", value: formatCurrency(agg.total_debit_amount, agg.currency || "SGD") },
              ].map((item) => (
                <div key={item.label} className="rounded-lg border border-zinc-800/50 bg-zinc-900/30 px-3 py-2.5">
                  <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 uppercase tracking-wider">
                    <item.icon className="h-3 w-3" />
                    {item.label}
                  </div>
                  <p className="mt-1 text-sm font-medium text-zinc-200 truncate">{item.value || "—"}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-6xl px-6 py-8 space-y-10">

        {/* Group-Level Agent Results (only for multi-doc uploads) */}
        {!isSingleDoc && (
          <section>
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
              <Layers className="h-5 w-5 text-indigo-400" />
              Cross-Statement Analysis
            </h2>

            {/* Extraction Summary Card */}
            <Link
              href={`/groups/${groupId}/extraction`}
              className="group mb-4 flex items-center justify-between rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5 hover:border-zinc-700/50 hover:bg-zinc-900/60 transition-all"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border bg-blue-500/10 border-blue-500/20">
                  <FileText className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-zinc-200">Extraction Summary</p>
                  <p className="text-[10px] text-zinc-500">
                    Aggregated extraction metrics across {docs.length} statements
                  </p>
                </div>
              </div>
              <ChevronRight className="h-4 w-4 text-zinc-600 transition-transform group-hover:translate-x-1 group-hover:text-zinc-400" />
            </Link>

            {/* Group Agent Cards */}
            {Object.keys(groupResults.group_agents || {}).length > 0 && (
              <div className="grid gap-4 sm:grid-cols-3">
                {["tampering", "fraud", "insights"].map((agentType) => (
                  <GroupAgentCard
                    key={agentType}
                    agentType={agentType}
                    result={groupResults.group_agents?.[agentType]}
                    groupId={groupId}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {/* Per-Document Results */}
        <section>
          <h2 className="mb-4 text-lg font-semibold text-white">
            {isSingleDoc ? "AI Agent Results" : "Per-Statement Results"}
          </h2>

          <div className="space-y-6">
            {docs.map((docAnalysis) => {
              const doc = docAnalysis.document;
              const agents = docAnalysis.agents;
              return (
                <div
                  key={doc.id}
                  className="rounded-xl border border-zinc-800/50 bg-zinc-900/10 overflow-hidden"
                >
                  {/* Document Header */}
                  <div className="flex items-center justify-between border-b border-zinc-800/30 px-5 py-3">
                    <div className="flex items-center gap-3">
                      <FileText className="h-4 w-4 text-indigo-400" />
                      <div>
                        <p className="text-sm font-medium text-zinc-200">{doc.original_filename}</p>
                        <div className="flex items-center gap-3 text-[10px] text-zinc-500">
                          <span>{formatFileSize(doc.file_size)}</span>
                          {doc.page_count && <span>{doc.page_count} pages</span>}
                        </div>
                      </div>
                    </div>
                    <span className={cn(
                      "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                      doc.status === "completed"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : doc.status === "processing"
                        ? "bg-blue-500/10 text-blue-400"
                        : "bg-red-500/10 text-red-400"
                    )}>
                      {doc.status}
                    </span>
                  </div>

                  {/* Agent Cards Grid */}
                  <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
                    {["extraction", "insights", "tampering", "fraud"].map((agentType) => (
                      <AgentCard
                        key={agentType}
                        agentType={agentType}
                        result={agents[agentType]}
                        documentId={doc.id}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
