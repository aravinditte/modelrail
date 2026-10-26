"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL, clearToken, getToken, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/models", label: "Models & Routes" },
  { href: "/projects", label: "Projects & Keys" },
  { href: "/requests", label: "Requests" },
  { href: "/usage", label: "Usage & Budgets" },
  { href: "/evaluations", label: "Evaluations" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [token, setTokenState] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => setTokenState(getToken()), []);

  function save() {
    setToken(token.trim());
    setSaved(true);
    setTimeout(() => window.location.reload(), 250);
  }
  function clear() {
    clearToken();
    setTokenState("");
    window.location.reload();
  }

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3">
          <Link href="/" className="text-lg font-bold tracking-tight">ModelRail</Link>
          <span className="hidden text-xs text-zinc-500 sm:inline">Admin · {API_URL}</span>
          <div className="ml-auto flex items-center gap-2">
            <Input
              type="password"
              value={token}
              onChange={(e) => setTokenState(e.target.value)}
              placeholder="X-Admin-Token"
              className="w-56"
              aria-label="Admin token"
              onKeyDown={(e) => e.key === "Enter" && save()}
            />
            <Button onClick={save}>{saved ? "Saved" : "Save token"}</Button>
            {token && <Button variant="ghost" onClick={clear}>Clear</Button>}
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-2">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium ${
                pathname === n.href
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                  : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
              }`}
            >
              {n.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-zinc-400">
        Prompts and provider secrets are not displayed by this dashboard.
      </footer>
    </div>
  );
}
