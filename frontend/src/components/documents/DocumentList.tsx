"use client";

import Link from "next/link";
import { DocumentResponse } from "@/lib/types";
import {
  formatDateTime,
  formatFileSize,
  cn,
} from "@/lib/utils";
import {
  FileText,
  Clock,
  HardDrive,
  FileStack,
  ChevronRight,
  Loader2,
  CheckCircle2,
  XCircle,
  UploadCloud,
  Play,
  Trash2,
} from "lucide-react";

interface DocumentListProps {
  documents: DocumentResponse[];
  onAnalyze: (id: string) => void;
  onDelete: (id: string) => void;
  analyzingIds: Set<string>;
}

export function DocumentList({ documents, onAnalyze, onDelete, analyzingIds }: DocumentListProps) {
  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-800/50">
          <FileStack className="h-7 w-7 text-zinc-600" />
        </div>
        <p className="text-base font-medium text-zinc-400">No documents yet</p>
        <p className="mt-1 text-sm text-zinc-600">
          Upload bank statements above to get started
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {documents.map((doc, index) => {
        const isAnalyzing = analyzingIds.has(doc.id) || doc.status === "processing";
        const isCompleted = doc.status === "completed";
        const isFailed = doc.status === "failed";

        return (
          <div
            key={doc.id}
            className={cn(
              "group relative flex items-center justify-between rounded-xl border px-5 py-4 transition-all duration-200 animate-fade-in",
              isCompleted
                ? "border-zinc-800/50 bg-zinc-900/30 hover:border-zinc-700/50 hover:bg-zinc-900/50"
                : isAnalyzing
                ? "border-blue-500/20 bg-blue-500/5"
                : isFailed
                ? "border-red-500/20 bg-red-500/5"
                : "border-zinc-800/50 bg-zinc-900/30 hover:border-zinc-700/50"
            )}
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <div className="flex items-center gap-4">
              {/* Status Icon */}
              <div
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-lg",
                  isCompleted
                    ? "bg-emerald-500/10"
                    : isAnalyzing
                    ? "bg-blue-500/10"
                    : isFailed
                    ? "bg-red-500/10"
                    : "bg-zinc-800/50"
                )}
              >
                {isAnalyzing ? (
                  <Loader2 className="h-5 w-5 animate-spin text-blue-400" />
                ) : isCompleted ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                ) : isFailed ? (
                  <XCircle className="h-5 w-5 text-red-400" />
                ) : (
                  <UploadCloud className="h-5 w-5 text-zinc-500" />
                )}
              </div>

              {/* File Info */}
              <div>
                <p className="text-sm font-medium text-zinc-200">
                  {doc.original_filename}
                </p>
                <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
                  <span className="flex items-center gap-1">
                    <HardDrive className="h-3 w-3" />
                    {formatFileSize(doc.file_size)}
                  </span>
                  {doc.page_count && (
                    <span className="flex items-center gap-1">
                      <FileText className="h-3 w-3" />
                      {doc.page_count} pages
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatDateTime(doc.created_at)}
                  </span>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
              {/* Status Badge */}
              <span
                className={cn(
                  "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                  isCompleted
                    ? "bg-emerald-500/10 text-emerald-400"
                    : isAnalyzing
                    ? "bg-blue-500/10 text-blue-400"
                    : isFailed
                    ? "bg-red-500/10 text-red-400"
                    : "bg-zinc-800 text-zinc-500"
                )}
              >
                {isAnalyzing ? "Analyzing..." : doc.status}
              </span>

              {/* Analyze Button */}
              {!isCompleted && !isAnalyzing && (
                <button
                  onClick={() => onAnalyze(doc.id)}
                  className="flex items-center gap-1.5 rounded-lg bg-indigo-600/80 px-3 py-1.5 text-xs font-medium text-white transition-all hover:bg-indigo-500"
                >
                  <Play className="h-3 w-3" />
                  Analyze
                </button>
              )}

              {/* View Button */}
              {isCompleted && (
                <Link
                  href={`/documents/${doc.id}`}
                  className="flex items-center gap-1 rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-all hover:bg-zinc-700 hover:text-white"
                >
                  View Results
                  <ChevronRight className="h-3 w-3" />
                </Link>
              )}

              {/* Delete Button */}
              <button
                onClick={() => onDelete(doc.id)}
                className="rounded-lg p-1.5 text-zinc-600 opacity-0 transition-all group-hover:opacity-100 hover:bg-red-500/10 hover:text-red-400"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
