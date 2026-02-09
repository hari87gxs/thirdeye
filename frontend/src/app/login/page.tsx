"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import {
  Eye,
  EyeOff,
  Loader2,
  Mail,
  Lock,
  User,
  FileText,
  BarChart3,
  Shield,
  AlertTriangle,
} from "lucide-react";

const AGENTS = [
  {
    icon: FileText,
    label: "Extraction",
    desc: "Parse bank statements automatically",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
  },
  {
    icon: BarChart3,
    label: "Insights",
    desc: "Detect unusual spending patterns",
    color: "text-purple-400",
    bg: "bg-purple-500/10",
  },
  {
    icon: Shield,
    label: "Tampering",
    desc: "Catch forged or altered documents",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
  },
  {
    icon: AlertTriangle,
    label: "Fraud",
    desc: "Flag suspicious transactions",
    color: "text-red-400",
    bg: "bg-red-500/10",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(name, email, password);
      }
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      {/* Left — Branding Panel */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-gradient-to-br from-[#0c0c14] via-[#111128] to-[#0c0c14] p-12 border-r border-zinc-800/50">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Image
              src="/logo.png"
              alt="ThirdEye"
              width={44}
              height={44}
              className="rounded-lg"
            />
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-bold text-white tracking-tight">
                ThirdEye
              </span>
              <span className="text-sm font-semibold text-indigo-400 uppercase tracking-wider">
                AI
              </span>
            </div>
          </div>
          <p className="mt-4 text-lg text-zinc-400 max-w-md">
            Multi-agent AI platform for financial document intelligence.
            Upload bank statements and let our agents do the heavy lifting.
          </p>
        </div>

        {/* Agent cards */}
        <div className="space-y-3">
          {AGENTS.map((agent) => (
            <div
              key={agent.label}
              className="flex items-center gap-4 rounded-xl border border-zinc-800/50 bg-zinc-900/30 px-4 py-3"
            >
              <div
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                  agent.bg
                )}
              >
                <agent.icon className={cn("h-5 w-5", agent.color)} />
              </div>
              <div>
                <p className={cn("text-sm font-semibold", agent.color)}>
                  {agent.label} Agent
                </p>
                <p className="text-xs text-zinc-500">{agent.desc}</p>
              </div>
            </div>
          ))}
        </div>

        <p className="text-xs text-zinc-600">
          © {new Date().getFullYear()} ThirdEye AI — Secure Document Analysis
        </p>
      </div>

      {/* Right — Auth Form */}
      <div className="flex w-full lg:w-1/2 items-center justify-center px-6 py-12 bg-[#0a0a0f]">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="flex lg:hidden items-center gap-3 mb-8 justify-center">
            <Image
              src="/logo.png"
              alt="ThirdEye"
              width={40}
              height={40}
              className="rounded-lg"
            />
            <div className="flex items-baseline gap-1.5">
              <span className="text-xl font-bold text-white">ThirdEye</span>
              <span className="text-xs font-semibold text-indigo-400 uppercase">
                AI
              </span>
            </div>
          </div>

          <h1 className="text-2xl font-bold text-white mb-1">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="text-sm text-zinc-500 mb-8">
            {mode === "login"
              ? "Sign in to access your document analysis"
              : "Get started with ThirdEye AI in seconds"}
          </p>

          {error && (
            <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && (
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                  Full Name
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="John Doe"
                    required
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-900/50 py-2.5 pl-10 pr-4 text-sm text-white placeholder-zinc-600 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 transition-all"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-900/50 py-2.5 pl-10 pr-4 text-sm text-white placeholder-zinc-600 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  minLength={6}
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-900/50 py-2.5 pl-10 pr-10 text-sm text-white placeholder-zinc-600 outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className={cn(
                "w-full rounded-lg py-2.5 text-sm font-semibold transition-all",
                loading
                  ? "bg-indigo-500/50 text-indigo-200 cursor-wait"
                  : "bg-indigo-600 text-white hover:bg-indigo-500 active:scale-[0.98]"
              )}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {mode === "login" ? "Signing in…" : "Creating account…"}
                </span>
              ) : mode === "login" ? (
                "Sign In"
              ) : (
                "Create Account"
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-zinc-500">
            {mode === "login" ? (
              <>
                Don&apos;t have an account?{" "}
                <button
                  onClick={() => {
                    setMode("register");
                    setError(null);
                  }}
                  className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
                >
                  Create one
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  onClick={() => {
                    setMode("login");
                    setError(null);
                  }}
                  className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
