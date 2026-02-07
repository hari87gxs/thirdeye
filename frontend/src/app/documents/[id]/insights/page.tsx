"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAgentResult } from "@/lib/api";
import { AgentResult, InsightsResults } from "@/lib/types";
import { cn, formatCurrency } from "@/lib/utils";
import {
  ArrowLeft,
  BarChart3,
  Loader2,
  TrendingUp,
  TrendingDown,
  Heart,
  MessageSquare,
  ArrowRightLeft,
  Wallet,
  Users,
  AlertCircle,
  Calendar,
  Radio,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const COLORS = ["#6366f1", "#8b5cf6", "#a855f7", "#d946ef", "#ec4899", "#f43f5e", "#f97316", "#eab308", "#22c55e", "#06b6d4", "#3b82f6", "#64748b"];

export default function InsightsPage() {
  const params = useParams();
  const documentId = params.id as string;
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!documentId) return;
    getAgentResult(documentId, "insights").then((r) => {
      setAgentResult(r);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [documentId]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  const results = (agentResult?.results || {}) as InsightsResults;
  const cashFlow = results.cash_flow;
  const rawCategories = results.category_breakdown;
  const counterparties = results.top_counterparties;
  const rawUnusual = results.unusual_transactions;
  const rawDayPatterns = results.day_of_week_patterns || results.day_of_month_patterns;
  const rawChannels = results.channel_analysis;
  const health = results.business_health;
  const rawNarrative = results.narrative;

  // ─── Normalize narrative: could be string or object with sections ────────
  let narrativeText = "";
  const narrativeSections: { title: string; content: string }[] = [];
  if (typeof rawNarrative === "string") {
    narrativeText = rawNarrative;
  } else if (rawNarrative && typeof rawNarrative === "object") {
    const sectionOrder = ["executive_summary", "spending_analysis", "income_analysis", "cash_flow_assessment", "risk_observations", "recommendations"];
    const labelMap: Record<string, string> = {
      executive_summary: "Executive Summary",
      spending_analysis: "Spending Analysis",
      income_analysis: "Income Analysis",
      cash_flow_assessment: "Cash Flow Assessment",
      risk_observations: "Risk Observations",
      recommendations: "Recommendations",
    };
    for (const key of sectionOrder) {
      const val = (rawNarrative as Record<string, unknown>)[key];
      if (val) {
        const content = Array.isArray(val) ? val.map((v, i) => `${i + 1}. ${v}`).join("\n") : String(val);
        narrativeSections.push({ title: labelMap[key] || key, content });
      }
    }
  }

  // ─── Normalize category_breakdown: could be old {name: {count,total}} or new {debit_categories: [...]} ───
  // Merge same-label categories, keep top 5, group rest into "Other"
  let categoryData: { name: string; fullName: string; total: number; count: number }[] = [];
  if (rawCategories) {
    let rawList: { label: string; count: number; total: number }[] = [];
    if ("debit_categories" in rawCategories || "credit_categories" in rawCategories) {
      const cats = rawCategories as { debit_categories?: { label: string; count: number; total: number }[]; credit_categories?: { label: string; count: number; total: number }[] };
      rawList = [...(cats.debit_categories || []), ...(cats.credit_categories || [])];
    } else {
      rawList = Object.entries(rawCategories as Record<string, { count: number; total: number }>)
        .map(([name, data]) => ({
          label: name,
          total: typeof data === "object" ? data.total : 0,
          count: typeof data === "object" ? data.count : 0,
        }));
    }

    // Merge duplicate labels (same category appearing in debit & credit)
    const merged = new Map<string, { count: number; total: number }>();
    for (const item of rawList) {
      const key = item.label;
      const existing = merged.get(key);
      if (existing) {
        existing.count += item.count;
        existing.total += Math.abs(item.total);
      } else {
        merged.set(key, { count: item.count, total: Math.abs(item.total) });
      }
    }

    // Sort by total descending
    const sorted = Array.from(merged.entries())
      .map(([label, data]) => ({ label, ...data }))
      .sort((a, b) => b.total - a.total);

    // Keep top 5, group the rest as "Other"
    const MAX_SLICES = 5;
    const top = sorted.slice(0, MAX_SLICES);
    const rest = sorted.slice(MAX_SLICES);

    categoryData = top.map((c) => ({
      name: c.label.length > 18 ? c.label.slice(0, 18) + "…" : c.label,
      fullName: c.label,
      total: c.total,
      count: c.count,
    }));

    if (rest.length > 0) {
      const otherTotal = rest.reduce((s, c) => s + c.total, 0);
      const otherCount = rest.reduce((s, c) => s + c.count, 0);
      categoryData.push({ name: "Other", fullName: `Other (${rest.length} categories)`, total: otherTotal, count: otherCount });
    }
  }

  // ─── Normalize cash flow time series ─────────────────────────────────────
  const monthlyFlows = cashFlow?.monthly_flows || cashFlow?.weekly_breakdown || [];

  // ─── Normalize day patterns ──────────────────────────────────────────────
  let dayData: { day: string; count: number; total: number }[] = [];
  let isDayOfMonth = false;
  if (rawDayPatterns) {
    if ("daily_pattern" in (rawDayPatterns as Record<string, unknown>)) {
      // New format: {daily_pattern: [{day, transaction_count, total_amount}], ...}
      isDayOfMonth = true;
      const dp = (rawDayPatterns as { daily_pattern?: { day: number; transaction_count: number; total_amount: number; count?: number }[] }).daily_pattern;
      if (Array.isArray(dp)) {
        dayData = dp
          .map((d) => ({ day: String(d.day), count: d.transaction_count ?? d.count ?? 0, total: d.total_amount ?? 0 }))
          .sort((a, b) => Number(a.day) - Number(b.day));
      }
    } else {
      // Legacy format: {Monday: 5, Tuesday: 3, ...}
      dayData = Object.entries(rawDayPatterns as Record<string, number>).map(([day, count]) => ({
        day: day.slice(0, 3),
        count: typeof count === "number" ? count : 0,
        total: 0,
      }));
    }
  }

  // ─── Normalize channel analysis ──────────────────────────────────────────
  let channelData: { name: string; fullName: string; count: number }[] = [];
  if (rawChannels) {
    if ("channels" in (rawChannels as Record<string, unknown>)) {
      // New format: {channels: [{channel, count, total, percentage}], ...}
      const ch = (rawChannels as { channels?: { channel: string; count: number }[] }).channels || [];
      channelData = ch.map((c) => ({
        name: c.channel.length > 12 ? c.channel.slice(0, 12) + "…" : c.channel,
        fullName: c.channel,
        count: c.count,
      }));
    } else {
      // Legacy format: {channel_name: count}
      channelData = Object.entries(rawChannels as Record<string, number>).map(([name, count]) => ({
        name: name.length > 12 ? name.slice(0, 12) + "…" : name,
        fullName: name,
        count: typeof count === "number" ? count : 0,
      }));
    }
  }

  // ─── Normalize counterparties ────────────────────────────────────────────
  const topCreditors = (counterparties?.by_credit || counterparties?.top_customers || []).slice(0, 5);
  const topDebitors = (counterparties?.by_debit || counterparties?.top_vendors || []).slice(0, 5);

  // ─── Normalize unusual transactions ──────────────────────────────────────
  let unusualList: { date: string; description: string; amount: number; reason: string }[] = [];
  if (Array.isArray(rawUnusual)) {
    unusualList = rawUnusual;
  } else if (rawUnusual && typeof rawUnusual === "object") {
    // New format: {large_transactions: [...], round_number_transactions: [...], ...}
    const ut = rawUnusual as Record<string, unknown>;
    for (const key of ["large_transactions", "same_day_large_movements", "low_balance_events", "round_number_transactions"]) {
      const arr = ut[key];
      if (Array.isArray(arr)) {
        for (const item of arr) {
          unusualList.push({
            date: item.date || "—",
            description: item.description || item.reason || key.replace(/_/g, " "),
            amount: item.amount || item.credits || item.balance || 0,
            reason: item.reason || item.type || key.replace(/_/g, " "),
          });
        }
      }
    }
  }

  // ─── Normalize business health factors ───────────────────────────────────
  let healthFactors: { factor: string; impact: string; details: string }[] = [];
  let healthGrade = health?.grade || "";
  if (health) {
    if (Array.isArray(health.factors)) {
      healthFactors = health.factors;
    } else if (health.indicators) {
      if (Array.isArray(health.indicators)) {
        healthFactors = health.indicators as { factor: string; impact: string; details: string }[];
      } else {
        // indicators is a dict like {cash_runway_months: x, ...}
        healthFactors = Object.entries(health.indicators).map(([key, val]) => ({
          factor: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
          impact: typeof val === "number" && val < 0 ? "negative" : typeof val === "number" && val > 0 ? "positive" : "neutral",
          details: String(val),
        }));
      }
    }
    if (!healthGrade && health.assessment) {
      healthGrade = health.assessment;
    }
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-zinc-800/50 bg-gradient-to-b from-purple-500/[0.02] to-transparent">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Link
            href={`/documents/${documentId}`}
            className="mb-4 inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to Overview
          </Link>

          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10 border border-purple-500/20">
              <BarChart3 className="h-5 w-5 text-purple-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Insights Agent</h1>
              <p className="text-sm text-zinc-500">
                Cash flow analysis, spending categories, counterparties & business health
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-8 space-y-8">

        {/* Cash Flow Summary Cards */}
        {cashFlow && (
          <div className="grid grid-cols-3 gap-4">
            <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
                <TrendingUp className="h-3 w-3 text-emerald-400" />
                Total Inflow
              </div>
              <p className="mt-2 text-2xl font-bold text-emerald-400">
                {formatCurrency(cashFlow.total_inflow)}
              </p>
            </div>
            <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
                <TrendingDown className="h-3 w-3 text-red-400" />
                Total Outflow
              </div>
              <p className="mt-2 text-2xl font-bold text-red-400">
                {formatCurrency(cashFlow.total_outflow)}
              </p>
            </div>
            <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zinc-500">
                <ArrowRightLeft className="h-3 w-3 text-indigo-400" />
                Net Flow
              </div>
              <p className={cn("mt-2 text-2xl font-bold", cashFlow.net_flow >= 0 ? "text-emerald-400" : "text-red-400")}>
                {formatCurrency(cashFlow.net_flow)}
              </p>
            </div>
          </div>
        )}

        {/* Business Health Score */}
        {health && (
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <div className="flex items-center gap-2 mb-4">
              <Heart className="h-4 w-4 text-purple-400" />
              <h3 className="text-sm font-semibold text-zinc-300">Business Health</h3>
            </div>
            <div className="flex items-center gap-6 mb-4">
              <div>
                <span className="text-4xl font-bold text-purple-400">{health.score}</span>
                <span className="text-lg text-zinc-500">/100</span>
              </div>
              {healthGrade && (
                <span className={cn(
                  "rounded-full px-3 py-1 text-sm font-bold",
                  health.score >= 80 ? "bg-emerald-500/10 text-emerald-400" :
                  health.score >= 60 ? "bg-green-500/10 text-green-400" :
                  health.score >= 40 ? "bg-amber-500/10 text-amber-400" :
                  "bg-red-500/10 text-red-400"
                )}>
                  {healthGrade}
                </span>
              )}
            </div>
            {healthFactors.length > 0 && (
              <div className="space-y-2">
                {healthFactors.map((f, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-lg bg-zinc-800/30 px-3 py-2">
                    <span className={cn(
                      "mt-0.5 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                      f.impact === "positive" ? "bg-emerald-500/10 text-emerald-400" :
                      f.impact === "negative" ? "bg-red-500/10 text-red-400" :
                      "bg-zinc-700 text-zinc-400"
                    )}>
                      {f.impact}
                    </span>
                    <div>
                      <p className="text-xs font-medium text-zinc-300">{f.factor}</p>
                      <p className="text-[11px] text-zinc-500">{f.details}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Monthly Cash Flow Chart */}
        {monthlyFlows.length > 0 && (
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
              <Wallet className="h-4 w-4 text-purple-400" />
              Monthly Cash Flow
            </h3>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyFlows} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                  <XAxis dataKey={(d: Record<string, unknown>) => d.month || d.week || ''} tick={{ fontSize: 10, fill: "#71717a" }} axisLine={{ stroke: "#27272a" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#71717a" }} axisLine={{ stroke: "#27272a" }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#111118", border: "1px solid #27272a", borderRadius: "8px", fontSize: 12 }}
                    formatter={(value, name) => [formatCurrency(value as number), String(name).charAt(0).toUpperCase() + String(name).slice(1)]}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="inflow" fill="#10b981" radius={[3, 3, 0, 0]} fillOpacity={0.8} />
                  <Bar dataKey="outflow" fill="#ef4444" radius={[3, 3, 0, 0]} fillOpacity={0.8} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Two Column: Categories + Channels */}
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Category Breakdown */}
          {categoryData.length > 0 && (
            <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
                <BarChart3 className="h-4 w-4 text-purple-400" />
                Top Categories
              </h3>
              <div className="flex items-center gap-4">
                {/* Donut chart — no labels, clean look */}
                <div className="h-52 w-52 flex-shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={categoryData}
                        dataKey="total"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={40}
                        outerRadius={75}
                        paddingAngle={2}
                        label={false}
                        labelLine={false}
                      >
                        {categoryData.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.85} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ backgroundColor: "#111118", border: "1px solid #27272a", borderRadius: "8px", fontSize: 12 }}
                        formatter={(value) => [formatCurrency(value as number), "Total"]}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                {/* Legend table */}
                <div className="flex-1 space-y-1.5 min-w-0">
                  {categoryData.map((cat, i) => {
                    const grandTotal = categoryData.reduce((s, c) => s + c.total, 0);
                    const pct = grandTotal > 0 ? ((cat.total / grandTotal) * 100).toFixed(0) : "0";
                    return (
                      <div key={i} className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                        <span className="text-xs text-zinc-300 truncate flex-1" title={cat.fullName}>{cat.fullName}</span>
                        <span className="text-xs font-mono text-zinc-500 flex-shrink-0">{pct}%</span>
                        <span className="text-xs font-mono text-zinc-400 flex-shrink-0">{formatCurrency(cat.total)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Channel Analysis */}
          {channelData.length > 0 && (
            <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
                <Radio className="h-4 w-4 text-purple-400" />
                Channels
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={channelData} layout="vertical" margin={{ top: 5, right: 20, left: 60, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                    <XAxis type="number" tick={{ fontSize: 10, fill: "#71717a" }} axisLine={{ stroke: "#27272a" }} />
                    <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: "#71717a" }} axisLine={{ stroke: "#27272a" }} width={55} />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#111118", border: "1px solid #27272a", borderRadius: "8px", fontSize: 12 }}
                    />
                    <Bar dataKey="count" fill="#8b5cf6" radius={[0, 3, 3, 0]} fillOpacity={0.8} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>

        {/* Day of Week & Counterparties */}
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Day Patterns */}
          {dayData.length > 0 && (
            <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
                <Calendar className="h-4 w-4 text-purple-400" />
                {isDayOfMonth ? "Transaction Activity by Day of Month" : "Day of Week Patterns"}
              </h3>
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dayData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                    <XAxis
                      dataKey="day"
                      tick={{ fontSize: 10, fill: "#71717a" }}
                      axisLine={{ stroke: "#27272a" }}
                      label={isDayOfMonth ? { value: "Day of Month", position: "insideBottom", offset: -2, fontSize: 10, fill: "#52525b" } : undefined}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "#71717a" }}
                      axisLine={{ stroke: "#27272a" }}
                      label={{ value: "Transactions", angle: -90, position: "insideLeft", offset: 10, fontSize: 10, fill: "#52525b" }}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: "#111118", border: "1px solid #27272a", borderRadius: "8px", fontSize: 12 }}
                      formatter={(value, name) => {
                        const v = Number(value) || 0;
                        if (name === "Transactions") return [v, "Transactions"];
                        if (name === "total") return [formatCurrency(v), "Total Amount"];
                        return [v, String(name)];
                      }}
                      labelFormatter={(label) => isDayOfMonth ? `Day ${label}` : label}
                    />
                    <Bar dataKey="count" name="Transactions" fill="#a855f7" radius={[3, 3, 0, 0]} fillOpacity={0.8} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Top Counterparties */}
          {(topCreditors.length > 0 || topDebitors.length > 0) && (
            <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
                <Users className="h-4 w-4 text-purple-400" />
                Top Counterparties
              </h3>
              <div className="space-y-4">
                {topCreditors.length > 0 && (
                  <div>
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-emerald-400">Top Senders</p>
                    <div className="space-y-1.5">
                      {topCreditors.map((c, i) => (
                        <div key={i} className="flex items-center justify-between rounded-lg bg-zinc-800/30 px-3 py-2">
                          <span className="text-xs text-zinc-300 truncate max-w-[150px]">{c.name}</span>
                          <div className="text-right">
                            <span className="text-xs font-mono text-emerald-400">{formatCurrency(c.total)}</span>
                            <span className="ml-2 text-[10px] text-zinc-500">({c.count}x)</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {topDebitors.length > 0 && (
                  <div>
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-red-400">Top Recipients</p>
                    <div className="space-y-1.5">
                      {topDebitors.map((c, i) => (
                        <div key={i} className="flex items-center justify-between rounded-lg bg-zinc-800/30 px-3 py-2">
                          <span className="text-xs text-zinc-300 truncate max-w-[150px]">{c.name}</span>
                          <div className="text-right">
                            <span className="text-xs font-mono text-red-400">{formatCurrency(c.total)}</span>
                            <span className="ml-2 text-[10px] text-zinc-500">({c.count}x)</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Unusual Transactions */}
        {unusualList.length > 0 && (
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
              <AlertCircle className="h-4 w-4 text-amber-400" />
              Unusual Transactions ({unusualList.length})
            </h3>
            <div className="space-y-2">
              {unusualList.slice(0, 20).map((u, i) => (
                <div key={i} className="flex items-start justify-between rounded-lg bg-amber-500/5 border border-amber-500/10 px-4 py-3">
                  <div>
                    <p className="text-xs font-medium text-zinc-300">{u.description}</p>
                    <p className="text-[11px] text-zinc-500">{u.date} — {u.reason}</p>
                  </div>
                  {u.amount !== 0 && (
                    <span className="font-mono text-xs text-amber-400 whitespace-nowrap ml-4">
                      {formatCurrency(u.amount)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* AI Narrative */}
        {narrativeText && (
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-300">
              <MessageSquare className="h-4 w-4 text-purple-400" />
              AI Analysis Narrative
            </h3>
            <div className="prose prose-invert prose-sm max-w-none">
              <p className="text-sm leading-relaxed text-zinc-400 whitespace-pre-line">{narrativeText}</p>
            </div>
          </div>
        )}

        {/* AI Narrative — Sectioned */}
        {narrativeSections.length > 0 && (
          <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/30 p-5">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-zinc-300">
              <MessageSquare className="h-4 w-4 text-purple-400" />
              AI Analysis Narrative
            </h3>
            <div className="space-y-4">
              {narrativeSections.map((section, i) => (
                <div key={i}>
                  <h4 className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-1">
                    {section.title}
                  </h4>
                  <p className="text-sm leading-relaxed text-zinc-400 whitespace-pre-line">
                    {section.content}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
