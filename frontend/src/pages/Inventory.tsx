import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, ArrowDownToLine, ArrowUpFromLine } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import { uid } from "@/lib/utils";
import type { Warehouse, StockLot, Movement, Material } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select, Label, Badge, Modal, ErrorState, Skeleton } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtQty, fmtMoney, fmtDateTime } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

const txnSchema = z.object({
  material_id: z.string().uuid(), warehouse_id: z.string().uuid(),
  lot_number: z.string().min(1), heat_number: z.string().optional(),
  quantity: z.string().refine((v) => Number(v) > 0, "Quantity must be positive"),
  unit_cost: z.string().optional(),
});

export default function Inventory() {
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = React.useState<"lots" | "movements">("lots");
  const [warehouseId, setWarehouseId] = React.useState("");
  const [quality, setQuality] = React.useState("");
  const [materialId, setMaterialId] = React.useState("");
  const [receiptOpen, setReceiptOpen] = React.useState(false);
  const [issueOpen, setIssueOpen] = React.useState(false);
  const [issueLot, setIssueLot] = React.useState<StockLot | null>(null);

  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: () => get<Warehouse[]>("/v1/inventory/warehouses") });
  const materials = useQuery({ queryKey: ["materials-all"], queryFn: () => get<Page<Material>>("/v1/materials?page_size=100") });
  const valuation = useQuery({ queryKey: ["valuation"], queryFn: () => get<{ total_value: string; lines: unknown[] }>("/v1/inventory/valuation") });

  const lotParams = new URLSearchParams();
  if (warehouseId) lotParams.set("warehouse_id", warehouseId);
  if (quality) lotParams.set("quality_status", quality);
  if (materialId) lotParams.set("material_id", materialId);
  const lots = useQuery({ queryKey: ["lots", lotParams.toString()], queryFn: () => get<Page<StockLot>>(`/v1/inventory/stock-lots?${lotParams}`) });
  const movements = useQuery({
    queryKey: ["movements", warehouseId],
    queryFn: () => get<Page<Movement>>(`/v1/inventory/movements${warehouseId ? `?warehouse_id=${warehouseId}` : ""}`),
    enabled: tab === "movements",
  });

  const receiptForm = useForm<z.infer<typeof txnSchema>>({ resolver: zodResolver(txnSchema) });
  const issueQty = React.useRef<HTMLInputElement>(null);

  const receiptMut = useMutation({
    mutationFn: (v: z.infer<typeof txnSchema>) =>
      post("/v1/inventory/receipts", { ...v, unit: "MT", heat_number: v.heat_number || undefined, unit_cost: v.unit_cost || undefined }, uid()),
    onSuccess: () => { toast.push("success", "Stock receipt posted"); setReceiptOpen(false); receiptForm.reset(); invalidate(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Receipt failed"),
  });
  const issueMut = useMutation({
    mutationFn: (v: { lot_id: string; quantity: string }) =>
      post("/v1/inventory/issues", { ...v, unit: "MT" }, uid()),
    onSuccess: () => { toast.push("success", "Stock issue posted"); setIssueOpen(false); setIssueLot(null); invalidate(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Issue failed"),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["lots"] }).then(() => {
    qc.invalidateQueries({ queryKey: ["movements"] }); qc.invalidateQueries({ queryKey: ["valuation"] });
    qc.invalidateQueries({ queryKey: ["availability"] }); qc.invalidateQueries({ queryKey: ["dashboard"] });
  });

  const lotCols: ColumnDef<StockLot, unknown>[] = [
    { accessorKey: "lot_number", header: "Lot", cell: (c) => <span className="font-medium">{c.getValue() as string}</span> },
    { accessorKey: "material_name", header: "Material" },
    { accessorKey: "warehouse_name", header: "Warehouse" },
    { accessorKey: "heat_number", header: "Heat #" },
    { id: "onhand", header: "On hand", cell: (c) => <span className="tabular-nums">{fmtQty(c.row.original.on_hand_qty, c.row.original.unit)}</span> },
    { id: "res", header: "Reserved", cell: (c) => <span className="tabular-nums">{fmtQty(c.row.original.reserved_qty, c.row.original.unit)}</span> },
    { id: "avail", header: "Available", cell: (c) => <span className="font-semibold tabular-nums">{fmtQty(c.row.original.available_qty, c.row.original.unit)}</span> },
    { accessorKey: "quality_status", header: "Quality", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "cost", header: "Unit cost", cell: (c) => <span className="tabular-nums">{fmtMoney(c.row.original.unit_cost)}</span> },
    {
      id: "actions", header: "", cell: (c) => (
        <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setIssueLot(c.row.original); setIssueOpen(true); }}>
          <ArrowUpFromLine className="h-3.5 w-3.5" /> Issue
        </Button>),
    },
  ];
  const mvCols: ColumnDef<Movement, unknown>[] = [
    { accessorKey: "created_at", header: "When", cell: (c) => <span className="text-xs">{fmtDateTime(c.getValue() as string)}</span> },
    { accessorKey: "movement_type", header: "Type", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "quantity", header: "Qty", cell: (c) => <span className="tabular-nums">{fmtQty(c.getValue() as string, c.row.original.unit)}</span> },
    { accessorKey: "reference", header: "Ref", cell: (c) => <span className="text-xs">{typeof c.row.original.reference === "object" ? JSON.stringify(c.row.original.reference) : c.row.original.reference}</span> },
    { accessorKey: "balance_after_on_hand", header: "On hand after", cell: (c) => <span className="tabular-nums">{fmtQty(c.getValue() as string)}</span> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">Inventory</h1>
          <p className="text-xs text-muted-foreground">
            Valuation {valuation.data ? <b className="text-foreground">{fmtMoney(valuation.data.total_value)}</b> : "…"} · {lots.data?.total ?? "—"} stock lots
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setReceiptOpen(true)}><ArrowDownToLine className="h-3.5 w-3.5" /> Receipt</Button>
        </div>
      </div>

      {/* Filters */}
      <Card><CardContent className="flex flex-wrap items-end gap-3 py-3">
        <div className="w-52"><Label>Warehouse</Label>
          <Select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
            <option value="">All warehouses</option>
            {warehouses.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </Select></div>
        <div className="w-52"><Label>Material</Label>
          <Select value={materialId} onChange={(e) => setMaterialId(e.target.value)}>
            <option value="">All materials</option>
            {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </Select></div>
        <div className="w-40"><Label>Quality</Label>
          <Select value={quality} onChange={(e) => setQuality(e.target.value)}>
            <option value="">All</option><option>OK</option><option>QUARANTINED</option><option>REJECTED</option>
          </Select></div>
        <div className="ml-auto flex rounded-md border border-border text-xs">
          {(["lots", "movements"] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1.5 capitalize ${tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}>
              {t === "lots" ? "Stock lots" : "Movement ledger"}
            </button>
          ))}
        </div>
      </CardContent></Card>

      {tab === "lots"
        ? <Card>{lots.error ? <ErrorState error={lots.error} onRetry={() => lots.refetch()} />
          : <DataTable columns={lotCols} data={lots.data?.items} loading={lots.isLoading} dense
              emptyTitle="No stock lots" emptyHint="Post a receipt to add stock." />}</Card>
        : <Card>{movements.error ? <ErrorState error={movements.error} />
          : <DataTable columns={mvCols} data={movements.data?.items} loading={movements.isLoading} dense
              emptyTitle="No movements yet" />}</Card>}

      {/* Receipt modal */}
      <Modal open={receiptOpen} onClose={() => setReceiptOpen(false)} title="Post stock receipt">
        <form onSubmit={receiptForm.handleSubmit((v) => receiptMut.mutate(v))} className="space-y-3">
          <div><Label>Material</Label>
            <Select {...receiptForm.register("material_id")}>
              <option value="">Select…</option>
              {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.sku} — {m.name}</option>)}
            </Select></div>
          <div><Label>Warehouse</Label>
            <Select {...receiptForm.register("warehouse_id")}>
              <option value="">Select…</option>
              {warehouses.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </Select></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Lot number</Label><Input {...receiptForm.register("lot_number")} placeholder="LOT-001" /></div>
            <div><Label>Heat number</Label><Input {...receiptForm.register("heat_number")} placeholder="H-7781" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Quantity (MT)</Label><Input {...receiptForm.register("quantity")} placeholder="25" />
              {receiptForm.formState.errors.quantity && <p className="mt-1 text-[11px] text-red-600">{receiptForm.formState.errors.quantity.message}</p>}</div>
            <div><Label>Unit cost ₹/MT</Label><Input {...receiptForm.register("unit_cost")} placeholder="56200" /></div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setReceiptOpen(false)}>Cancel</Button>
            <Button type="submit" loading={receiptMut.isPending}>Post receipt</Button>
          </div>
        </form>
      </Modal>

      {/* Issue modal */}
      <Modal open={issueOpen} onClose={() => setIssueOpen(false)} title={`Issue stock — ${issueLot?.lot_number ?? ""}`}>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (issueLot && issueQty.current) issueMut.mutate({ lot_id: issueLot.id, quantity: issueQty.current.value }); }}>
          <p className="text-xs text-muted-foreground">{issueLot?.material_name} · available {fmtQty(issueLot?.available_qty, issueLot?.unit)} · quality {issueLot?.quality_status}</p>
          <div><Label>Quantity (MT)</Label><Input ref={issueQty} required inputMode="decimal" placeholder="10" /></div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setIssueOpen(false)}>Cancel</Button>
            <Button type="submit" loading={issueMut.isPending}>Post issue</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
