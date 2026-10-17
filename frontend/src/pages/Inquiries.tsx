import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { Plus, Trash2 } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import type { Inquiry, Customer, Material, Availability } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtQty, fmtDate } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface Line { material_id: string; description: string; quantity: string; unit: string }

export default function Inquiries() {
  const qc = useQueryClient();
  const toast = useToast();
  const [params] = useSearchParams();
  const [open, setOpen] = React.useState(params.get("new") === "1");
  const [detail, setDetail] = React.useState<Inquiry | null>(null);
  const [customerId, setCustomerId] = React.useState("");
  const [reference, setReference] = React.useState("");
  const [lines, setLines] = React.useState<Line[]>([{ material_id: "", description: "", quantity: "", unit: "MT" }]);

  const list = useQuery({ queryKey: ["inquiries"], queryFn: () => get<Page<Inquiry>>("/v1/inquiries") });
  const customers = useQuery({ queryKey: ["customers"], queryFn: () => get<Page<Customer>>("/v1/customers?page_size=100") });
  const materials = useQuery({ queryKey: ["materials-all"], queryFn: () => get<Page<Material>>("/v1/materials?page_size=100") });
  const detailAvail = useQuery({
    queryKey: ["inq-avail", detail?.id],
    queryFn: async () => {
      const map: Record<string, Availability> = {};
      await Promise.all((detail?.items ?? [])
        .filter((i) => i.material_id)
        .map(async (i) => {
          const rows = await get<Availability[]>(`/v1/materials/availability?material_id=${i.material_id}`);
          if (rows[0]) map[i.material_id!] = rows[0];
        }));
      return map;
    },
    enabled: !!detail,
  });

  const createMut = useMutation({
    mutationFn: () => post("/v1/inquiries", {
      customer_id: customerId, reference,
      items: lines.filter((l) => l.description || l.material_id).map((l) => ({
        material_id: l.material_id || undefined, description: l.description, quantity: l.quantity, unit: l.unit,
      })),
    }),
    onSuccess: () => { toast.push("success", "Inquiry recorded"); setOpen(false); setLines([{ material_id: "", description: "", quantity: "", unit: "MT" }]); setReference(""); qc.invalidateQueries({ queryKey: ["inquiries"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });

  const cols: ColumnDef<Inquiry, unknown>[] = [
    { accessorKey: "reference", header: "Reference", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "customer_name", header: "Customer" },
    { id: "items", header: "Requirement", cell: (c) => (
      <span className="text-xs">{c.row.original.items.map((i) => `${i.material_name ?? i.description} ${fmtQty(i.quantity, i.unit)}`).join(", ")}</span>) },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "received_at", header: "Received", cell: (c) => <span className="text-xs text-muted-foreground">{fmtDate(c.getValue() as string)}</span> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Customer Inquiries</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} inquiries</p></div>
        <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New inquiry</Button>
      </div>

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} onRowClick={setDetail} emptyTitle="No inquiries yet" /></Card>}

      {/* Detail modal with availability */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={`Inquiry ${detail?.reference ?? ""}`} wide>
        {detail && (
          <div className="space-y-4">
            <div className="flex items-center gap-4 text-sm">
              <span className="font-medium">{detail.customer_name}</span>
              <Badge value={detail.status} />
              <span className="text-xs text-muted-foreground">Received {fmtDate(detail.received_at)}</span>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="py-2">Item</th><th>Grade</th><th>Qty</th><th>Available</th><th>Shortfall</th>
              </tr></thead>
              <tbody>
                {detail.items.map((it) => {
                  const av = it.material_id ? detailAvail.data?.[it.material_id] : undefined;
                  const shortfall = av ? Math.max(0, Number(it.quantity) - Number(av.available)) : null;
                  return (
                    <tr key={it.id} className="border-b border-border/50">
                      <td className="py-2 font-medium">{it.material_name ?? it.description}</td>
                      <td>{it.grade ?? "—"}</td>
                      <td className="tabular-nums">{fmtQty(it.quantity, it.unit)}</td>
                      <td className="tabular-nums">{av ? fmtQty(av.available) : "…"}</td>
                      <td className={`tabular-nums font-semibold ${shortfall && shortfall > 0 ? "text-red-600" : "text-emerald-600"}`}>
                        {shortfall === null ? "…" : shortfall > 0 ? fmtQty(shortfall) : "Covered"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="flex justify-end">
              <Button size="sm" onClick={() => { window.location.href = `/quotations?new=1&inquiry=${detail.id}&customer=${detail.customer_id}`; }}>
                Create quotation →
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Create modal */}
      <Modal open={open} onClose={() => setOpen(false)} title="New customer inquiry" wide>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Customer</Label>
              <Select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                <option value="">Select customer…</option>
                {customers.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select></div>
            <div><Label>Reference</Label><Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="RFQ-2026-114" /></div>
          </div>
          <div>
            <Label>Requirement lines</Label>
            {lines.map((l, i) => (
              <div key={i} className="mb-2 grid grid-cols-[1fr_1fr_90px_80px_36px] items-end gap-2">
                <Select value={l.material_id} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, material_id: e.target.value } : x))}>
                  <option value="">Material…</option>
                  {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </Select>
                <Input value={l.description} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, description: e.target.value } : x))} placeholder="Description" />
                <Input value={l.quantity} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, quantity: e.target.value } : x))} placeholder="Qty" />
                <Select value={l.unit} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, unit: e.target.value } : x))}>
                  <option>MT</option><option>KG</option><option>NOS</option>
                </Select>
                <Button variant="ghost" size="sm" aria-label="Remove line"
                  onClick={() => setLines(lines.filter((_, j) => j !== i))} disabled={lines.length === 1}>
                  <Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => setLines([...lines, { material_id: "", description: "", quantity: "", unit: "MT" }])}>
              <Plus className="h-3.5 w-3.5" /> Add line
            </Button>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button loading={createMut.isPending}
              disabled={!customerId || !reference || !lines.some((l) => l.description && l.quantity)}
              onClick={() => createMut.mutate()}>Record inquiry</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
