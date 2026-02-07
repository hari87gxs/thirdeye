import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number | null | undefined, currency = "SGD"): string {
  if (amount == null) return "—";
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-SG").format(n);
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleDateString("en-SG", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleString("en-SG", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function riskColor(level: string | null | undefined): string {
  switch (level?.toLowerCase()) {
    case "low":
      return "text-emerald-400";
    case "medium":
      return "text-amber-400";
    case "high":
      return "text-orange-400";
    case "critical":
      return "text-red-400";
    default:
      return "text-slate-400";
  }
}

export function riskBgColor(level: string | null | undefined): string {
  switch (level?.toLowerCase()) {
    case "low":
      return "bg-emerald-500/10 border-emerald-500/30";
    case "medium":
      return "bg-amber-500/10 border-amber-500/30";
    case "high":
      return "bg-orange-500/10 border-orange-500/30";
    case "critical":
      return "bg-red-500/10 border-red-500/30";
    default:
      return "bg-slate-500/10 border-slate-500/30";
  }
}

export function statusColor(status: string): string {
  switch (status) {
    case "completed":
      return "text-emerald-400";
    case "processing":
    case "running":
      return "text-blue-400";
    case "pending":
    case "uploaded":
      return "text-slate-400";
    case "failed":
      return "text-red-400";
    default:
      return "text-slate-400";
  }
}

export function checkStatusIcon(status: string): { icon: string; color: string } {
  switch (status?.toLowerCase()) {
    case "pass":
      return { icon: "✓", color: "text-emerald-400" };
    case "fail":
      return { icon: "✗", color: "text-red-400" };
    case "warning":
      return { icon: "⚠", color: "text-amber-400" };
    default:
      return { icon: "?", color: "text-slate-400" };
  }
}

export function gradeFromScore(score: number): { grade: string; color: string } {
  if (score >= 95) return { grade: "A+", color: "text-emerald-400" };
  if (score >= 90) return { grade: "A", color: "text-emerald-400" };
  if (score >= 85) return { grade: "B+", color: "text-green-400" };
  if (score >= 80) return { grade: "B", color: "text-green-400" };
  if (score >= 75) return { grade: "C+", color: "text-amber-400" };
  if (score >= 70) return { grade: "C", color: "text-amber-400" };
  if (score >= 60) return { grade: "D", color: "text-orange-400" };
  return { grade: "F", color: "text-red-400" };
}
