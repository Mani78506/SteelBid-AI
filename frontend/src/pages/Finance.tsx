import { useQuery } from "@tanstack/react-query";
import { IndianRupee, FileText, Landmark, Scale } from "lucide-react";
import { get, type Page } from "@/lib/api";
import { Card, CardContent, Badge, ErrorState, Skeleton } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { fmtMoney, fmtDate } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface Receivables { items: { invoice_id: string; number: string; total: string; paid: string; balance: string; due_date: string | null; is_overdue: boolean }[]; total_receivable: string; overdue_receivable: string }
interface Payables { total_payable: string }
interface Valuation { inventory_value: string }
interface Invoice { id: string; invoice_type: string; number: string; issue_date: string | null;
  due_date: string | null; subtotal: string; tax_amount: string; total: string;
  currency: string; status: string; paid_amount: string }

export default function Finance() {
  const rec = useQuery({ queryKey: ["receivables"], queryFn: () => get<Receivables>("/v1/finance/receivables") });
  const pay = useQuery({ queryKey: ["payables"], queryFn: () => get<Payables>("/v1/finance/payables") });
  const val = useQuery({ queryKey: ["fin-valuation"], queryFn: () => get<Valuation>("/v1/finance/valuation") });
  const invoices = useQuery({ queryKey: ["invoices"], queryFn: () => get<Page<Invoice>>("/v1/finance/invoices") });

  const cards = [
    { label: "Receivables", icon: Landmark, value: rec.data?.total_receivable },
    { label: "Overdue receivables", icon: Scale, value: rec.data?.overdue_receivable, danger: true },
    { label: "Payables", icon: FileText, value: pay.data?.total_payable },
    { label: "Inventory valuation", icon: IndianRupee, value: val.data?.inventory_value },
  ];

  const cols: ColumnDef<Invoice, unknown>[] = [
    { accessorKey: "number", header: "Invoice #", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "invoice_type", header: "Type", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "total", header: "Total", cell: (c) => <span className="font-semibold tabular-nums">{fmtMoney(c.getValue() as string)}</span> },
    { id: "balance", header: "Balance", cell: (c) => <span className="tabular-nums">{fmtMoney(String(Number(c.row.original.total) - Number(c.row.original.paid_amount ?? 0)))}</span> },
    { accessorKey: "due_date", header: "Due", cell: (c) => <span className="text-xs">{fmtDate(c.getValue() as string)}</span> },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div><h1 className="text-lg font-bold">Finance</h1>
        <p className="text-xs text-muted-foreground">Receivables, payables, and valuation from live records — not a statutory accounting system.</p></div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {cards.map(({ label, icon: Icon, value, danger }) => (
          <Card key={label}><CardContent className="flex items-center gap-3 py-3.5">
            <div className={`flex h-9 w-9 items-center justify-center rounded-md ${danger && Number(value) > 0 ? "bg-red-50 text-red-600" : "bg-primary-50 text-primary-600"}`}><Icon className="h-4.5 w-4.5" /></div>
            <div><p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
              {!value ? <Skeleton className="mt-1 h-6 w-20" />
                : <p className={`text-lg font-bold tabular-nums ${danger && Number(value) > 0 ? "text-red-600" : ""}`}>{fmtMoney(value)}</p>}</div>
          </CardContent></Card>
        ))}
      </div>

      {(rec.data?.items?.length ?? 0) > 0 && (
        <Card>
          <div className="border-b border-border px-4 py-2.5 text-sm font-semibold">Open receivables</div>
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-2">Invoice</th><th className="px-4 py-2">Total</th><th className="px-4 py-2">Paid</th><th className="px-4 py-2">Balance</th><th className="px-4 py-2">Due</th><th className="px-4 py-2" /></tr></thead>
            <tbody>
              {rec.data!.items.map((r) => (
                <tr key={r.invoice_id} className="border-b border-border/60 last:border-0">
                  <td className="px-4 py-2 font-medium">{r.number}</td>
                  <td className="px-4 py-2 tabular-nums">{fmtMoney(r.total)}</td>
                  <td className="px-4 py-2 tabular-nums">{fmtMoney(r.paid)}</td>
                  <td className="px-4 py-2 font-semibold tabular-nums">{fmtMoney(r.balance)}</td>
                  <td className="px-4 py-2 text-xs">{fmtDate(r.due_date)}</td>
                  <td className="px-4 py-2">{r.is_overdue && <Badge value="OVERDUE" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {invoices.error ? <ErrorState error={invoices.error} onRetry={() => invoices.refetch()} />
        : <Card><DataTable columns={cols} data={invoices.data?.items} loading={invoices.isLoading} emptyTitle="No invoices recorded" /></Card>}
    </div>
  );
}
