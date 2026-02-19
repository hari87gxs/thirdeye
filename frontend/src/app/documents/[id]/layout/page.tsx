"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAgentResult } from "@/lib/api";
import { AgentResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  FileText,
  CheckCircle2,
  XCircle,
  Loader2,
  FileSearch,
  Table,
  Calendar,
  Hash,
} from "lucide-react";

interface LayoutResults {
  bank_detected?: string;
  confidence?: number;
  table_structure?: boolean;
  column_mapping?: Record<string, string>;
  date_format?: string;
  amount_format?: string;
  multi_line_descriptions?: boolean;
  special_markers?: {
    has_opening_balance?: boolean;
    has_closing_balance?: boolean;
    has_brought_forward?: boolean;
  };
  metadata?: {
    total_pages?: number;
    has_headers?: boolean;
    has_footers?: boolean;
  };
}

export default function LayoutPage() {
  const params = useParams();
  const documentId = params.id as string;
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!documentId) return;
    getAgentResult(documentId, "layout")
      .then((result) => {
        setAgentResult(result);
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

  const results = (agentResult?.results || {}) as LayoutResults;
  const confidence = (results.confidence || 0) * 100;

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link
                href={`/documents/${documentId}`}
                className="rounded-lg p-2 hover:bg-gray-800 transition-colors"
              >
                <ArrowLeft className="h-5 w-5 text-gray-400" />
              </Link>
              <div className="flex items-center gap-3">
                <FileSearch className="h-6 w-6 text-cyan-400" />
                <div>
                  <h1 className="text-xl font-semibold">Layout Agent</h1>
                  <p className="text-sm text-gray-400">
                    PDF structure analysis & bank detection
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {agentResult?.status === "completed" ? (
                <div className="flex items-center gap-2 rounded-lg bg-green-500/10 px-3 py-1.5 text-green-400 border border-green-500/20">
                  <CheckCircle2 className="h-4 w-4" />
                  <span className="text-sm font-medium">Completed</span>
                </div>
              ) : agentResult?.status === "failed" ? (
                <div className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-1.5 text-red-400 border border-red-500/20">
                  <XCircle className="h-4 w-4" />
                  <span className="text-sm font-medium">Failed</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 rounded-lg bg-yellow-500/10 px-3 py-1.5 text-yellow-400 border border-yellow-500/20">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm font-medium">Running</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="space-y-6">
          {/* Bank Detection */}
          <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="rounded-lg bg-cyan-500/10 p-2">
                <FileSearch className="h-5 w-5 text-cyan-400" />
              </div>
              <h2 className="text-lg font-semibold">Bank Detection</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <div className="text-sm text-gray-400 mb-1">Detected Bank</div>
                <div className="text-2xl font-bold text-white">
                  {results.bank_detected || "Unknown"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-400 mb-1">Confidence Score</div>
                <div className="flex items-end gap-3">
                  <div className="text-2xl font-bold text-cyan-400">
                    {confidence.toFixed(1)}%
                  </div>
                  <div
                    className={cn(
                      "text-sm font-medium px-2 py-0.5 rounded",
                      confidence >= 80
                        ? "bg-green-500/10 text-green-400"
                        : confidence >= 50
                        ? "bg-yellow-500/10 text-yellow-400"
                        : "bg-red-500/10 text-red-400"
                    )}
                  >
                    {confidence >= 80 ? "High" : confidence >= 50 ? "Medium" : "Low"}
                  </div>
                </div>
                <div className="mt-2 h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full transition-all",
                      confidence >= 80
                        ? "bg-green-500"
                        : confidence >= 50
                        ? "bg-yellow-500"
                        : "bg-red-500"
                    )}
                    style={{ width: `${confidence}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Table Structure */}
          <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="rounded-lg bg-blue-500/10 p-2">
                <Table className="h-5 w-5 text-blue-400" />
              </div>
              <h2 className="text-lg font-semibold">Table Structure</h2>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 rounded-lg bg-gray-800/50">
                <span className="text-gray-300">Tabular Data Detected</span>
                {results.table_structure ? (
                  <CheckCircle2 className="h-5 w-5 text-green-400" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-400" />
                )}
              </div>
              {results.column_mapping && Object.keys(results.column_mapping).length > 0 && (
                <div>
                  <div className="text-sm text-gray-400 mb-3">Column Mappings</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.entries(results.column_mapping).map(([header, canonical]) => (
                      <div
                        key={header}
                        className="flex items-center gap-3 p-3 rounded-lg bg-gray-800/50 border border-gray-700"
                      >
                        <div className="flex-1">
                          <div className="text-xs text-gray-500">Header</div>
                          <div className="text-sm text-white">{header}</div>
                        </div>
                        <div className="text-gray-600">→</div>
                        <div className="flex-1">
                          <div className="text-xs text-gray-500">Canonical</div>
                          <div className="text-sm text-cyan-400 font-medium">{canonical}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Format Detection */}
          <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="rounded-lg bg-purple-500/10 p-2">
                <Calendar className="h-5 w-5 text-purple-400" />
              </div>
              <h2 className="text-lg font-semibold">Format Detection</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {results.date_format && (
                <div>
                  <div className="text-sm text-gray-400 mb-2">Date Format</div>
                  <div className="p-3 rounded-lg bg-gray-800/50 border border-gray-700">
                    <code className="text-purple-400 font-mono text-sm">
                      {results.date_format}
                    </code>
                  </div>
                </div>
              )}
              {results.amount_format && (
                <div>
                  <div className="text-sm text-gray-400 mb-2">Amount Format</div>
                  <div className="p-3 rounded-lg bg-gray-800/50 border border-gray-700">
                    <code className="text-purple-400 font-mono text-sm">
                      {results.amount_format}
                    </code>
                  </div>
                </div>
              )}
              <div>
                <div className="text-sm text-gray-400 mb-2">Multi-line Descriptions</div>
                <div className="flex items-center gap-2">
                  {results.multi_line_descriptions ? (
                    <>
                      <CheckCircle2 className="h-5 w-5 text-green-400" />
                      <span className="text-green-400">Detected</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-5 w-5 text-gray-600" />
                      <span className="text-gray-500">Not detected</span>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Special Markers */}
          {results.special_markers && (
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="rounded-lg bg-amber-500/10 p-2">
                  <Hash className="h-5 w-5 text-amber-400" />
                </div>
                <h2 className="text-lg font-semibold">Special Markers</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex items-center justify-between p-4 rounded-lg bg-gray-800/50">
                  <span className="text-gray-300">Opening Balance</span>
                  {results.special_markers.has_opening_balance ? (
                    <CheckCircle2 className="h-5 w-5 text-green-400" />
                  ) : (
                    <XCircle className="h-5 w-5 text-gray-600" />
                  )}
                </div>
                <div className="flex items-center justify-between p-4 rounded-lg bg-gray-800/50">
                  <span className="text-gray-300">Closing Balance</span>
                  {results.special_markers.has_closing_balance ? (
                    <CheckCircle2 className="h-5 w-5 text-green-400" />
                  ) : (
                    <XCircle className="h-5 w-5 text-gray-600" />
                  )}
                </div>
                <div className="flex items-center justify-between p-4 rounded-lg bg-gray-800/50">
                  <span className="text-gray-300">Brought Forward</span>
                  {results.special_markers.has_brought_forward ? (
                    <CheckCircle2 className="h-5 w-5 text-green-400" />
                  ) : (
                    <XCircle className="h-5 w-5 text-gray-600" />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Document Metadata */}
          {results.metadata && (
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="rounded-lg bg-indigo-500/10 p-2">
                  <FileText className="h-5 w-5 text-indigo-400" />
                </div>
                <h2 className="text-lg font-semibold">Document Metadata</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {results.metadata.total_pages && (
                  <div>
                    <div className="text-sm text-gray-400 mb-1">Total Pages</div>
                    <div className="text-2xl font-bold text-white">
                      {results.metadata.total_pages}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-sm text-gray-400 mb-1">Headers</div>
                  <div className="flex items-center gap-2">
                    {results.metadata.has_headers ? (
                      <>
                        <CheckCircle2 className="h-5 w-5 text-green-400" />
                        <span className="text-green-400">Detected</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="h-5 w-5 text-gray-600" />
                        <span className="text-gray-500">Not detected</span>
                      </>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-400 mb-1">Footers</div>
                  <div className="flex items-center gap-2">
                    {results.metadata.has_footers ? (
                      <>
                        <CheckCircle2 className="h-5 w-5 text-green-400" />
                        <span className="text-green-400">Detected</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="h-5 w-5 text-gray-600" />
                        <span className="text-gray-500">Not detected</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Error Display */}
          {agentResult?.error_message && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-6">
              <div className="flex items-start gap-3">
                <XCircle className="h-5 w-5 text-red-400 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-red-400 mb-1">Error</h3>
                  <p className="text-sm text-red-300">{agentResult.error_message}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
