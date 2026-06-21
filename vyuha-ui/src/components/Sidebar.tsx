"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FlaskConical, Play, Settings, Mic, BarChart3,
  Database, Activity, FileText, Bot, MessageSquare, Bell,
} from "lucide-react";
import { clsx } from "clsx";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/test-cases", label: "Test Cases", icon: FlaskConical },
  { href: "/runs", label: "Runs", icon: Play },
  { href: "/evaluators", label: "Eval Studio", icon: BarChart3 },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/traces", label: "Traces", icon: Activity },
  { href: "/prompts", label: "Prompts", icon: FileText },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/annotations", label: "Annotations", icon: MessageSquare },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/settings", label: "Providers", icon: Settings },
];

export function Sidebar() {
  const path = usePathname();

  const isTestCases = path.startsWith("/test-cases") || path === "/generate"
    || path === "/ingest" || path === "/workflows";

  return (
    <aside className="w-56 bg-brand-900 text-white flex flex-col flex-shrink-0">
      <div className="flex items-center gap-2 px-4 py-5 border-b border-white/10">
        <Mic className="text-brand-500 w-5 h-5" />
        <span className="font-bold text-lg tracking-tight">Vyuha</span>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/test-cases" ? isTestCases : path === href;
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                active
                  ? "bg-brand-500 text-white"
                  : "text-white/70 hover:text-white hover:bg-white/10"
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-3 text-xs text-white/20 border-t border-white/10">
        v0.1.0
      </div>
    </aside>
  );
}
