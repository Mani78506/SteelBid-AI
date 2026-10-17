import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Play, CheckCircle2 } from "lucide-react";
import { get, post, api, type Page } from "@/lib/api";
import type { Material, StockLot } from "@/lib/types";
import { Card, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney, fmtQty, fmtDate } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface BomItem { id: string; material_id: string; material_name?: string; quantity: string; unit: string; theoretical_waste_pct: string; estimated_cost: string | null }
interface Bom { id: string; bom_code: string; product_name: string; version_no: number; status: string;
  estimated_material_cost: string; estimated_total_cost: string; items: BomItem[]; created_at: string }
interface WoOp { id: string; sequence: number; operation_type: string; status: string; actual_hours: string | null }
interface WorkOrder { id: string; number: string; status: string; planned_qty: string; produced_qty: string;
  due_date: string | null; actual_material_cost: string; actual_labour_cost: string; operations: WoOp[] }

export default function Fabrication() {
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = React.useState<"boms" | "wos">("boms");
  const [bomOpen, setBomOpen] = React.useState(false);
  const [bomDetail, setBomDetail] = React.useState<Bom | null>(null);
  const [woFor, setWoFor] = React.useState<Bom | null>(null);
  const [woQty, setWoQty] = React.useState("1");
  const [woDetail, setWoDetail] = React.useState<WorkOrder | null>(null);
  const [allocFor, setAllocFor] = React.useState<WorkOrder | null>(null);
  const [allocItem, setAllocItem] = React.useState("");
  const [allocLot, setAllocLot] = React.useState("");
  const [allocQty, setAllocQty] = React.useState("");
  const [code, setCode] = React.useState("");
  const [name, setName] = React.useState("");
  const [items, setItems] = React.useState<{ material_id: string; quantity: string }[]>([{ material_id: "", quantity: "" }]);

  const boms = useQuery({ queryKey: ["boms"], queryFn: () => get<Page<Bom>>("/v1/fabrication/boms") });
  const wos = useQuery({ queryKey: ["work-orders"], queryFn: () => get<Page<WorkOrder>>("/v1/fabrication/work-orders") });
  const materials = useQuery({ queryKey: ["materials-all"], queryFn: () => get<Page<Material>>("/v1/materials?page_size=100") });
  const bomForWo = useQuery({
    queryKey: ["bom-detail", bomDetail?.id],
    queryFn: () => get<Bom>(`/v1/fabrication/boms/${bomDetail?.id}`),
    enabled: !!bomDetail,
  });
  const allocLots = useQuery({
    queryKey: ["alloc-lots", allocItem],
    queryFn: () => get<Page<StockLot>>(`/v1/inventory/stock-lots?material_id=${allocItem}&quality_status=OK`),
    enabled: !!allocFor && !!allocItem,
  });

  const refresh = () => ["boms", "work-orders", "dashboard", "availability", "lots"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  const bomMut = useMutation({
    mutationFn: () => post("/v1/fabrication/boms", {
      bom_code: code, product_name: name,
      items: items.filter((i) => i.material_id && i.quantity).map((i) => ({ ...i, unit: "MT" })),
      routings: ["CUTTING", "WELDING", "DRILLING", "PAINTING", "INSPECTION"].map((op, i) => ({ sequence: i + 1, operation_type: op })),
    }),
    onSuccess: () => { toast.push("success", "BOM created with cost estimate"); setBomOpen(false); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });
  const woMut = useMutation({
    mutationFn: () => post("/v1/fabrication/work-orders", { bom_version_id: woFor?.id, planned_qty: woQty }),
    onSuccess: () => { toast.push("success", "Work order created — allocate stock next"); setWoFor(null); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });
  const approveMut = useMutation({
    mutationFn: (id: string) => post(`/v1/fabrication/boms/${id}/approve`),
    onSuccess: () => { toast.push("success", "BOM approved"); refresh(); setBomDetail(null); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Approve failed"),
  });
  const opMut = useMutation({
    mutationFn: ({ woId, opId, status }: { woId: string; opId: string; status: string }) =>
      api(`/v1/fabrication/work-orders/${woId}/operations/${opId}`, { method: "PATCH", body: { status } }),
    onSuccess: () => { refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Failed"),
  });
  const allocMut = useMutation({
    mutationFn: () => post(`/v1/fabrication/work-orders/${allocFor?.id}/allocate`, {
      material_id: allocItem, lot_id: allocLot, quantity: allocQty,
    }),
    onSuccess: () => { toast.push("success", "Material allocated"); setAllocFor(null); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Allocate failed"),
  });

  const bomCols: ColumnDef<Bom, unknown>[] = [
    { accessorKey: "bom_code", header: "BOM", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string} <span className="text-muted-foreground">v{c.row.original.version_no}</span></span> },
    { accessorKey: "product_name", header: "Product" },
    { id: "items", header: "Items", cell: (c) => c.row.original.items?.length ?? 0 },
    { id: "cost", header: "Est. cost", cell: (c) => <span className="font-semibold tabular-nums">{fmtMoney(c.row.original.estimated_total_cost)}</span> },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "actions", header: "", cell: (c) => (
      <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setWoFor(c.row.original); }}>
        <Play className="h-3.5 w-3.5" /> Work order</Button>) },
  ];
  const woCols: ColumnDef<WorkOrder, unknown>[] = [
    { accessorKey: "number", header: "WO #", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { id: "ops", header: "Operations", cell: (c) => (
      <span className="flex flex-wrap gap-1">{(c.row.original.operations ?? []).map((o) => (
        <Badge key={o.id} value={o.operation_type + ":" + o.status} />))}</span>) },
    { id: "progress", header: "Progress", cell: (c) => `${c.row.original.produced_qty}/${c.row.original.planned_qty}` },
    { accessorKey: "due_date", header: "Due", cell: (c) => <span className="text-xs">{fmtDate(c.getValue() as string)}</span> },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "cost", header: "Actual cost", cell: (c) => <span className="tabular-nums">{fmtMoney(c.row.original.actual_material_cost)}</span> },
    { id: "actions", header: "", cell: (c) => {
      const next = (c.row.original.operations ?? []).find((o) => o.status !== "COMPLETED");
      return (
        <span className="flex gap-1" onClick={(e) => e.stopPropagation()}>
          <Button size="sm" variant="ghost" onClick={() => setAllocFor(c.row.original)}>Allocate</Button>
          {next && <Button size="sm" variant="outline" onClick={() => opMut.mutate({ woId: c.row.original.id, opId: next.id, status: "COMPLETED" })}>
            <CheckCircle2 className="h-3.5 w-3.5" /> Done {next.operation_type.toLowerCase()}</Button>}
        </span>); } },
  ];

  const detail = bomForWo.data ?? bomDetail;

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Fabrication</h1>
          <p className="text-xs text-muted-foreground">BOMs → allocation → work orders → operations → QC</p></div>
        <Button size="sm" onClick={() => setBomOpen(true)}><Plus className="h-3.5 w-3.5" /> New BOM</Button>
      </div>

      <div className="flex gap-1 rounded-md border border-border bg-card p-0.5 text-xs w-fit">
        {(["boms", "wos"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded px-3 py-1.5 font-medium ${tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}>
            {t === "boms" ? `BOMs (${boms.data?.total ?? "…"})` : `Work orders (${wos.data?.total ?? "…"})`}
          </button>
        ))}
      </div>

      {tab === "boms"
        ? <Card>{boms.error ? <ErrorState error={boms.error} />
          : <DataTable columns={bomCols} data={boms.data?.items} loading={boms.isLoading} onRowClick={setBomDetail} emptyTitle="No BOMs — create one to begin" />}</Card>
        : <Card>{wos.error ? <ErrorState error={wos.error} />
          : <DataTable columns={woCols} data={wos.data?.items} loading={wos.isLoading} onRowClick={setWoDetail} emptyTitle="No work orders" />}</Card>}

      {/* BOM detail */}
      <Modal open={!!bomDetail} onClose={() => setBomDetail(null)} title={`BOM ${detail?.bom_code ?? ""} v${detail?.version_no ?? ""}`} wide>
        {detail && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 text-sm">
              <Badge value={detail.status} /><span className="font-medium">{detail.product_name}</span>
              <span className="ml-auto">Est. cost <b className="tabular-nums">{fmtMoney(detail.estimated_total_cost)}</b> (material {fmtMoney(detail.estimated_material_cost)})</span>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="py-2">Material</th><th>Qty</th><th>Waste</th><th>Est. cost</th></tr></thead>
              <tbody>
                {detail.items?.map((it) => (
                  <tr key={it.id} className="border-b border-border/50">
                    <td className="py-2 font-medium">{it.material_name}</td>
                    <td className="tabular-nums">{fmtQty(it.quantity, it.unit)}</td>
                    <td className="tabular-nums">{it.theoretical_waste_pct}%</td>
                    <td className="tabular-nums font-semibold">{fmtMoney(it.estimated_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex justify-end gap-2">
              {detail.status === "DRAFT" && <Button size="sm" onClick={() => approveMut.mutate(detail.id)} loading={approveMut.isPending}>Approve BOM</Button>}
            </div>
          </div>
        )}
      </Modal>

      {/* WO detail */}
      <Modal open={!!woDetail} onClose={() => setWoDetail(null)} title={`Work order ${woDetail?.number ?? ""}`} wide>
        {woDetail && (
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-sm"><Badge value={woDetail.status} />
              <span>{woDetail.produced_qty}/{woDetail.planned_qty} produced</span>
              <span className="ml-auto text-xs text-muted-foreground">Material {fmtMoney(woDetail.actual_material_cost)} · Labour {fmtMoney(woDetail.actual_labour_cost)}</span></div>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="py-2">Seq</th><th>Operation</th><th>Status</th><th /></tr></thead>
              <tbody>
                {woDetail.operations.map((o) => (
                  <tr key={o.id} className="border-b border-border/50">
                    <td className="py-2">{o.sequence}</td>
                    <td className="font-medium">{o.operation_type}</td>
                    <td><Badge value={o.status} /></td>
                    <td className="text-right">{o.status !== "COMPLETED" && (
                      <Button size="sm" variant="ghost" onClick={() => { opMut.mutate({ woId: woDetail.id, opId: o.id, status: "COMPLETED" }); setWoDetail({ ...woDetail, operations: woDetail.operations.map((x) => x.id === o.id ? { ...x, status: "COMPLETED" } : x) }); }}>
                        Complete</Button>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      {/* New BOM */}
      <Modal open={bomOpen} onClose={() => setBomOpen(false)} title="New engineering BOM" wide>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>BOM code</Label><Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="BOM-PLAT-12" /></div>
            <div><Label>Product name</Label><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Platform frame P-12" /></div>
          </div>
          <Label>Material lines</Label>
          {items.map((it, i) => (
            <div key={i} className="grid grid-cols-[1fr_100px] items-end gap-2">
              <Select value={it.material_id} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, material_id: e.target.value } : x))}>
                <option value="">Material…</option>
                {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Select>
              <Input value={it.quantity} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, quantity: e.target.value } : x))} placeholder="Qty MT" />
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={() => setItems([...items, { material_id: "", quantity: "" }])}>
            <Plus className="h-3.5 w-3.5" /> Add line</Button>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setBomOpen(false)}>Cancel</Button>
            <Button loading={bomMut.isPending} disabled={!code || !name || !items.some((i) => i.material_id && i.quantity)} onClick={() => bomMut.mutate()}>Create BOM</Button>
          </div>
        </div>
      </Modal>

      {/* WO create */}
      <Modal open={!!woFor} onClose={() => setWoFor(null)} title={`New work order — ${woFor?.bom_code ?? ""}`}>
        <div className="space-y-3">
          <div><Label>Planned quantity</Label><Input value={woQty} onChange={(e) => setWoQty(e.target.value)} /></div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setWoFor(null)}>Cancel</Button>
            <Button loading={woMut.isPending} onClick={() => woMut.mutate()}>Generate</Button>
          </div>
        </div>
      </Modal>

      {/* Allocate */}
      <Modal open={!!allocFor} onClose={() => setAllocFor(null)} title={`Allocate material — ${allocFor?.number ?? ""}`}>
        <div className="space-y-3">
          <div><Label>Material</Label>
            <Select value={allocItem} onChange={(e) => { setAllocItem(e.target.value); setAllocLot(""); }}>
              <option value="">Select…</option>
              {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </Select></div>
          <div><Label>Stock lot (eligible)</Label>
            <Select value={allocLot} onChange={(e) => setAllocLot(e.target.value)}>
              <option value="">Select…</option>
              {allocLots.data?.items.map((l) => <option key={l.id} value={l.id}>{l.lot_number} · {fmtQty(l.available_qty, l.unit)} available</option>)}
            </Select></div>
          <div><Label>Quantity (MT)</Label><Input value={allocQty} onChange={(e) => setAllocQty(e.target.value)} /></div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setAllocFor(null)}>Cancel</Button>
            <Button loading={allocMut.isPending} disabled={!allocItem || !allocLot || !allocQty} onClick={() => allocMut.mutate()}>Allocate</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
