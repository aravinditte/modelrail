"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, asArray, num, str, type Row } from "@/lib/api";
import { EmptyState, ErrorState, LoadingState, Stat, formatCost } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

function section(data: unknown, keys: string[]): Row[] {
  if (Array.isArray(data)) return data as Row[];
  if (data && typeof data === "object") {
    const obj = data as Row;
    for (const k of keys) if (Array.isArray(obj[k])) return obj[k] as Row[];
  }
  return [];
}

function groupRequests(requests: Row[], keyField: string): Row[] {
  const map = new Map<string, Row>();
  for (const r of requests) {
    const key = str(r[keyField] ?? r.model_alias ?? r.project_id, "unknown");
    const cur = map.get(key) || { name: key, requests: 0, input_tokens: 0, output_tokens: 0, cost: 0 };
    cur.requests = num(cur.requests) + 1;
    cur.input_tokens = num(cur.input_tokens) + num(r.input_tokens);
    cur.output_tokens = num(cur.output_tokens) + num(r.output_tokens);
    cur.cost = num(cur.cost) + num(r.final_cost ?? r.cost);
    map.set(key, cur);
  }
  return [...map.values()];
}

function UsageTable({ rows, firstCol }: { rows: Row[]; firstCol: string }) {
  if (rows.length === 0) return <EmptyState title="No usage recorded yet" hint="Usage appears after requests are served by the gateway." />;
  return (
    <Table><THead><TR><TH>{firstCol}</TH><TH>Requests</TH><TH>Input tokens</TH><TH>Output tokens</TH><TH>Estimated cost</TH></TR></THead>
      <TBody>{rows.map((r, i) => (
        <TR key={i}><TD className="font-medium">{str(r.name ?? r.project_id ?? r.model_alias ?? r.model)}</TD>
          <TD>{num(r.requests ?? r.total_requests ?? r.request_count).toLocaleString()}</TD>
          <TD>{num(r.input_tokens).toLocaleString()}</TD><TD>{num(r.output_tokens).toLocaleString()}</TD>
          <TD>{formatCost(r.cost ?? r.total_cost)}</TD></TR>
      ))}</TBody></Table>
  );
}

export default function UsagePage() {
  const [usage, setUsage] = useState<unknown>(null);
  const [policies, setPolicies] = useState<Row[]>([]);
  const [projects, setProjects] = useState<Row[]>([]);
  const [requests, setRequests] = useState<Row[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [u, pol, proj, req] = await Promise.all([
        api.usage(), api.listPolicies().catch(() => []), api.listProjects().catch(() => []), api.listRequests("?limit=200").catch(() => []),
      ]);
      setUsage(u); setPolicies(asArray<Row>(pol)); setProjects(asArray<Row>(proj)); setRequests(asArray<Row>(req));
    } catch (e) { setError(e); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const byProject = useMemo(() => {
    const rows = section(usage, ["by_project", "projects", "per_project"]);
    return rows.length ? rows : groupRequests(requests, "project_id");
  }, [usage, requests]);
  const byModel = useMemo(() => {
    const rows = section(usage, ["by_model", "models", "per_model"]);
    return rows.length ? rows : groupRequests(requests, "model_alias");
  }, [usage, requests]);

  const budgetRows = useMemo(() => byProject.map((r) => {
    const pid = String(r.project_id ?? r.name ?? "");
    const policy = policies.find((p) => String(p.project_id) === pid);
    const project = projects.find((p) => String(p.id) === pid);
    const limit = num(policy?.budget_limit ?? r.budget_limit);
    const spent = num(r.cost ?? r.total_cost);
    return { name: str(project?.name ?? r.name ?? pid), limit, spent, pct: limit > 0 ? Math.min(100, (spent / limit) * 100) : 0 };
  }).filter((r) => r.limit > 0), [byProject, policies, projects]);

  if (loading) return <LoadingState label="Loading usage…" />;
  if (error) return <ErrorState error={error} onRetry={load} />;

  const totals = (usage && typeof usage === "object" ? ((usage as Row).totals as Row) || (usage as Row) : {}) as Row;
  const totalCost = num(totals.total_cost ?? totals.cost, byProject.reduce((a, r) => a + num(r.cost ?? r.total_cost), 0));
  const totalTokens = num(totals.input_tokens) + num(totals.output_tokens) ||
    byProject.reduce((a, r) => a + num(r.input_tokens) + num(r.output_tokens), 0);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Usage & Budgets</h1>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <Stat label="Estimated cost" value={formatCost(totalCost)} sub="Estimated from configured prices — not provider billing" />
        <Stat label="Total tokens" value={totalTokens.toLocaleString()} />
        <Stat label="Projects with usage" value={String(byProject.length)} />
      </div>

      <Card><CardHeader><CardTitle>Budget utilisation</CardTitle></CardHeader><CardContent>
        {budgetRows.length === 0 ? <EmptyState title="No budgets configured" hint="Set a budget_limit in a project policy to see utilisation here." /> :
          <div className="space-y-4">{budgetRows.map((r, i) => (
            <div key={i}>
              <div className="flex justify-between text-sm"><span className="font-medium">{r.name}</span><span>{formatCost(r.spent)} of {formatCost(r.limit)} ({r.pct.toFixed(1)}%)</span></div>
              <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                <div className={`h-full ${r.pct >= 90 ? "bg-red-500" : r.pct >= 70 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${r.pct}%` }} />
              </div>
            </div>
          ))}</div>}
      </CardContent></Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card><CardHeader><CardTitle>Usage by project</CardTitle></CardHeader><CardContent><UsageTable rows={byProject} firstCol="Project" /></CardContent></Card>
        <Card><CardHeader><CardTitle>Usage by model</CardTitle></CardHeader><CardContent><UsageTable rows={byModel} firstCol="Model" /></CardContent></Card>
      </div>
    </div>
  );
}
