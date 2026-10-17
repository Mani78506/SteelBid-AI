import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { Plus, Trash2, Send, CheckCircle2, FileDown, ArrowRightCircle } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import type { Quotation, Customer, Material, ComparisonItem, Inquiry } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select, Label, Badge, Modal, ErrorState, Confirm } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney, fmtQty, fmtPct, fmtDate } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import type { ColumnDef } from "@tanstack/react-table";

interface Line { material_id: string; description: string; quantity: string; unit: string; unit_cost: string }

export default function Quotations() {
  const qc = useQueryClient();
  const toast = useToast();
  const { can } = useAuth();
  const [params] = useSearchParams();
  const [open, setOpen] = React.useState(params.get("new") === "1");
  const [detail, setDetail] = React.useState<Quotation | null>(null);
  const [approveConfirm, setApproveConfirm] = React.useState(false);
  const [customerId, setCustomerId] = React.useState(params.get("customer") ?? "");
  const [inquiryId] = React.useState(params.get("inquiry") ?? "");
  const [margin, setMargin] = React.useState("0.12");
  const [lines, setLines] = React.useState<Line[]>([{ material_id: "", description: "", quantity: "", unit: "MT", unit_cost: "" }]);
  const [compareFor, setCompareFor] = React.useState<string | null>(null);

  const list = useQuery({ queryKey: ["quotations"], queryFn: () => get<Page<Quotation>>("/v1/quotations") });
  const customers = useQuery({ queryKey: ["customers"], queryFn: () => get<Page<Customer>>("/v1/customers?page_size=100") });
  const materials = useQuery({ queryKey: ["materials-all"], queryFn: () => get<Page<Material>>("/v1/materials?page_size=100") });
  const inquiries = useQuery({ queryKey: ["inquiries"], queryFn: () => get<Page<Inquiry>>("/v1/inquiries") });
  const comparison = useQuery({
    queryKey: ["supplier-compare", compareFor],
    queryFn: () => get<{ items: ComparisonItem[] }>(`/v1/procurement/compare?material_id=${compareFor}`),
    enabled: !!compareFor,
  });

  const refresh = () => { qc.invalidateQueries({ queryKey: ["quotations"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); qc.invalidateQueries({ queryKey: ["sales-orders"] }); };

  const createMut = useMutation({
    mutationFn: () => post("/v1/quotations", {
      customer_id: customerId, inquiry_id: inquiryId || undefined, target_margin: margin,
      items: lines.filter((l) => l.description && l.quantity && l.unit_cost).map((l) => ({
        material_id: l.material_id || undefined, description: l.description,
        quantity: l.quantity, unit: l.unit, unit_cost: l.unit_cost,
      })),
    }),
    onSuccess: () => { toast.push("success", "Quotation drafted"); setOpen(false); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });
  const submitMut = useMutation({
    mutationFn: (id: string) => post(`/v1/quotations/${id}/submit`),
    onSuccess: () => { toast.push("success", "Submitted for approval"); refresh(); setDetail((d) => d ? { ...d, status: "PENDING_APPROVAL" } : d); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Submit failed"),
  });
  const approveMut = useMutation({
    mutationFn: (id: string) => post(`/v1/quotations/${id}/approve`, { comment: "Approved via UI" }),
    onSuccess: () => { toast.push("success", "Quotation approved — version is now immutable"); setApproveConfirm(false); refresh(); setDetail(null); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Approve failed"),
  });
  const convertMut = useMutation({
    mutationFn: (id: string) => post(`/v1/quotations/${id}/convert`),
    onSuccess: (so) => { toast.push("success", `Converted to sales order ${(so as { number?: string }).number ?? ""}`); refresh(); setDetail(null); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Convert failed"),
  });

  const cols: ColumnDef<Quotation, unknown>[] = [
    { accessorKey: "number", header: "Number", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "customer_name", header: "Customer" },
    { id: "value", header: "Selling value", cell: (c) => <span className="font-semibold tabular-nums">{fmtMoney(c.row.original.versions.at(-1)?.total_selling_price ?? "0")}</span> },
    { id: "margin", header: "Margin", cell: (c) => <span className="tabular-nums">{fmtPct(c.row.original.versions.at(-1)?.gross_margin_pct)}</span> },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "created_at", header: "Created", cell: (c) => <span className="text-xs text-muted-foreground">{fmtDate(c.getValue() as string)}</span> },
  ];
  const setLine = (i: number, patch: Partial<Line>) => setLines(lines.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Quotations</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} quotations · cost-vs-price with target margin</p></div>
        <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New quotation</Button>
      </div>

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} onRowClick={setDetail} emptyTitle="No quotations yet" /></Card>}

      {/* Detail */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={`Quotation ${detail?.number ?? ""}`} wide>
        {detail && (() => {
          const v = detail.versions.at(-1);
          return (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <Badge value={detail.status} />
                <span className="font-medium">{detail.customer_name}</span>
                <span className="text-xs text-muted-foreground">v{v?.version_no} · target margin {fmtPct(detail.target_margin)}</span>
              </div>
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="py-2">Item</th><th>Qty</th><th>Unit cost</th><th>Unit price</th><th>Available</th><th>Shortage</th><th>Line total</th>
                </tr></thead>
                <tbody>
                  {detail.items.map((l) => (
                    <tr key={l.id} className="border-b border-border/50">
                      <td className="py-2 font-medium">{l.description}</td>
                      <td className="tabular-nums">{fmtQty(l.quantity, l.unit)}</td>
                      <td className="tabular-nums">{fmtMoney(l.unit_cost)}</td>
                      <td className="tabular-nums">{fmtMoney(l.unit_price)}</td>
                      <td className="tabular-nums text-emerald-700">{fmtQty(l.available_qty)}</td>
                      <td className={`tabular-nums ${Number(l.shortage_qty) > 0 ? "font-semibold text-red-600" : "text-emerald-700"}`}>{fmtQty(l.shortage_qty)}</td>
                      <td className="tabular-nums font-semibold">{fmtMoney(l.line_selling_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-muted/50 px-4 py-3 text-sm">
                <div className="space-x-6">
                  <span>Cost <b className="tabular-nums">{fmtMoney(v?.total_estimated_cost)}</b></span>
                  <span>Selling <b className="tabular-nums text-primary">{fmtMoney(v?.total_selling_price)}</b></span>
                  <span>Margin <b className="tabular-nums">{fmtPct(v?.gross_margin_pct)}</b></span>
                </div>
                {v?.is_immutable && <Badge value="APPROVED" />}
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                {detail.status === "DRAFT" && (
                  <Button size="sm" onClick={() => submitMut.mutate(detail.id)} loading={submitMut.isPending}>
                    <Send className="h-3.5 w-3.5" /> Submit for approval</Button>)}
                {detail.status === "PENDING_APPROVAL" && can("approvals.write") && (
                  <Button size="sm" variant="accent" onClick={() => setApproveConfirm(true)}>
                    <CheckCircle2 className="h-3.5 w-3.5" /> Approve</Button>)}
                {detail.status === "APPROVED" && (
                  <Button size="sm" onClick={() => convertMut.mutate(detail.id)} loading={convertMut.isPending}>
                    <ArrowRightCircle className="h-3.5 w-3.5" /> Convert to sales order</Button>)}
                <Button size="sm" variant="outline" onClick={() => window.open(`/api/v1/quotations/${detail.id}/export`, "_blank")}>
                  <FileDown className="h-3.5 w-3.5" /> Export</Button>
              </div>
            </div>
          );
        })()}
      </Modal>

      <Confirm open={approveConfirm} onClose={() => setApproveConfirm(false)}
        onConfirm={() => detail && approveMut.mutate(detail.id)} loading={approveMut.isPending}
        title="Approve quotation" message="Approving freezes the current version permanently. The version becomes immutable and can be converted to a sales order." />

      {/* Create */}
      <Modal open={open} onClose={() => setOpen(false)} title="New quotation" wide>
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Customer</Label>
              <Select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                <option value="">Select…</option>
                {customers.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select></div>
            <div><Label>Linked inquiry</Label>
              <Select value={inquiryId} disabled>
                <option value="">{inquiryId ? inquiries.data?.items.find((i) => i.id === inquiryId)?.reference ?? inquiryId : "— none —"}</option>
              </Select></div>
            <div><Label>Target gross margin</Label>
              <Select value={margin} onChange={(e) => setMargin(e.target.value)}>
                <option value="0.08">8%</option><option value="0.10">10%</option>
                <option value="0.12">12%</option><option value="0.15">15%</option><option value="0.20">20%</option>
              </Select></div>
          </div>

          <div>
            <Label>Lines — set unit cost, or pull landed cost from supplier comparison</Label>
            {lines.map((l, i) => (
              <div key={i} className="mb-2 grid grid-cols-[1.2fr_1.4fr_80px_70px_110px_auto_36px] items-end gap-2">
                <Select value={l.material_id} onChange={(e) => setLine(i, { material_id: e.target.value })}>
                  <option value="">Material…</option>
                  {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </Select>
                <Input value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} placeholder="Description" />
                <Input value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} placeholder="Qty" />
                <Select value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })}>
                  <option>MT</option><option>KG</option><option>NOS</option></Select>
                <Input value={l.unit_cost} onChange={(e) => setLine(i, { unit_cost: e.target.value })} placeholder="Unit cost ₹" />
                <Button variant="outline" size="sm" disabled={!l.material_id}
                  onClick={() => setCompareFor(l.material_id)}>Compare</Button>
                <Button variant="ghost" size="sm" aria-label="Remove"
                  onClick={() => setLines(lines.filter((_, j) => j !== i))} disabled={lines.length === 1}>
                  <Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => setLines([...lines, { material_id: "", description: "", quantity: "", unit: "MT", unit_cost: "" }])}>
              <Plus className="h-3.5 w-3.5" /> Add line</Button>
          </div>

          {/* Inline supplier comparison */}
          {compareFor && (
            <div className="rounded-md border border-accent/40 bg-teal-50/50 p-3">
              <p className="mb-2 text-xs font-semibold text-teal-900">Landed-cost comparison — pick a supplier cost</p>
              {comparison.isLoading ? <p className="text-xs text-muted-foreground">Comparing suppliers…</p>
                : comparison.data?.items.length === 0 ? <p className="text-xs text-muted-foreground">No supplier offers for this material.</p>
                : comparison.data?.items.map((o) => (
                  <button key={o.supplier_id} type="button"
                    onClick={() => { const idx = lines.findIndex((x) => x.material_id === compareFor); if (idx >= 0) setLine(idx, { unit_cost: o.landed_cost }); setCompareFor(null); }}
                    className="mb-1 flex w-full items-center justify-between rounded border border-transparent bg-card px-3 py-1.5 text-left text-sm hover:border-accent">
                    <span><b>{o.rank ? `#${o.rank}` : "—"}</b> {o.supplier_name} <span className="text-xs text-muted-foreground">· {o.lead_time_days}d lead{o.lead_time_ok === false ? " (late)" : ""}</span></span>
                    <span className="font-semibold tabular-nums">{fmtMoney(o.landed_cost)}/MT{o.premium_vs_best && Number(o.premium_vs_best) > 0 && <span className="ml-1 text-[10px] text-amber-600">+{fmtMoney(o.premium_vs_best)}</span>}</span>
                  </button>
                ))}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button loading={createMut.isPending}
              disabled={!customerId || !lines.some((l) => l.description && l.quantity && l.unit_cost)}
              onClick={() => createMut.mutate()}>Create draft</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
