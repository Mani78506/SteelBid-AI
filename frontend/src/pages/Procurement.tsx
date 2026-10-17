import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, CheckCircle2, PackageOpen } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import { uid } from "@/lib/utils";
import type { PurchaseRequest, PurchaseOrder, Supplier, Material, Warehouse } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney, fmtQty, fmtDate } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

export default function Procurement() {
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = React.useState<"prs" | "pos">("prs");
  const [prOpen, setPrOpen] = React.useState(false);
  const [poOpen, setPoOpen] = React.useState(false);
  const [grnFor, setGrnFor] = React.useState<PurchaseOrder | null>(null);
  const [grnWh, setGrnWh] = React.useState("");

  // PR form
  const [prMaterial, setPrMaterial] = React.useState("");
  const [prQty, setPrQty] = React.useState("");
  // PO form
  const [poSupplier, setPoSupplier] = React.useState("");
  const [poPr, setPoPr] = React.useState("");
  const [poMaterial, setPoMaterial] = React.useState("");
  const [poQty, setPoQty] = React.useState("");
  const [poPrice, setPoPrice] = React.useState("");

  const prs = useQuery({ queryKey: ["purchase-requests"], queryFn: () => get<Page<PurchaseRequest>>("/v1/procurement/purchase-requests") });
  const pos = useQuery({ queryKey: ["purchase-orders"], queryFn: () => get<Page<PurchaseOrder>>("/v1/procurement/purchase-orders") });
  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: () => get<Page<Supplier>>("/v1/suppliers?page_size=100") });
  const materials = useQuery({ queryKey: ["materials-all"], queryFn: () => get<Page<Material>>("/v1/materials?page_size=100") });
  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: () => get<Warehouse[]>("/v1/inventory/warehouses") });

  const refresh = () => ["purchase-requests", "purchase-orders", "dashboard", "lots", "availability", "valuation"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  const prMut = useMutation({
    mutationFn: () => post("/v1/procurement/purchase-requests", {
      source_type: "MANUAL", items: [{ material_id: prMaterial, quantity: prQty, unit: "MT" }],
    }, uid()),
    onSuccess: () => { toast.push("success", "Purchase request created"); setPrOpen(false); setPrQty(""); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });
  const poMut = useMutation({
    mutationFn: () => post("/v1/procurement/purchase-orders", {
      supplier_id: poSupplier, purchase_request_id: poPr || undefined,
      items: [{ material_id: poMaterial, quantity: poQty, unit: "MT", unit_price: poPrice }],
    }),
    onSuccess: () => { toast.push("success", "Purchase order drafted"); setPoOpen(false); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });
  const approveMut = useMutation({
    mutationFn: (id: string) => post(`/v1/procurement/purchase-orders/${id}/approve`),
    onSuccess: () => { toast.push("success", "PO approved"); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Approve failed"),
  });
  const grnMut = useMutation({
    mutationFn: () => post("/v1/procurement/goods-receipts", {
      purchase_order_id: grnFor?.id, warehouse_id: grnWh,
    }, uid()),
    onSuccess: () => { toast.push("success", "Goods received — stock lots updated"); setGrnFor(null); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Receipt failed"),
  });

  const prCols: ColumnDef<PurchaseRequest, unknown>[] = [
    { accessorKey: "number", header: "PR #", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { id: "items", header: "Requirement", cell: (c) => <span className="text-xs">{c.row.original.items.map((i) => `${i.material_name} ${fmtQty(i.quantity, i.unit)}`).join(", ")}</span> },
    { accessorKey: "source_type", header: "Source", cell: (c) => <Badge value={(c.getValue() as string) ?? "MANUAL"} /> },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "created_at", header: "Created", cell: (c) => <span className="text-xs text-muted-foreground">{fmtDate(c.getValue() as string)}</span> },
  ];
  const poCols: ColumnDef<PurchaseOrder, unknown>[] = [
    { accessorKey: "number", header: "PO #", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "supplier_name", header: "Supplier" },
    { id: "items", header: "Items", cell: (c) => <span className="text-xs">{c.row.original.items.map((i) => `${i.material_name} ${fmtQty(i.quantity, i.unit)} @ ${fmtMoney(i.unit_price)}`).join(", ")}</span> },
    { accessorKey: "total_value", header: "Value", cell: (c) => <span className="font-semibold tabular-nums">{fmtMoney(c.getValue() as string)}</span> },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    {
      id: "actions", header: "", cell: (c) => (
        <span className="flex gap-1 justify-end" onClick={(e) => e.stopPropagation()}>
          {c.row.original.status === "DRAFT" && (
            <Button size="sm" variant="outline" onClick={() => approveMut.mutate(c.row.original.id)} loading={approveMut.isPending}>
              <CheckCircle2 className="h-3.5 w-3.5" /> Approve</Button>)}
          {["APPROVED", "SENT", "PARTIALLY_RECEIVED"].includes(c.row.original.status) && (
            <Button size="sm" variant="outline" onClick={() => { setGrnFor(c.row.original); setGrnWh(warehouses.data?.[0]?.id ?? ""); }}>
              <PackageOpen className="h-3.5 w-3.5" /> Receive</Button>)}
        </span>),
    },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Procurement</h1>
          <p className="text-xs text-muted-foreground">Shortage → purchase request → PO → goods receipt</p></div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setPrOpen(true)}><Plus className="h-3.5 w-3.5" /> Purchase request</Button>
          <Button size="sm" onClick={() => setPoOpen(true)}><Plus className="h-3.5 w-3.5" /> Purchase order</Button>
        </div>
      </div>

      <div className="flex gap-1 rounded-md border border-border bg-card p-0.5 text-xs w-fit">
        {(["prs", "pos"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded px-3 py-1.5 font-medium ${tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}>
            {t === "prs" ? `Purchase requests (${prs.data?.total ?? "…"})` : `Purchase orders (${pos.data?.total ?? "…"})`}
          </button>
        ))}
      </div>

      {tab === "prs"
        ? <Card>{prs.error ? <ErrorState error={prs.error} onRetry={() => prs.refetch()} />
          : <DataTable columns={prCols} data={prs.data?.items} loading={prs.isLoading} emptyTitle="No purchase requests" />}</Card>
        : <Card>{pos.error ? <ErrorState error={pos.error} onRetry={() => pos.refetch()} />
          : <DataTable columns={poCols} data={pos.data?.items} loading={pos.isLoading} emptyTitle="No purchase orders" />}</Card>}

      {/* New PR */}
      <Modal open={prOpen} onClose={() => setPrOpen(false)} title="New purchase request">
        <div className="space-y-3">
          <div><Label>Material</Label>
            <Select value={prMaterial} onChange={(e) => setPrMaterial(e.target.value)}>
              <option value="">Select…</option>
              {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </Select></div>
          <div><Label>Quantity (MT)</Label><Input value={prQty} onChange={(e) => setPrQty(e.target.value)} placeholder="60" /></div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setPrOpen(false)}>Cancel</Button>
            <Button loading={prMut.isPending} disabled={!prMaterial || !prQty} onClick={() => prMut.mutate()}>Create</Button>
          </div>
        </div>
      </Modal>

      {/* New PO */}
      <Modal open={poOpen} onClose={() => setPoOpen(false)} title="New purchase order">
        <div className="space-y-3">
          <div><Label>Supplier</Label>
            <Select value={poSupplier} onChange={(e) => setPoSupplier(e.target.value)}>
              <option value="">Select…</option>
              {suppliers.data?.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select></div>
          <div><Label>Linked purchase request (optional)</Label>
            <Select value={poPr} onChange={(e) => setPoPr(e.target.value)}>
              <option value="">—</option>
              {prs.data?.items.map((p) => <option key={p.id} value={p.id}>{p.number}</option>)}
            </Select></div>
          <div className="grid grid-cols-[1fr_80px_110px] gap-2 items-end">
            <div><Label>Material</Label>
              <Select value={poMaterial} onChange={(e) => setPoMaterial(e.target.value)}>
                <option value="">Select…</option>
                {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Select></div>
            <div><Label>Qty MT</Label><Input value={poQty} onChange={(e) => setPoQty(e.target.value)} /></div>
            <div><Label>Unit ₹/MT</Label><Input value={poPrice} onChange={(e) => setPoPrice(e.target.value)} /></div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setPoOpen(false)}>Cancel</Button>
            <Button loading={poMut.isPending} disabled={!poSupplier || !poMaterial || !poQty || !poPrice} onClick={() => poMut.mutate()}>Create</Button>
          </div>
        </div>
      </Modal>

      {/* GRN */}
      <Modal open={!!grnFor} onClose={() => setGrnFor(null)} title={`Goods receipt — ${grnFor?.number ?? ""}`}>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Receiving creates stock lots and movement entries for each PO line.
          </p>
          <div><Label>Receiving warehouse</Label>
            <Select value={grnWh} onChange={(e) => setGrnWh(e.target.value)}>
              <option value="">Select…</option>
              {warehouses.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </Select></div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setGrnFor(null)}>Cancel</Button>
            <Button loading={grnMut.isPending} disabled={!grnWh} onClick={() => grnMut.mutate()}>Receive goods</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
