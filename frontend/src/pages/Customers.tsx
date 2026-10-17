import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Search } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import type { Customer } from "@/lib/types";
import { Card, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
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

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Customers</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} accounts</p></div>
        <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New customer</Button>
      </div>
      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name or code…" className="pl-8" />
      </div>
      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} emptyTitle="No customers" /></Card>}

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
