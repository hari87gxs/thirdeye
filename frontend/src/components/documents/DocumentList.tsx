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
  Layers,
} from "lucide-react";

interface DocumentListProps {
  documents: DocumentResponse[];
  onAnalyze: (id: string) => void;
  onDelete: (id: string) => void;
  analyzingIds: Set<string>;
}

interface DocumentGroup {
  upload_group_id: string;
  documents: DocumentResponse[];
  created_at: string;
}

function getStatusIcon(status: string, isAnalyzing: boolean) {
  if (isAnalyzing) return <Loader2 className="h-4 w-4 animate-spin text-blue-400" />;
  if (status === "completed") return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
  if (status === "failed") return <XCircle className="h-4 w-4 text-red-400" />;
  return <UploadCloud className="h-4 w-4 text-zinc-500" />;
}

function getGroupStatus(docs: DocumentResponse[], analyzingIds: Set<string>) {
  const anyAnalyzing = docs.some(d => analyzingIds.has(d.id) || d.status === "processing");
  const allCompleted = docs.every(d => d.status === "completed");
  const anyFailed = docs.some(d => d.status === "failed");

  if (anyAnalyzing) return "processing";
  if (allCompleted) return "completed";
  if (anyFailed) return "failed";
  return "uploaded";
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

  // Group documents by upload_group_id
  const groupMap = new Map<string, DocumentGroup>();
  for (const doc of documents) {
    const gid = doc.upload_group_id || doc.id;
    if (!groupMap.has(gid)) {
      groupMap.set(gid, {
        upload_group_id: gid,
        documents: [],
        created_at: doc.created_at,
      });
    }
    groupMap.get(gid)!.documents.push(doc);
  }

  const groups = Array.from(groupMap.values()).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <div className="space-y-4">
      {groups.map((group, groupIdx) => {
        const isSingleDoc = group.documents.length === 1;
        const groupStatus = getGroupStatus(group.documents, analyzingIds);
        const isGroupCompleted = groupStatus === "completed";
        const isGroupAnalyzing = groupStatus === "processing";

        return (
          <div
            key={group.upload_group_id}
            className={cn(
              "rounded-xl border transition-all duration-200 animate-fade-in overflow-hidden",
              isGroupCompleted
                ? "border-zinc-800/50 bg-zinc-900/20"
                : isGroupAnalyzing
                ? "border-blue-500/20 bg-blue-500/[0.03]"
                : groupStatus === "failed"
                ? "border-red-500/20 bg-red-500/[0.03]"
                : "border-zinc-800/50 bg-zinc-900/20"
            )}
            style={{ animationDelay: `${groupIdx * 50}ms` }}
          >
            {/* Group Header */}
            {!isSingleDoc && (
              <div className="flex items-center justify-between border-b border-zinc-800/30 px-5 py-3">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-lg",
                    isGroupCompleted ? "bg-emerald-500/10" : isGroupAnalyzing ? "bg-blue-500/10" : "bg-zinc-800/50"
                  )}>
                    <Layers className={cn(
                      "h-4 w-4",
                      isGroupCompleted ? "text-emerald-400" : isGroupAnalyzing ? "text-blue-400" : "text-zinc-500"
                    )} />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-zinc-300">
                      Batch Upload · {group.documents.length} statements
                    </p>
                    <p className="text-[10px] text-zinc-600">
                      {formatDateTime(group.created_at)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                    isGroupCompleted
                      ? "bg-emerald-500/10 text-emerald-400"
                      : isGroupAnalyzing
                      ? "bg-blue-500/10 text-blue-400"
                      : groupStatus === "failed"
                      ? "bg-red-500/10 text-red-400"
                      : "bg-zinc-800 text-zinc-500"
                  )}>
                    {isGroupAnalyzing
                      ? `Analyzing (${group.documents.filter(d => d.status === "completed").length}/${group.documents.length})`
                      : groupStatus}
                  </span>
                  {isGroupCompleted && (
                    <Link
                      href={`/groups/${group.upload_group_id}`}
                      className="flex items-center gap-1 rounded-lg bg-indigo-600/80 px-3 py-1.5 text-xs font-medium text-white transition-all hover:bg-indigo-500"
                    >
                      Group Results
                      <ChevronRight className="h-3 w-3" />
                    </Link>
                  )}
                </div>
              </div>
            )}

            {/* Individual Documents */}
            <div className={cn(isSingleDoc ? "" : "divide-y divide-zinc-800/20")}>
              {group.documents.map((doc) => {
                const isAnalyzing = analyzingIds.has(doc.id) || doc.status === "processing";
                const isCompleted = doc.status === "completed";
                const isFailed = doc.status === "failed";

                return (
                  <div
                    key={doc.id}
                    className="group flex items-center justify-between px-5 py-3.5 transition-all hover:bg-zinc-800/10"
                  >
                    <div className="flex items-center gap-4">
                      <div className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-lg",
                        isCompleted ? "bg-emerald-500/10" : isAnalyzing ? "bg-blue-500/10" : isFailed ? "bg-red-500/10" : "bg-zinc-800/50"
                      )}>
                        {getStatusIcon(doc.status, isAnalyzing)}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-zinc-200">{doc.original_filename}</p>
                        <div className="mt-0.5 flex items-center gap-3 text-xs text-zinc-500">
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
                          {isSingleDoc && (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {formatDateTime(doc.created_at)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
                        isCompleted
                          ? "bg-emerald-500/10 text-emerald-400"
                          : isAnalyzing
                          ? "bg-blue-500/10 text-blue-400"
                          : isFailed
                          ? "bg-red-500/10 text-red-400"
                          : "bg-zinc-800 text-zinc-500"
                      )}>
                        {isAnalyzing ? "Analyzing..." : doc.status}
                      </span>

                      {!isCompleted && !isAnalyzing && (
                        <button
                          onClick={() => onAnalyze(doc.id)}
                          className="flex items-center gap-1.5 rounded-lg bg-indigo-600/80 px-3 py-1.5 text-xs font-medium text-white transition-all hover:bg-indigo-500"
                        >
                          <Play className="h-3 w-3" />
                          Analyze
                        </button>
                      )}

                      {isCompleted && (
                        <Link
                          href={isSingleDoc ? `/groups/${group.upload_group_id}` : `/documents/${doc.id}`}
                          className="flex items-center gap-1 rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-all hover:bg-zinc-700 hover:text-white"
                        >
                          View
                          <ChevronRight className="h-3 w-3" />
                        </Link>
                      )}

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
          </div>
        );
      })}
    </div>
  );
}
