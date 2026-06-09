"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Search, Star, Landmark } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/grants", label: "Grant Search", icon: Landmark },
  { href: "/recipients", label: "Recipient Search", icon: Search },
  { href: "/watchlist", label: "Watchlist", icon: Star },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const showSidebar = pathname !== "/";

  return (
    <div className="flex min-h-screen">
      {showSidebar && (
        <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r bg-background">
          <nav className="flex flex-col gap-1 p-4">
            {navItems.map(({ href, label, icon: Icon }) => {
              const active =
                pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  {label}
                </Link>
              );
            })}
          </nav>
        </aside>
      )}
      <main className="flex-1 px-6 py-8">
        {showSidebar ? (
          <div className="mx-auto max-w-7xl">{children}</div>
        ) : (
          children
        )}
      </main>
    </div>
  );
}
