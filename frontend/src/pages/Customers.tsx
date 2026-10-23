import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, CheckCircle2, Plus, Search, Users2 } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import type { Customer } from "@/lib/types";
import { Card, Button, Input, Select, Label, Badge, Modal, ErrorState, MetricCard, CompactChartCard, DetailDrawer } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import type { ColumnDef } from "@tanstack/react-table";

const schema = z.object({
  name: z.string().min(2), code: z.string().min(2),
  category: z.string().optional(), gstin: z.string().optional(),
  credit_terms_days: z.string().optional(),
});

export default function Customers() {
  const qc = useQueryClient();
  const toast = useToast();
  const [search, setSearch] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<Customer | null>(null);

  const list = useQuery({
    queryKey: ["customers", search],
    queryFn: () => get<Page<Customer>>(`/v1/customers?search=${encodeURIComponent(search)}`),
  });
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  const createMut = useMutation({
    mutationFn: (v: z.infer<typeof schema>) => post("/v1/customers", {
      name: v.name, code: v.code, category: v.category || undefined, gstin: v.gstin || undefined,
      credit_terms_days: v.credit_terms_days ? Number(v.credit_terms_days) : 30,
    }),
    onSuccess: () => { toast.push("success", "Customer created"); setOpen(false); form.reset(); qc.invalidateQueries({ queryKey: ["customers"] }); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });

  const cols: ColumnDef<Customer, unknown>[] = [
    { accessorKey: "code", header: "Code", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "name", header: "Customer" },
    { accessorKey: "category", header: "Category", cell: (c) => c.row.original.category ? <Badge value={c.row.original.category!} /> : "—" },
    { accessorKey: "gstin", header: "GSTIN", cell: (c) => <span className="text-xs text-muted-foreground">{c.row.original.gstin ?? "—"}</span> },
    { id: "terms", header: "Credit terms", cell: (c) => `${c.row.original.credit_terms_days}d` },
    { id: "demo", header: "Data", cell: (c) => c.row.original.is_demo ? <Badge value="UNCONFIRMED" /> : null },
  ];
  const customers = list.data?.items ?? [];
  const active = customers.filter((customer) => customer.is_active).length;
  const categories = Object.entries(customers.reduce<Record<string, number>>((result, customer) => { const key = customer.category || "Uncategorized"; result[key] = (result[key] ?? 0) + 1; return result; }, {})).sort((a, b) => b[1] - a[1]);

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Customers</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} accounts</p></div>
        <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New customer</Button>
      </div>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><MetricCard label="Customer accounts" value={list.data?.total ?? "—"} hint="Portfolio records" icon={<Users2 className="h-5 w-5" />} /><MetricCard label="Active customers" value={list.data ? active : "—"} hint="Currently enabled" icon={<CheckCircle2 className="h-5 w-5" />} /><MetricCard label="Customer segments" value={list.data ? categories.length : "—"} hint="Recorded categories" icon={<Building2 className="h-5 w-5" />} /></section>
      <CompactChartCard title="Customer segmentation" subtitle="Distribution from recorded customer categories"><div className="h-[210px] space-y-3 overflow-y-auto pr-1">{categories.length ? categories.map(([category, count]) => <div key={category}><div className="mb-1 flex justify-between text-xs"><span className="font-medium">{category}</span><span className="text-muted-foreground">{count}</span></div><div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(8, (count / customers.length) * 100)}%` }} /></div></div>) : <p className="grid h-full place-items-center text-sm text-muted-foreground">No customer categories recorded.</p>}</div></CompactChartCard>
      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name or code…" className="pl-8" />
      </div>
      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} onRowClick={setSelected} dense emptyTitle="No customers" /></Card>}
      <DetailDrawer open={!!selected} onClose={() => setSelected(null)} title="Customer details">{selected && <div className="space-y-5"><div><p className="text-lg font-semibold">{selected.name}</p><p className="mt-1 text-sm text-muted-foreground">{selected.code}</p><div className="mt-3"><Badge value={selected.is_active ? "ACTIVE" : "CANCELLED"} /></div></div><dl className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-muted/30 p-4 text-sm"><div><dt className="text-xs text-muted-foreground">Category</dt><dd className="mt-1 font-medium">{selected.category || "—"}</dd></div><div><dt className="text-xs text-muted-foreground">Credit terms</dt><dd className="mt-1 font-medium">{selected.credit_terms_days} days</dd></div><div className="col-span-2"><dt className="text-xs text-muted-foreground">GSTIN</dt><dd className="mt-1 font-medium">{selected.gstin || "Not recorded"}</dd></div></dl></div>}</DetailDrawer>

      <Modal open={open} onClose={() => setOpen(false)} title="New customer">
        <form onSubmit={form.handleSubmit((v) => createMut.mutate(v))} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Name</Label><Input {...form.register("name")} placeholder="Bharat Constructions Ltd" />
              {form.formState.errors.name && <p className="mt-1 text-[11px] text-red-600">{form.formState.errors.name.message}</p>}</div>
            <div><Label>Code</Label><Input {...form.register("code")} placeholder="CUST-010" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Category</Label>
              <Select {...form.register("category")}><option value="">—</option>
                <option>OEM</option><option>CONTRACTOR</option><option>DISTRIBUTOR</option><option>FABRICATOR</option><option>RETAIL</option></Select></div>
            <div><Label>GSTIN</Label><Input {...form.register("gstin")} placeholder="27AABCB1234F1Z5" /></div>
          </div>
          <div><Label>Credit terms (days)</Label><Input {...form.register("credit_terms_days")} placeholder="30" /></div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={createMut.isPending}>Create</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
