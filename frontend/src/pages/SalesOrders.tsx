import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PackageCheck } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import { uid } from "@/lib/utils";
import type { SalesOrder, StockLot, Reservation } from "@/lib/types";
import { Card, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney, fmtQty, fmtDate } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

export default function SalesOrders() {
  const qc = useQueryClient();
  const toast = useToast();
  const [detail, setDetail] = React.useState<SalesOrder | null>(null);
  const [reserveFor, setReserveFor] = React.useState<{ itemId: string; materialId: string | null; open: string } | null>(null);
  const [lotId, setLotId] = React.useState("");
  const [qty, setQty] = React.useState("");

  const list = useQuery({ queryKey: ["sales-orders"], queryFn: () => get<Page<SalesOrder>>("/v1/sales-orders") });
  const eligibleLots = useQuery({
    queryKey: ["eligible-lots", reserveFor?.materialId],
    queryFn: () => get<Page<StockLot>>(`/v1/inventory/stock-lots?material_id=${reserveFor?.materialId}&quality_status=OK`),
    enabled: !!reserveFor?.materialId,
  });

  const reserveMut = useMutation({
    mutationFn: () => post(`/v1/sales-orders/${detail?.id}/reserve`, {
      sales_order_item_id: reserveFor?.itemId, lot_id: lotId, quantity: qty,
    }, uid()),
    onSuccess: () => {
      toast.push("success", "Stock reserved");
      setReserveFor(null); setDetail(null);
      ["sales-orders", "availability", "lots", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Reservation failed"),
  });

  const cols: ColumnDef<SalesOrder, unknown>[] = [
    { accessorKey: "number", header: "SO #", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "customer_name", header: "Customer" },
    { id: "value", header: "Value", cell: (c) => <span className="font-semibold tabular-nums">{fmtMoney(c.row.original.total_value)}</span> },
    { id: "lines", header: "Lines", cell: (c) => c.row.original.items.length },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "created_at", header: "Created", cell: (c) => <span className="text-xs text-muted-foreground">{fmtDate(c.getValue() as string)}</span> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div><h1 className="text-lg font-bold">Sales Orders</h1>
        <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} orders · reserve stock against order lines</p></div>

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} onRowClick={setDetail} emptyTitle="No sales orders" /></Card>}

      <Modal open={!!detail} onClose={() => setDetail(null)} title={`Sales order ${detail?.number ?? ""}`} wide>
        {detail && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 text-sm">
              <Badge value={detail.status} /><span className="font-medium">{detail.customer_name}</span>
              <span className="ml-auto font-semibold tabular-nums">{fmtMoney(detail.total_value)}</span>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="py-2">Item</th><th>Ordered</th><th>Reserved</th><th>Dispatched</th><th>Unit price</th><th /></tr></thead>
              <tbody>
                {detail.items.map((it) => {
                  const open = Number(it.quantity) - Number(it.reserved_qty ?? 0);
                  return (
                    <tr key={it.id} className="border-b border-border/50">
                      <td className="py-2 font-medium">{it.description}</td>
                      <td className="tabular-nums">{fmtQty(it.quantity, it.unit)}</td>
                      <td className="tabular-nums">{fmtQty(it.reserved_qty)}</td>
                      <td className="tabular-nums">{fmtQty(it.delivered_qty)}</td>
                      <td className="tabular-nums">{fmtMoney(it.unit_price)}</td>
                      <td className="text-right">
                        {open > 0 && (
                          <Button size="sm" variant="outline"
                            onClick={() => { setReserveFor({ itemId: it.id, materialId: it.material_id, open: String(open) }); setQty(String(open)); }}>
                            <PackageCheck className="h-3.5 w-3.5" /> Reserve
                          </Button>)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      <Modal open={!!reserveFor} onClose={() => setReserveFor(null)} title="Reserve stock">
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">Open quantity: {fmtQty(reserveFor?.open)}</p>
          <div><Label>Stock lot (eligible, quality OK)</Label>
            <Select value={lotId} onChange={(e) => setLotId(e.target.value)}>
              <option value="">Select lot…</option>
              {eligibleLots.data?.items.map((l) => (
                <option key={l.id} value={l.id}>{l.lot_number} · {l.warehouse_name} · avail {fmtQty(l.available_qty, l.unit)}</option>))}
            </Select>
            {eligibleLots.data?.items.length === 0 && <p className="mt-1 text-[11px] text-amber-600">No eligible lots — create a purchase request for the shortfall.</p>}
          </div>
          <div><Label>Quantity (MT)</Label><Input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" /></div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setReserveFor(null)}>Cancel</Button>
            <Button loading={reserveMut.isPending} disabled={!lotId || !qty} onClick={() => reserveMut.mutate()}>Reserve</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
