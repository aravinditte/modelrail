"use client";
import { useCallback, useEffect, useState } from "react";
import { api, asArray, num, str, type Row } from "@/lib/api";
import { Badge, EmptyState, ErrorState, LoadingState, formatCost, formatDate, statusTone } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function RequestsPage() {
  const [requests, setRequests] = useState<Row[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [model, setModel] = useState("");
  const [selected, setSelected] = useState<(Row & { attempts?: Row[] }) | null>(null);
  const [detailError, setDetailError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    const params = new URLSearchParams();
    params.set("limit", "100");
    if (status) params.set("status", status);
    if (model) params.set("model_alias", model);
    if (search) params.set("search", search);
    try {
      const rows = asArray<Row>(await api.listRequests(`?${params.toString()}`));
      // Client-side fallback filtering in case the API ignores a filter param.
      setRequests(rows.filter((r) =>
        (!search || String(r.id ?? r.request_id ?? "").includes(search)) &&
        (!status || String(r.status).toLowerCase() === status) &&
        (!model || String(r.model_alias ?? r.model ?? "").includes(model))
      ));
    } catch (e) { setError(e); } finally { setLoading(false); }
  }, [search, status, model]);
  useEffect(() => { load(); }, [load]);

  async function openDetail(id: string | number) {
    setDetailError(null); setSelected(null);
    try { setSelected(await api.getRequest(id)); }
    catch (e) { setDetailError(e); }
  }

  if (loading) return <LoadingState label="Loading requests…" />;
  if (error) return <ErrorState error={error} onRetry={load} />;

  const attempts: Row[] = selected?.attempts && Array.isArray(selected.attempts) ? selected.attempts : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Requests & Traces</h1>
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 pt-5">
          <div className="min-w-48 flex-1"><Label>Search by request ID</Label><Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="req_…" /></div>
          <div><Label>Status</Label>
            <select className="h-9 rounded-md border border-zinc-300 bg-transparent px-2 text-sm dark:border-zinc-700" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option><option value="succeeded">succeeded</option><option value="failed">failed</option><option value="running">running</option>
            </select></div>
          <div><Label>Model alias</Label><Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="fast-chat" /></div>
          <Button variant="outline" onClick={load}>Refresh</Button>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardContent className="pt-5">
            {requests.length === 0 ? <EmptyState title="No requests match" hint="Send a chat completion through the gateway, or clear the filters." /> : (
              <Table><THead><TR><TH>Request</TH><TH>Model</TH><TH>Status</TH><TH>Latency</TH><TH>When</TH></TR></THead>
                <TBody>{requests.map((r, i) => {
                  const id = (r.id ?? r.request_id) as string | number | undefined;
                  return (
                    <TR key={String(id ?? i)} className="cursor-pointer" onClick={() => id != null && openDetail(id)}>
                      <TD className="max-w-40 truncate font-mono text-xs">{str(id)}</TD>
                      <TD>{str(r.model_alias ?? r.model)}</TD>
                      <TD><Badge tone={statusTone(str(r.status, ""))}>{str(r.status)}</Badge></TD>
                      <TD>{r.total_latency_ms ? `${num(r.total_latency_ms)} ms` : "—"}</TD>
                      <TD>{formatDate(r.started_at ?? r.created_at)}</TD>
                    </TR>
                  );
                })}</TBody></Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Request detail & attempt timeline</CardTitle></CardHeader>
          <CardContent>
            {detailError ? <ErrorState error={detailError} /> : !selected ? (
              <EmptyState title="Select a request" hint="Click a row to see its provider attempts, usage and errors. Prompts are not shown." />
            ) : (
              <div className="space-y-4">
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <div><dt className="text-zinc-500">Status</dt><dd><Badge tone={statusTone(str(selected.status, ""))}>{str(selected.status)}</Badge></dd></div>
                  <div><dt className="text-zinc-500">Model alias</dt><dd>{str(selected.model_alias ?? selected.model)}</dd></div>
                  <div><dt className="text-zinc-500">Attempts</dt><dd>{str(selected.total_attempts ?? attempts.length)}</dd></div>
                  <div><dt className="text-zinc-500">Latency</dt><dd>{selected.total_latency_ms ? `${num(selected.total_latency_ms)} ms` : "—"}</dd></div>
                  <div><dt className="text-zinc-500">Tokens (in / out)</dt><dd>{num(selected.input_tokens).toLocaleString()} / {num(selected.output_tokens).toLocaleString()}</dd></div>
                  <div><dt className="text-zinc-500">Final cost</dt><dd>{formatCost(selected.final_cost ?? selected.cost)} <span className="text-zinc-500">{str(selected.cost_basis, "")}</span></dd></div>
                  <div><dt className="text-zinc-500">Error</dt><dd>{str(selected.error_code)}</dd></div>
                  <div><dt className="text-zinc-500">Started</dt><dd>{formatDate(selected.started_at)}</dd></div>
                </dl>
                <h4 className="text-sm font-semibold">Provider attempts</h4>
                {attempts.length === 0 ? <EmptyState title="No attempts recorded" /> : (
                  <ol className="space-y-3 border-l-2 border-zinc-200 pl-4 dark:border-zinc-800">
                    {attempts.map((a, i) => (
                      <li key={String(a.id ?? i)} className="relative">
                        <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-zinc-400" />
                        <p className="text-sm font-medium">#{str(a.attempt_number, String(i + 1))} · {str(a.provider)} / {str(a.upstream_model)} — <Badge tone={statusTone(str(a.status, ""))}>{str(a.status)}</Badge></p>
                        <p className="text-xs text-zinc-500">{a.latency_ms ? `${num(a.latency_ms)} ms` : ""} {a.error_code ? `· error: ${str(a.error_code)}` : ""} {a.fallback_reason ? `· fallback: ${str(a.fallback_reason)}` : ""} · cost {formatCost(a.cost)}</p>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
