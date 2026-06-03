"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FlaskConical, Play, Wand2,
  Download, Settings, Mic,
} from "lucide-react";
import { clsx } from "clsx";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/test-cases", label: "Test Cases", icon: FlaskConical },
  { href: "/runs", label: "Runs", icon: Play },
  { href: "/generate", label: "Generate", icon: Wand2 },
  { href: "/ingest", label: "Ingest Calls", icon: Download },
  { href: "/settings", label: "Providers", icon: Settings },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="w-56 bg-brand-900 text-white flex flex-col flex-shrink-0">
      <div className="flex items-center gap-2 px-4 py-5 border-b border-white/10">
        <Mic className="text-brand-500 w-5 h-5" />
        <span className="font-bold text-lg tracking-tight">Vyuha</span>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
              path === href
                ? "bg-brand-500 text-white"
                : "text-white/70 hover:text-white hover:bg-white/10"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </nav>

      <div className="p-4 text-xs text-white/30 border-t border-white/10">
        v0.1.0 · Phase 3
      </div>
    </aside>
  );
}
