"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Upload,
  FileText,
  BarChart3,
  Shield,
  AlertTriangle,
  Activity,
  Menu,
  X,
} from "lucide-react";
import { useState } from "react";

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: Upload, description: "Upload & Documents" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 h-screen border-r border-zinc-800/50 bg-[#0c0c14] transition-all duration-300",
        collapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center justify-between border-b border-zinc-800/50 px-4">
        {!collapsed && (
          <Link href="/" className="flex items-center gap-2.5">
            <Image
              src="/logo.png"
              alt="ThirdEye AI"
              width={36}
              height={36}
              className="rounded-lg"
            />
            <div>
              <span className="text-lg font-bold text-white">ThirdEye</span>
              <span className="ml-1.5 text-[10px] font-medium text-indigo-400/70 uppercase tracking-wider">
                AI
              </span>
            </div>
          </Link>
        )}
        {collapsed && (
          <Link href="/" className="mx-auto">
            <Image
              src="/logo.png"
              alt="ThirdEye AI"
              width={32}
              height={32}
              className="rounded-lg"
            />
          </Link>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="rounded-md p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors"
        >
          {collapsed ? <Menu className="h-4 w-4" /> : <X className="h-4 w-4" />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 p-3">
        {!collapsed && (
          <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
            Navigation
          </p>
        )}
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                isActive
                  ? "bg-indigo-500/10 text-indigo-400"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Agent Legend */}
      {!collapsed && (
        <div className="absolute bottom-0 left-0 right-0 border-t border-zinc-800/50 p-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
            AI Agents
          </p>
          <div className="space-y-2">
            {[
              { icon: FileText, label: "Extraction", color: "text-blue-400" },
              { icon: BarChart3, label: "Insights", color: "text-purple-400" },
              { icon: Shield, label: "Tampering", color: "text-amber-400" },
              { icon: AlertTriangle, label: "Fraud", color: "text-red-400" },
            ].map((agent) => (
              <div key={agent.label} className="flex items-center gap-2.5 text-xs">
                <agent.icon className={cn("h-3.5 w-3.5", agent.color)} />
                <span className="text-zinc-500">{agent.label}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-2 text-[10px] text-zinc-600">
            <Activity className="h-3 w-3" />
            <span>Multi-Agent Platform</span>
          </div>
        </div>
      )}
    </aside>
  );
}
