"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, asArray, num, str, type Row } from "@/lib/api";
import { Badge, EmptyState, ErrorState, LoadingState, Stat, formatCost, formatDate, statusTone } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

function totalsFrom(usage: unknown, requests: Row[]) {
  const u = (usage && typeof usage === "object" ? usage : {}) as Row;
  const t = (u.totals && typeof u.totals === "object" ? (u.totals as Row) : u) as Row;
  const total = num(t.total_requests ?? t.requests ?? t.request_count, requests.length);
  const failed = requests.filter((r) => ["failed", "error"].includes(String(r.status).toLowerCase())).length;
  const success = num(
    t.successful_requests ?? t.success_count,
    total ? total - failed : requests.filter((r) => String(r.status).toLowerCase() === "succeeded").length
  );
  const latencies = requests.map((r) => num(r.total_latency_ms ?? r.latency_ms)).filter((n) => n > 0);
  const avgLatency = num(t.avg_latency_ms ?? t.average_latency_ms, latencies.length ? latencies.reduce((a, b) => a + b, 0) / latencies.length : 0);
  return {
    total,
    successRate: total ? (success / total) * 100 : 0,
    avgLatency,
    inputTokens: num(t.input_tokens ?? t.total_input_tokens, requests.reduce((a, r) => a + num(r.input_tokens), 0)),
    outputTokens: num(t.output_tokens ?? t.total_output_tokens, requests.reduce((a, r) => a + num(r.output_tokens), 0)),
    cost: t.total_cost ?? t.cost ?? requests.reduce((a, r) => a + num(r.final_cost ?? r.cost), 0),
  };
}

export default function OverviewPage() {
  const [usage, setUsage] = useState<unknown>(null);
  const [requests, setRequests] = useState<Row[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [u, r] = await Promise.all([api.usage(), api.listRequests("?limit=50")]);
      setUsage(u); setRequests(asArray<Row>(r));
    } catch (e) { setError(e); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const totals = useMemo(() => totalsFrom(usage, requests), [usage, requests]);
  const failures = useMemo(
    () => requests.filter((r) => ["failed", "error"].includes(String(r.status).toLowerCase())).slice(0, 10),
    [requests]
  );

  if (loading) return <LoadingState label="Loading overview…" />;
  if (error) return <ErrorState error={error} onRetry={load} />;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Overview</h1>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <Stat label="Total requests" value={String(totals.total)} />
        <Stat label="Success rate" value={`${totals.successRate.toFixed(1)}%`} />
        <Stat label="Avg latency" value={totals.avgLatency ? `${Math.round(totals.avgLatency)} ms` : "—"} />
        <Stat label="Input tokens" value={totals.inputTokens.toLocaleString()} />
        <Stat label="Output tokens" value={totals.outputTokens.toLocaleString()} />
        <Stat label="Estimated cost" value={formatCost(totals.cost)} sub="Estimated, not provider billing" />
      </div>

      <Card>
        <CardHeader><CardTitle>Recent failures</CardTitle></CardHeader>
        <CardContent>
          {failures.length === 0 ? (
            <EmptyState title="No recent failures" hint="Failed requests from the latest 50 requests will appear here." />
          ) : (
            <Table>
              <THead><TR><TH>Request</TH><TH>Model</TH><TH>Status</TH><TH>Error</TH><TH>When</TH></TR></THead>
              <TBody>
                {failures.map((r, i) => (
                  <TR key={String(r.id ?? i)}>
                    <TD><Link className="underline" href="/requests">{str(r.id ?? r.request_id)}</Link></TD>
                    <TD>{str(r.model_alias ?? r.model)}</TD>
                    <TD><Badge tone={statusTone(str(r.status, ""))}>{str(r.status)}</Badge></TD>
                    <TD>{str(r.error_code ?? r.error)}</TD>
                    <TD>{formatDate(r.started_at ?? r.created_at)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
