import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { AuthShell } from "@/components/layout/AuthShell";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ThirdEye AI — Financial Document Analyzer",
  description:
    "AI-powered multi-agent platform for bank statement analysis: extraction, insights, tampering detection, and fraud detection.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} antialiased`}>
        <AuthProvider>
          <AuthShell>{children}</AuthShell>
        </AuthProvider>
      </body>
    </html>
  );
}
