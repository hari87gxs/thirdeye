"use client";

import Link from "next/link";
import Image from "next/image";
import { FileText, BarChart3, Shield, AlertTriangle, LogOut, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

const AGENTS = [
  { icon: FileText, label: "Extraction", color: "text-blue-400 border-blue-400/30" },
  { icon: BarChart3, label: "Insights", color: "text-purple-400 border-purple-400/30" },
  { icon: Shield, label: "Tampering", color: "text-amber-400 border-amber-400/30" },
  { icon: AlertTriangle, label: "Fraud", color: "text-red-400 border-red-400/30" },
];

export function Navbar() {
  const { user, logout } = useAuth();

  return (
    <header className="sticky top-0 z-40 border-b border-zinc-800/50 bg-[#0c0c14]/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3">
          <Image
            src="/logo.png"
            alt="ThirdEye AI"
            width={36}
            height={36}
            className="rounded-lg"
          />
          <div className="flex items-baseline gap-1.5">
            <span className="text-lg font-bold text-white tracking-tight">ThirdEye</span>
            <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">AI</span>
          </div>
        </Link>

        {/* Agent Pills */}
        <div className="hidden md:flex items-center gap-2">
          {AGENTS.map((agent) => (
            <div
              key={agent.label}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
                agent.color
              )}
            >
              <agent.icon className="h-3 w-3" />
              {agent.label}
            </div>
          ))}
        </div>

        {/* User menu */}
        {user && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-lg border border-zinc-800/50 bg-zinc-900/30 px-3 py-1.5">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500/20">
                <User className="h-3.5 w-3.5 text-indigo-400" />
              </div>
              <span className="text-xs font-medium text-zinc-300 hidden sm:inline">
                {user.name}
              </span>
            </div>
            <button
              onClick={logout}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-800/50 px-2.5 py-1.5 text-xs text-zinc-500 hover:text-red-400 hover:border-red-500/30 transition-all"
              title="Sign out"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
