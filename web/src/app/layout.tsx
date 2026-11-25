import type { Metadata } from "next";
import { Navbar } from "@/components/Navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kotone.binder — tripleS Photocard Companion",
  description:
    "Companion web binder, era completion tracker, and leaderboards for the Kotone Discord bot.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased selection:bg-[#ff6b8b]/30 selection:text-white">
        <div className="binder-grid-bg flex min-h-screen flex-col">
          <Navbar />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
            {children}
          </main>
          <footer className="border-t border-white/10 bg-[#07070d]/70 py-6 text-center text-xs text-zinc-500">
            Kotone Bot Companion • Phase 1 Read-Only Mode • Shared SQLite WAL
            Database
          </footer>
        </div>
      </body>
    </html>
  );
}
