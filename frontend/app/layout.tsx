import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Publicus — Grants Intelligence",
  description:
    "Discover Canadian government grants you're eligible for and see what similar companies are winning.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-40 border-b bg-background">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
            <Link href="/" className="flex items-center gap-2">
              <span className="grid h-6 w-6 place-items-center rounded bg-primary text-xs font-bold text-primary-foreground">
                P
              </span>
              <span className="font-semibold tracking-tight">Publicus</span>
              <span className="hidden text-sm text-muted-foreground sm:inline">
                Grants Intelligence
              </span>
            </Link>
            <nav className="flex items-center gap-6 text-sm font-medium text-muted-foreground">
              <Link href="/dashboard" className="transition-colors hover:text-foreground">
                Dashboard
              </Link>
              <Link href="/recipients" className="transition-colors hover:text-foreground">
                Recipient Search
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
