import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Truck } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import { uid as genId } from "@/lib/utils";
import type { SalesOrder, Warehouse, Material } from "@/lib/types";
import { Card, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtQty, fmtDate } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface Dispatch { id: string; number: string; sales_order_id: string | null; warehouse_id: string;
  status: string; vehicle: string | null; transporter: string | null;
  dispatch_date: string | null; delivery_date: string | null; items: Record<string, unknown>[] }

export default function Logistics() {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = React.useState(false);
  const [soId, setSoId] = React.useState("");
  const [whId, setWhId] = React.useState("");
  const [vehicle, setVehicle] = React.useState("");
  const [transporter, setTransporter] = React.useState("");
  const [matId, setMatId] = React.useState("");
  const [qty, setQty] = React.useState("");

  const list = useQuery({ queryKey: ["dispatches"], queryFn: () => get<Page<Dispatch>>("/v1/logistics/dispatches") });
  const sos = useQuery({ queryKey: ["sales-orders"], queryFn: () => get<Page<SalesOrder>>("/v1/sales-orders?page_size=100") });
  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: () => get<Warehouse[]>("/v1/inventory/warehouses") });
  const materials = useQuery({ queryKey: ["materials-all"], queryFn: () => get<Page<Material>>("/v1/materials?page_size=100") });
  const selSo = sos.data?.items.find((s) => s.id === soId);

  const createMut = useMutation({
    mutationFn: () => post("/v1/logistics/dispatches", {
      sales_order_id: soId || undefined, warehouse_id: whId,
      vehicle: vehicle || undefined, transporter: transporter || undefined,
      dispatch_date: new Date().toISOString().slice(0, 10),
      items: [{ material_id: matId, quantity: qty, unit: "MT",
                sales_order_item_id: selSo?.items[0]?.id }],
    }, genId()),
    onSuccess: () => {
      toast.push("success", "Dispatch created");
      setOpen(false);
      ["dispatches", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });
  const shipMut = useMutation({
    mutationFn: (id: string) => post(`/v1/logistics/dispatches/${id}/ship`),
    onSuccess: () => {
      toast.push("success", "Dispatched — reserved stock issued");
      ["dispatches", "sales-orders", "lots", "availability", "movements", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Ship failed"),
  });

  const cols: ColumnDef<Dispatch, unknown>[] = [
    { accessorKey: "number", header: "Challan #", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { id: "items", header: "Items", cell: (c) => <span className="text-xs">{(c.row.original.items ?? []).map((i) => fmtQty(i.quantity as string, (i.unit as string) ?? "MT")).join(", ")}</span> },
    { accessorKey: "vehicle", header: "Vehicle" },
    { accessorKey: "transporter", header: "Transporter" },
    { accessorKey: "dispatch_date", header: "Date", cell: (c) => <span className="text-xs text-muted-foreground">{fmtDate(c.getValue() as string)}</span> },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "actions", header: "", cell: (c) => (
      <span className="flex gap-1" onClick={(e) => e.stopPropagation()}>
        {["PLANNED", "READY", "PICKING"].includes(c.row.original.status) && (
          <Button size="sm" variant="outline" onClick={() => shipMut.mutate(c.row.original.id)} loading={shipMut.isPending}>Ship</Button>)}
      </span>),
    },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Logistics</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} dispatches · shipping issues reserved stock transactionally</p></div>
        <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New dispatch</Button>
      </div>

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} emptyTitle="No dispatches" /></Card>}

      <Modal open={open} onClose={() => setOpen(false)} title="New dispatch">
        <div className="space-y-3">
          <div><Label>Sales order (optional)</Label>
            <Select value={soId} onChange={(e) => setSoId(e.target.value)}>
              <option value="">—</option>
              {sos.data?.items.map((s) => <option key={s.id} value={s.id}>{s.number} — {s.customer_name}</option>)}
            </Select></div>
          <div><Label>Warehouse</Label>
            <Select value={whId} onChange={(e) => setWhId(e.target.value)}>
              <option value="">Select…</option>
              {warehouses.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </Select></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Material</Label>
              <Select value={matId} onChange={(e) => setMatId(e.target.value)}>
                <option value="">Select…</option>
                {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Select></div>
            <div><Label>Qty (MT)</Label><Input value={qty} onChange={(e) => setQty(e.target.value)} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Vehicle</Label><Input value={vehicle} onChange={(e) => setVehicle(e.target.value)} placeholder="MH-12-AB-3456" /></div>
            <div><Label>Transporter</Label><Input value={transporter} onChange={(e) => setTransporter(e.target.value)} /></div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button loading={createMut.isPending} disabled={!whId || !matId || !qty} onClick={() => createMut.mutate()}>
              <Truck className="h-3.5 w-3.5" /> Create dispatch</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
