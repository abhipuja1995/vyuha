"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, FlaskConical, Play, Settings, Mic, BarChart3,
} from "lucide-react";
import { clsx } from "clsx";
import { apiFetch, ActiveLLM } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/test-cases", label: "Test Cases", icon: FlaskConical },
  { href: "/runs", label: "Runs", icon: Play },
  { href: "/evaluators", label: "Eval Studio", icon: BarChart3 },
  { href: "/settings", label: "Providers", icon: Settings },
];

function ActiveLLMBadge() {
  const { data } = useQuery({
    queryKey: ["active-llm"],
    queryFn: () => apiFetch<ActiveLLM>("/api/active-llm"),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });

  if (!data || !data.configured) return (
    <div className="px-4 pb-3">
      <span className="text-xs text-white/20 italic">No LLM configured</span>
    </div>
  );

  const [prefix, model] = data.provider.split("/");
  return (
    <div className="px-4 pb-3">
      <div className="bg-white/5 rounded-lg px-2.5 py-1.5">
        <p className="text-xs text-white/30 mb-0.5">Active LLM</p>
        <p className="text-xs text-white/70 font-medium truncate">{model ?? data.provider}</p>
        <p className="text-xs text-brand-400 capitalize">{prefix}</p>
      </div>
    </div>
  );
}

export function Sidebar() {
  const path = usePathname();

  // Test Cases is active for all sub-routes: /test-cases, /generate (now merged), /ingest, /workflows
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

      <ActiveLLMBadge />

      <div className="px-4 py-3 text-xs text-white/20 border-t border-white/10">
        v0.1.0 · Phase 3
      </div>
    </aside>
  );
}
