"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getResults, getMetrics } from "@/lib/api";
import { DocumentAnalysis, AgentResult, StatementMetrics } from "@/lib/types";
import {
  cn,
  formatCurrency,
  formatDateTime,
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
  Clock,
  HardDrive,
  User,
  Building,
  CreditCard,
  Calendar,
  Loader2,
  CheckCircle2,
  XCircle,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

const AGENT_CONFIG: Record<
  string,
  { icon: typeof FileText; label: string; color: string; bgColor: string; href: string; description: string }
> = {
  layout: {
    icon: FileText,
    label: "Layout Agent",
    color: "text-cyan-400",
    bgColor: "bg-cyan-500/10 border-cyan-500/20",
    href: "layout",
    description: "PDF structure analysis, bank detection & table mapping",
  },
  extraction: {
    icon: FileText,
    label: "Extraction Agent",
    color: "text-blue-400",
    bgColor: "bg-blue-500/10 border-blue-500/20",
    href: "extraction",
    description: "PDF parsing, transaction extraction & accuracy scoring",
  },
  insights: {
    icon: BarChart3,
    label: "Insights Agent",
    color: "text-purple-400",
    bgColor: "bg-purple-500/10 border-purple-500/20",
    href: "insights",
    description: "Cash flow analysis, categories, counterparties & health scoring",
  },
  tampering: {
    icon: Shield,
    label: "Tampering Agent",
    color: "text-amber-400",
    bgColor: "bg-amber-500/10 border-amber-500/20",
    href: "tampering",
    description: "PDF metadata, font, dimension & visual integrity checks",
  },
  fraud: {
    icon: AlertTriangle,
    label: "Fraud Agent",
    color: "text-red-400",
    bgColor: "bg-red-500/10 border-red-500/20",
    href: "fraud",
    description: "Transaction pattern analysis, anomaly & risk detection",
  },
};

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

  // Extract accuracy/score info
  let scoreLabel = "";
  let scoreValue = "";
  if (agentType === "extraction" && result?.results) {
    const r = result.results as Record<string, unknown>;
    // Support nested accuracy object or legacy flat keys
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
      href={isCompleted ? `/documents/${documentId}/${config.href}` : "#"}
      className={cn(
        "group relative flex flex-col rounded-xl border p-5 transition-all duration-300",
        isCompleted
          ? "border-zinc-800/50 bg-zinc-900/30 hover:border-zinc-700/50 hover:bg-zinc-900/60 cursor-pointer"
          : "border-zinc-800/30 bg-zinc-900/20 cursor-default"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg border", config.bgColor)}>
            <Icon className={cn("h-5 w-5", config.color)} />
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-200">{config.label}</p>
            <p className="text-[11px] text-zinc-500">{config.description}</p>
          </div>
        </div>
        {isCompleted && (
          <ChevronRight className="h-4 w-4 text-zinc-600 transition-transform group-hover:translate-x-1 group-hover:text-zinc-400" />
        )}
      </div>

      {/* Status & Score */}
      <div className="mt-4 flex items-center justify-between">
        {/* Status */}
        <div className="flex items-center gap-2">
          {isRunning && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />}
          {isCompleted && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />}
          {isFailed && <XCircle className="h-3.5 w-3.5 text-red-400" />}
          <span className={cn("text-xs font-medium", statusColor(result?.status || "pending"))}>
            {result?.status ? result.status.charAt(0).toUpperCase() + result.status.slice(1) : "Pending"}
          </span>
        </div>

        {/* Risk Level */}
        {result?.risk_level && (
          <span
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider",
              riskBgColor(result.risk_level),
              riskColor(result.risk_level)
            )}
          >
            {result.risk_level} risk
          </span>
        )}
      </div>

      {/* Score */}
      {scoreLabel && scoreValue && (
        <div className="mt-3 rounded-lg bg-zinc-800/30 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">{scoreLabel}</span>
            <span className="text-sm font-bold text-zinc-200">{scoreValue}</span>
          </div>
        </div>
      )}

      {/* Summary */}
      {result?.summary && (
        <p className="mt-3 text-xs leading-relaxed text-zinc-500 line-clamp-2">{result.summary}</p>
      )}
    </Link>
  );
}

export default function DocumentOverviewPage() {
  const params = useParams();
  const documentId = params.id as string;
  const [data, setData] = useState<DocumentAnalysis | null>(null);
  const [metrics, setMetrics] = useState<StatementMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;

    const fetchData = async () => {
      try {
        const [analysis, met] = await Promise.all([
          getResults(documentId),
          getMetrics(documentId).catch(() => null),
        ]);
        if (!cancelled) {
          setData(analysis);
          setMetrics(met);
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [documentId]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-zinc-400">Document not found</p>
        <Link href="/" className="text-sm text-indigo-400 hover:underline">
          ← Back to Home
        </Link>
      </div>
    );
  }

  const doc = data.document;
  const agents = data.agents;

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
              <h1 className="text-2xl font-bold text-white">{doc.original_filename}</h1>
              <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-zinc-500">
                <span className="flex items-center gap-1"><HardDrive className="h-3 w-3" />{formatFileSize(doc.file_size)}</span>
                <span className="flex items-center gap-1"><FileText className="h-3 w-3" />{doc.page_count} pages</span>
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{formatDateTime(doc.created_at)}</span>
                <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider", statusColor(doc.status), doc.status === "completed" ? "bg-emerald-500/10" : "bg-zinc-800")}>
                  {doc.status}
                </span>
              </div>
            </div>
          </div>

          {/* Account Info Bar */}
          {metrics && (
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              {[
                { icon: User, label: "Account Holder", value: metrics.account_holder },
                { icon: Building, label: "Bank", value: metrics.bank },
                { icon: CreditCard, label: "Account No", value: metrics.account_number },
                { icon: Calendar, label: "Period", value: metrics.statement_period },
                { icon: TrendingUp, label: "Opening Balance", value: formatCurrency(metrics.opening_balance, metrics.currency || "SGD") },
                { icon: TrendingDown, label: "Closing Balance", value: formatCurrency(metrics.closing_balance, metrics.currency || "SGD") },
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

      {/* Agent Cards Grid */}
      <div className="mx-auto max-w-6xl px-6 py-8">
        <h2 className="mb-4 text-lg font-semibold text-white">AI Agent Results</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {["layout", "extraction", "insights", "tampering", "fraud"].map((agentType) => (
            <AgentCard
              key={agentType}
              agentType={agentType}
              result={agents[agentType]}
              documentId={documentId}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
