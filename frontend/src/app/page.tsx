"use client";

import { useState, useEffect, useCallback } from "react";
import { FileUploadZone } from "@/components/upload/FileUploadZone";
import { DocumentList } from "@/components/documents/DocumentList";
import {
  uploadDocuments,
  listDocuments,
  analyzeDocument,
  deleteDocument,
} from "@/lib/api";
import { DocumentResponse } from "@/lib/types";
import {
  FileText,
  Sparkles,
  Zap,
} from "lucide-react";

export default function HomePage() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [analyzingIds, setAnalyzingIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // silent fail on poll
    }
  }, []);

  useEffect(() => {
    loadDocuments();
    const interval = setInterval(loadDocuments, 3000);
    return () => clearInterval(interval);
  }, [loadDocuments]);

  const handleUpload = async (files: File[]) => {
    setIsUploading(true);
    setError(null);
    try {
      const result = await uploadDocuments(files);
      await loadDocuments();

      // Auto-trigger analysis for each uploaded document
      for (const doc of result.documents) {
        try {
          await analyzeDocument(doc.id);
          setAnalyzingIds((prev) => new Set(prev).add(doc.id));
        } catch {
          // ignore individual analysis trigger errors
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  const handleAnalyze = async (id: string) => {
    try {
      await analyzeDocument(id);
      setAnalyzingIds((prev) => new Set(prev).add(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  // Clear analyzing status when doc becomes completed
  useEffect(() => {
    const newAnalyzing = new Set(analyzingIds);
    let changed = false;
    for (const id of Array.from(analyzingIds)) {
      const doc = documents.find((d) => d.id === id);
      if (doc && (doc.status === "completed" || doc.status === "failed")) {
        newAnalyzing.delete(id);
        changed = true;
      }
    }
    if (changed) setAnalyzingIds(newAnalyzing);
  }, [documents, analyzingIds]);

  const completedCount = documents.filter((d) => d.status === "completed").length;

  return (
    <div className="min-h-screen">
      {/* Hero Header */}
      <div className="relative border-b border-zinc-800/50 bg-gradient-to-b from-indigo-500/[0.03] to-transparent">
        <div className="mx-auto max-w-6xl px-6 py-10">
          <div className="flex items-start justify-between">
            <div>
              <div className="mb-2 flex items-center gap-1.5 rounded-full bg-indigo-500/10 px-3 py-1 text-[10px] font-semibold text-indigo-400 uppercase tracking-wider w-fit">
                <Sparkles className="h-3 w-3" />
                Financial Document Analyzer
              </div>
              <h1 className="text-3xl font-bold text-white">
                Analyze Bank Statements with AI
              </h1>
              <p className="mt-2 max-w-lg text-sm text-zinc-400">
                Upload bank statements and let our 4 specialized AI agents analyze them
                for extraction accuracy, financial insights, tampering detection, and fraud patterns.
              </p>
            </div>

            {/* Stats */}
            <div className="hidden lg:flex items-center gap-4">
              {[
                { icon: FileText, label: "Documents", value: documents.length, color: "text-blue-400" },
                { icon: Zap, label: "Analyzed", value: completedCount, color: "text-emerald-400" },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="flex items-center gap-3 rounded-xl border border-zinc-800/50 bg-zinc-900/30 px-4 py-3"
                >
                  <stat.icon className={`h-5 w-5 ${stat.color}`} />
                  <div>
                    <p className="text-lg font-bold text-white">{stat.value}</p>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{stat.label}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Error */}
        {error && (
          <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-2 text-red-300 underline hover:text-red-200"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Upload Section */}
        <div className="mb-8">
          <FileUploadZone onUpload={handleUpload} isUploading={isUploading} />
        </div>

        {/* Documents Section */}
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">Documents</h2>
            <span className="text-xs text-zinc-500">
              {documents.length} document{documents.length !== 1 ? "s" : ""}
            </span>
          </div>
          <DocumentList
            documents={documents}
            onAnalyze={handleAnalyze}
            onDelete={handleDelete}
            analyzingIds={analyzingIds}
          />
        </div>
      </div>
    </div>
  );
}