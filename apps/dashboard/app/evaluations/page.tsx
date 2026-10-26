"use client";
import { useState } from "react";
import { api, num, str, type Row } from "@/lib/api";
import { Badge, EmptyState, ErrorState, LoadingState, statusTone } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

function regressionOf(run: Row | null): { label: string; tone: "green" | "red" | "amber" | "neutral" } {
  if (!run) return { label: "—", tone: "neutral" };
  const summary = (run.summary && typeof run.summary === "object" ? (run.summary as Row) : {}) as Row;
  const gate = (summary.gate && typeof summary.gate === "object" ? (summary.gate as Row) : {}) as Row;
  const flag = gate.passed ?? summary.regression_passed ?? summary.gate_passed ?? run.regression_passed ?? (run as Row).gate_passed;
  if (flag === true) return { label: "Gate passed — no regression", tone: "green" };
  if (flag === false) return { label: "REGRESSION — gate failed", tone: "red" };
  const s = String(run.status || "").toLowerCase();
  if (s === "regressed" || s === "failed" || s === "regression") return { label: "REGRESSION — gate failed", tone: "red" };
  if (s === "passed" || s === "completed" || s === "succeeded") return { label: "Completed (no gate verdict field)", tone: "amber" };
  return { label: str(run.status, "unknown"), tone: "neutral" };
}

function MetricTiles({ run }: { run: Row }) {
  const summary = (run.summary && typeof run.summary === "object" ? (run.summary as Row) : run) as Row;
  const entries = Object.entries(summary).filter(([, v]) => typeof v === "number" || typeof v === "string").slice(0, 12);
  if (entries.length === 0) return <EmptyState title="No summary metrics" hint="The worker may still be running, or this run reported no metrics." />;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
          <p className="text-xs uppercase tracking-wide text-zinc-500">{k.replaceAll("_", " ")}</p>
          <p className="mt-1 text-lg font-semibold">{typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : v.toFixed(4)) : String(v)}</p>
        </div>
      ))}
    </div>
  );
}

export default function EvaluationsPage() {
  const [form, setForm] = useState({ dataset_version: "v1", candidate_model: "", baseline_model: "", configuration_version: "default" });
  const [lookupId, setLookupId] = useState("");
  const [run, setRun] = useState<Row | null>(null);
  const [results, setResults] = useState<Row[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);

  async function fetchRun(id: string | number) {
    setLoadingReport(true); setError(null);
    try {
      const data = await api.getEvaluation(id);
      setRun(data);
      const rows = (data as Row).results;
      setResults(Array.isArray(rows) ? (rows as Row[]) : []);
    } catch (e) { setError(e); setRun(null); } finally { setLoadingReport(false); }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setActionError(""); setBusy(true);
    try {
      const created = await api.createEvaluation({ ...form });
      if (created.id != null) { setLookupId(String(created.id)); await fetchRun(created.id as string | number); }
      else setRun(created);
    } catch (err) { setActionError(err instanceof Error ? err.message : "Failed to start evaluation"); }
    finally { setBusy(false); }
  }

  const regression = regressionOf(run);
  const summary = run?.summary && typeof run.summary === "object" ? (run.summary as Row) : null;
  const caseRows: Row[] = results.length ? results : (Array.isArray(summary?.results) ? (summary!.results as Row[]) : []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Evaluations</h1>
      {actionError && <ErrorState error={new Error(actionError)} />}

      <Card>
        <CardHeader><CardTitle>Run an evaluation</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div><Label>Dataset version</Label><Input required value={form.dataset_version} onChange={(e) => setForm({ ...form, dataset_version: e.target.value })} /></div>
            <div><Label>Candidate model (alias)</Label><Input required value={form.candidate_model} onChange={(e) => setForm({ ...form, candidate_model: e.target.value })} placeholder="fast-chat" /></div>
            <div><Label>Baseline model (alias)</Label><Input value={form.baseline_model} onChange={(e) => setForm({ ...form, baseline_model: e.target.value })} placeholder="fast-chat" /></div>
            <div><Label>Configuration version</Label><Input value={form.configuration_version} onChange={(e) => setForm({ ...form, configuration_version: e.target.value })} /></div>
            <div className="col-span-2"><Button type="submit" disabled={busy}>{busy ? "Starting…" : "Start evaluation"}</Button></div>
          </form>
          <form className="mt-5 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); if (lookupId) fetchRun(lookupId); }}>
            <div className="min-w-64 flex-1"><Label>Load report by evaluation ID</Label><Input value={lookupId} onChange={(e) => setLookupId(e.target.value)} /></div>
            <Button type="submit" variant="outline">Load report</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Evaluation report</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {loadingReport ? <LoadingState label="Loading report…" /> : error ? <ErrorState error={error} onRetry={() => lookupId && fetchRun(lookupId)} /> : !run ? (
            <EmptyState title="No report loaded" hint="Start an evaluation above or load one by ID. A deliberately degraded candidate should fail the regression gate." />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <Badge tone={regression.tone}>{regression.label}</Badge>
                <span className="text-sm text-zinc-500">Status: {str(run.status)} · Dataset: {str(run.dataset_version)} · Candidate: {str(run.candidate_model)} · Baseline: {str(run.baseline_model)}</span>
              </div>
              <MetricTiles run={run} />
              {caseRows.length > 0 && (
                <Table><THead><TR><TH>Case</TH><TH>Status</TH><TH>Latency</TH><TH>Tokens (in/out)</TH><TH>Failure reason</TH></TR></THead>
                  <TBody>{caseRows.slice(0, 50).map((r, i) => (
                    <TR key={String(r.id ?? i)}><TD>{str(r.case_id ?? r.id)}</TD><TD><Badge tone={statusTone(str(r.status, ""))}>{str(r.status)}</Badge></TD>
                      <TD>{r.latency_ms ? `${num(r.latency_ms)} ms` : "—"}</TD><TD>{num(r.input_tokens)} / {num(r.output_tokens)}</TD><TD>{str(r.failure_reason)}</TD></TR>
                  ))}</TBody></Table>
              )}
              <details className="text-sm">
                <summary className="cursor-pointer font-medium">Raw summary JSON</summary>
                <pre className="mt-2 overflow-x-auto rounded bg-zinc-100 p-3 text-xs dark:bg-zinc-800">{JSON.stringify(summary ?? run, null, 2)}</pre>
              </details>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
