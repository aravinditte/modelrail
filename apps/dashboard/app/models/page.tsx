"use client";
import { useCallback, useEffect, useState } from "react";
import { api, asArray, str, type Row } from "@/lib/api";
import { Badge, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const emptyForm = { alias: "", provider: "mock", upstream_model: "", priority: "100", capabilities: "chat,streaming" };

export default function ModelsPage() {
  const [models, setModels] = useState<Row[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setModels(asArray<Row>(await api.listModels())); }
    catch (e) { setError(e); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setActionError("");
    const body: Row = {
      alias: form.alias, provider: form.provider, upstream_model: form.upstream_model,
      priority: Number(form.priority),
      capabilities: form.capabilities.split(",").map((s) => s.trim()).filter(Boolean),
      enabled: true,
    };
    try {
      if (editingId !== null) await api.updateModel(editingId, body);
      else await api.createModel(body);
      setForm(emptyForm); setEditingId(null); await load();
    } catch (err) { setActionError(err instanceof Error ? err.message : "Save failed"); }
  }

  if (loading) return <LoadingState label="Loading models…" />;
  if (error) return <ErrorState error={error} onRetry={load} />;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Models & Routes</h1>
      {actionError && <ErrorState error={new Error(actionError)} />}
      <Card>
        <CardHeader><CardTitle>{editingId !== null ? "Edit route" : "Add route"}</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <div><Label>Alias</Label><Input required value={form.alias} onChange={(e) => setForm({ ...form, alias: e.target.value })} placeholder="fast-chat" /></div>
            <div><Label>Provider</Label>
              <select className="h-9 w-full rounded-md border border-zinc-300 bg-transparent px-2 text-sm dark:border-zinc-700" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}>
                <option value="mock">mock</option><option value="ollama">ollama</option><option value="remote">remote</option>
              </select></div>
            <div><Label>Upstream model</Label><Input required value={form.upstream_model} onChange={(e) => setForm({ ...form, upstream_model: e.target.value })} placeholder="mock-echo" /></div>
            <div><Label>Priority</Label><Input type="number" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></div>
            <div><Label>Capabilities (comma)</Label><Input value={form.capabilities} onChange={(e) => setForm({ ...form, capabilities: e.target.value })} /></div>
            <div className="col-span-2 flex gap-2">
              <Button type="submit">{editingId !== null ? "Update route" : "Create route"}</Button>
              {editingId !== null && <Button type="button" variant="outline" onClick={() => { setEditingId(null); setForm(emptyForm); }}>Cancel</Button>}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {models.length === 0 ? (
            <EmptyState title="No model routes yet" hint="Create the first route above — e.g. alias fast-chat on the mock provider." />
          ) : (
            <Table>
              <THead><TR><TH>Alias</TH><TH>Provider</TH><TH>Upstream model</TH><TH>Priority</TH><TH>Enabled</TH><TH>Capabilities</TH><TH /></TR></THead>
              <TBody>
                {models.map((m, i) => (
                  <TR key={String(m.id ?? i)}>
                    <TD className="font-medium">{str(m.alias)}</TD>
                    <TD>{str(m.provider)}</TD>
                    <TD>{str(m.upstream_model)}</TD>
                    <TD>{str(m.priority)}</TD>
                    <TD><Badge tone={m.enabled === false ? "red" : "green"}>{m.enabled === false ? "disabled" : "enabled"}</Badge></TD>
                    <TD>{Array.isArray(m.capabilities) ? (m.capabilities as unknown[]).join(", ") : str(m.capabilities)}</TD>
                    <TD><Button variant="outline" onClick={() => {
                      setEditingId((m.id as string | number) ?? null);
                      setForm({
                        alias: str(m.alias, ""), provider: str(m.provider, "mock"), upstream_model: str(m.upstream_model, ""),
                        priority: String(m.priority ?? 100),
                        capabilities: Array.isArray(m.capabilities) ? (m.capabilities as unknown[]).join(",") : str(m.capabilities, ""),
                      });
                    }}>Edit</Button></TD>
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
