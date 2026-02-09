"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Navbar } from "@/components/layout/Navbar";
import { Loader2 } from "lucide-react";

/**
 * Shell wrapper that:
 * - Shows a loading spinner while the auth context hydrates from localStorage
 * - Redirects unauthenticated users to /login
 * - Lets the /login page render without Navbar
 * - Wraps authenticated pages with Navbar + main
 */
export function AuthShell({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isLoginPage = pathname === "/login";

  useEffect(() => {
    if (!isLoading && !user && !isLoginPage) {
      router.replace("/login");
    }
    if (!isLoading && user && isLoginPage) {
      router.replace("/");
    }
  }, [isLoading, user, isLoginPage, router]);

  // While hydrating
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0a0a0f]">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  // Login page — no Navbar, full-screen
  if (isLoginPage) {
    return <>{children}</>;
  }

  // Not logged in but not on login page — will redirect (show spinner meanwhile)
  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0a0a0f]">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  // Authenticated — normal layout
  return (
    <>
      <Navbar />
      <main className="min-h-screen">{children}</main>
    </>
  );
}
