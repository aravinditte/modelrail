"use client";
import { useCallback, useEffect, useState } from "react";
import { api, asArray, str, type Row } from "@/lib/api";
import { Badge, EmptyState, ErrorState, LoadingState, formatDate } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Row[]>([]);
  const [keys, setKeys] = useState<Row[]>([]);
  const [policies, setPolicies] = useState<Row[]>([]);
  const [projectForm, setProjectForm] = useState({ name: "", organization_id: "" });
  const [keyForm, setKeyForm] = useState({ project_id: "" });
  const [policyForm, setPolicyForm] = useState({
    project_id: "", allowed_models: "", requests_per_minute: "60", tokens_per_minute: "100000",
    max_concurrency: "10", max_output_tokens: "4096", budget_limit: "100", routing_policy: "priority",
  });
  const [editingPolicy, setEditingPolicy] = useState<string | number | null>(null);
  const [newKey, setNewKey] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [p, k, pol] = await Promise.all([api.listProjects(), api.listKeys(), api.listPolicies()]);
      setProjects(asArray<Row>(p)); setKeys(asArray<Row>(k)); setPolicies(asArray<Row>(pol));
    } catch (e) { setError(e); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function createProject(e: React.FormEvent) {
    e.preventDefault(); setActionError("");
    try {
      const body: Row = { name: projectForm.name };
      if (projectForm.organization_id) body.organization_id = projectForm.organization_id;
      await api.createProject(body); setProjectForm({ name: "", organization_id: "" }); await load();
    } catch (err) { setActionError(err instanceof Error ? err.message : "Create failed"); }
  }

  async function createKey(e: React.FormEvent) {
    e.preventDefault(); setActionError(""); setNewKey("");
    try {
      const created = await api.createKey({ project_id: keyForm.project_id });
      const plaintext = String(created.api_key ?? created.key ?? created.plaintext ?? "");
      if (plaintext) setNewKey(plaintext);
      await load();
    } catch (err) { setActionError(err instanceof Error ? err.message : "Key creation failed"); }
  }

  async function revoke(id: string | number) {
    if (!window.confirm("Revoke this API key? Clients using it will stop working immediately.")) return;
    setActionError("");
    try { await api.revokeKey(id); await load(); }
    catch (err) { setActionError(err instanceof Error ? err.message : "Revoke failed"); }
  }

  async function savePolicy(e: React.FormEvent) {
    e.preventDefault(); setActionError("");
    const body: Row = {
      project_id: policyForm.project_id,
      allowed_models: policyForm.allowed_models.split(",").map((s) => s.trim()).filter(Boolean),
      requests_per_minute: Number(policyForm.requests_per_minute),
      tokens_per_minute: Number(policyForm.tokens_per_minute),
      max_concurrency: Number(policyForm.max_concurrency),
      max_output_tokens: Number(policyForm.max_output_tokens),
      budget_limit: policyForm.budget_limit,
      routing_policy: policyForm.routing_policy,
    };
    try {
      if (editingPolicy !== null) await api.updatePolicy(editingPolicy, body);
      else await api.createPolicy(body);
      setEditingPolicy(null); await load();
    } catch (err) { setActionError(err instanceof Error ? err.message : "Policy save failed"); }
  }

  if (loading) return <LoadingState label="Loading projects…" />;
  if (error) return <ErrorState error={error} onRetry={load} />;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Projects, API Keys & Policies</h1>
      {actionError && <ErrorState error={new Error(actionError)} />}
      {newKey && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-4 dark:border-amber-800 dark:bg-amber-950/40" role="alert">
          <p className="text-sm font-semibold">Your new API key — shown only once. Copy it now:</p>
          <code className="mt-2 block break-all rounded bg-white px-3 py-2 text-sm dark:bg-zinc-900">{newKey}</code>
          <div className="mt-3 flex gap-2">
            <Button onClick={() => navigator.clipboard?.writeText(newKey)}>Copy key</Button>
            <Button variant="outline" onClick={() => setNewKey("")}>I saved it — dismiss</Button>
          </div>
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Projects</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={createProject} className="flex flex-wrap items-end gap-3">
            <div className="min-w-52 flex-1"><Label>Project name</Label><Input required value={projectForm.name} onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })} /></div>
            <div className="min-w-52 flex-1"><Label>Organization ID (if required)</Label><Input value={projectForm.organization_id} onChange={(e) => setProjectForm({ ...projectForm, organization_id: e.target.value })} /></div>
            <Button type="submit">Create project</Button>
          </form>
          {projects.length === 0 ? <EmptyState title="No projects yet" /> : (
            <Table><THead><TR><TH>ID</TH><TH>Name</TH><TH>Organization</TH><TH>Status</TH><TH>Created</TH></TR></THead>
              <TBody>{projects.map((p, i) => (
                <TR key={String(p.id ?? i)}><TD className="font-mono text-xs">{str(p.id)}</TD><TD className="font-medium">{str(p.name)}</TD><TD>{str(p.organization_id)}</TD><TD><Badge tone={String(p.status).toLowerCase() === "active" ? "green" : "neutral"}>{str(p.status, "active")}</Badge></TD><TD>{formatDate(p.created_at)}</TD></TR>
              ))}</TBody></Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>API keys</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={createKey} className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1"><Label>Project</Label>
              <select required className="h-9 w-full rounded-md border border-zinc-300 bg-transparent px-2 text-sm dark:border-zinc-700" value={keyForm.project_id} onChange={(e) => setKeyForm({ project_id: e.target.value })}>
                <option value="">Select a project…</option>
                {projects.map((p) => <option key={String(p.id)} value={String(p.id)}>{str(p.name)} ({str(p.id)})</option>)}
              </select></div>
            <Button type="submit">Create key</Button>
          </form>
          <p className="text-xs text-zinc-500">Plaintext keys are shown once at creation and never stored or displayed again — only prefixes/hashes are listed here.</p>
          {keys.length === 0 ? <EmptyState title="No API keys yet" /> : (
            <Table><THead><TR><TH>ID</TH><TH>Project</TH><TH>Prefix</TH><TH>Created</TH><TH>Expires</TH><TH>Status</TH><TH /></TR></THead>
              <TBody>{keys.map((k, i) => {
                const revoked = Boolean(k.revoked_at);
                return (
                  <TR key={String(k.id ?? i)}><TD className="font-mono text-xs">{str(k.id)}</TD><TD>{str(k.project_id)}</TD><TD className="font-mono">{str(k.key_prefix ?? k.prefix)}</TD><TD>{formatDate(k.created_at)}</TD><TD>{formatDate(k.expires_at)}</TD>
                    <TD><Badge tone={revoked ? "red" : "green"}>{revoked ? "revoked" : "active"}</Badge></TD>
                    <TD>{!revoked && k.id != null && <Button variant="destructive" onClick={() => revoke(k.id as string | number)}>Revoke</Button>}</TD></TR>
                );
              })}</TBody></Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Policies {editingPolicy !== null ? "(editing)" : ""}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={savePolicy} className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div><Label>Project ID</Label><Input required value={policyForm.project_id} onChange={(e) => setPolicyForm({ ...policyForm, project_id: e.target.value })} /></div>
            <div><Label>Allowed models (comma)</Label><Input value={policyForm.allowed_models} onChange={(e) => setPolicyForm({ ...policyForm, allowed_models: e.target.value })} placeholder="fast-chat, quality-chat" /></div>
            <div><Label>Requests / min</Label><Input type="number" value={policyForm.requests_per_minute} onChange={(e) => setPolicyForm({ ...policyForm, requests_per_minute: e.target.value })} /></div>
            <div><Label>Tokens / min</Label><Input type="number" value={policyForm.tokens_per_minute} onChange={(e) => setPolicyForm({ ...policyForm, tokens_per_minute: e.target.value })} /></div>
            <div><Label>Max concurrency</Label><Input type="number" value={policyForm.max_concurrency} onChange={(e) => setPolicyForm({ ...policyForm, max_concurrency: e.target.value })} /></div>
            <div><Label>Max output tokens</Label><Input type="number" value={policyForm.max_output_tokens} onChange={(e) => setPolicyForm({ ...policyForm, max_output_tokens: e.target.value })} /></div>
            <div><Label>Budget limit</Label><Input value={policyForm.budget_limit} onChange={(e) => setPolicyForm({ ...policyForm, budget_limit: e.target.value })} /></div>
            <div><Label>Routing policy</Label>
              <select className="h-9 w-full rounded-md border border-zinc-300 bg-transparent px-2 text-sm dark:border-zinc-700" value={policyForm.routing_policy} onChange={(e) => setPolicyForm({ ...policyForm, routing_policy: e.target.value })}>
                <option value="priority">priority</option><option value="cost">cost</option><option value="latency">latency</option>
              </select></div>
            <div className="col-span-2 flex gap-2"><Button type="submit">{editingPolicy !== null ? "Update policy" : "Create policy"}</Button>
              {editingPolicy !== null && <Button type="button" variant="outline" onClick={() => setEditingPolicy(null)}>Cancel</Button>}</div>
          </form>
          {policies.length === 0 ? <EmptyState title="No policies yet" hint="Without a policy, project limits may be unrestricted depending on gateway defaults." /> : (
            <Table><THead><TR><TH>Project</TH><TH>Allowed models</TH><TH>RPM</TH><TH>Budget</TH><TH>Routing</TH><TH /></TR></THead>
              <TBody>{policies.map((p, i) => (
                <TR key={String(p.id ?? i)}><TD>{str(p.project_id)}</TD><TD>{Array.isArray(p.allowed_models) ? (p.allowed_models as unknown[]).join(", ") : str(p.allowed_models)}</TD><TD>{str(p.requests_per_minute)}</TD><TD>{str(p.budget_limit)}</TD><TD>{str(p.routing_policy)}</TD>
                  <TD><Button variant="outline" onClick={() => {
                    setEditingPolicy((p.id as string | number) ?? null);
                    setPolicyForm({
                      project_id: str(p.project_id, ""), allowed_models: Array.isArray(p.allowed_models) ? (p.allowed_models as unknown[]).join(",") : "",
                      requests_per_minute: String(p.requests_per_minute ?? 60), tokens_per_minute: String(p.tokens_per_minute ?? 100000),
                      max_concurrency: String(p.max_concurrency ?? 10), max_output_tokens: String(p.max_output_tokens ?? 4096),
                      budget_limit: String(p.budget_limit ?? ""), routing_policy: str(p.routing_policy, "priority"),
                    });
                  }}>Edit</Button></TD></TR>
              ))}</TBody></Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
