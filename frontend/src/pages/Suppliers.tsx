import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Search } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import type { Supplier, Material, ComparisonItem } from "@/lib/types";
import { Card, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

const schema = z.object({ name: z.string().min(2), code: z.string().min(2), city: z.string().optional(),
  payment_terms_days: z.string().optional(), lead_time_days: z.string().optional(),
  contact_name: z.string().optional(), email: z.string().optional(),
  capabilities: z.string().optional() });

export default function Suppliers() {
  const qc = useQueryClient();
  const toast = useToast();
  const [search, setSearch] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [compareMat, setCompareMat] = React.useState("");

  const list = useQuery({ queryKey: ["suppliers", search], queryFn: () => get<Page<Supplier>>(`/v1/suppliers?search=${encodeURIComponent(search)}`) });
  const materials = useQuery({ queryKey: ["materials-all"], queryFn: () => get<Page<Material>>("/v1/materials?page_size=100") });
  const comparison = useQuery({
    queryKey: ["supplier-compare", compareMat],
    queryFn: () => get<{ items: ComparisonItem[] }>(`/v1/procurement/compare?material_id=${compareMat}`),
    enabled: !!compareMat,
  });

  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  const createMut = useMutation({
    mutationFn: (v: z.infer<typeof schema>) => post("/v1/suppliers", {
      name: v.name, code: v.code, city: v.city || undefined, contact_name: v.contact_name || undefined,
      email: v.email || undefined,
      payment_terms_days: v.payment_terms_days ? Number(v.payment_terms_days) : undefined,
      lead_time_days: v.lead_time_days ? Number(v.lead_time_days) : undefined,
      material_capabilities: v.capabilities ? v.capabilities.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
    }),
    onSuccess: () => { toast.push("success", "Supplier added"); setOpen(false); form.reset(); qc.invalidateQueries({ queryKey: ["suppliers"] }); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });

  const cols: ColumnDef<Supplier, unknown>[] = [
    { accessorKey: "code", header: "Code", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "name", header: "Supplier" },
    { accessorKey: "city", header: "City" },
    { id: "caps", header: "Capabilities", cell: (c) => (
      <span className="flex flex-wrap gap-1">{((c.row.original.material_capabilities as string[]) ?? []).slice(0, 3).map((t) => <Badge key={t} value={t} />)}</span>) },
    { id: "terms", header: "Terms", cell: (c) => c.row.original.payment_terms_days ? `Net ${c.row.original.payment_terms_days}` : "—" },
    { id: "lead", header: "Lead", cell: (c) => c.row.original.lead_time_days ? `${c.row.original.lead_time_days}d` : "—" },
    { id: "rating", header: "Rating", cell: (c) => c.row.original.rating ? `${c.row.original.rating}★` : "—" },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Suppliers</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} suppliers · fictional demo vendors</p></div>
        <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New supplier</Button>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search suppliers…" className="pl-8" />
        </div>
        <div className="w-72">
          <Select value={compareMat} onChange={(e) => setCompareMat(e.target.value)}>
            <option value="">Compare supplier offers for a material…</option>
            {materials.data?.items.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </Select>
        </div>
      </div>

      {compareMat && (
        <Card>
          <div className="border-b border-border px-4 py-2.5">
            <p className="text-sm font-semibold">Landed-cost comparison — {materials.data?.items.find((m) => m.id === compareMat)?.name}</p>
          </div>
          {comparison.isLoading ? <p className="p-4 text-xs text-muted-foreground">Ranking offers…</p>
            : (comparison.data?.items.length ?? 0) === 0 ? <p className="p-4 text-xs text-muted-foreground">No offers recorded for this material.</p>
            : (
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2">Rank</th><th className="px-4 py-2">Supplier</th><th className="px-4 py-2">Quoted</th>
                  <th className="px-4 py-2">Landed ₹/MT</th><th className="px-4 py-2">Lead</th><th className="px-4 py-2">Terms</th><th className="px-4 py-2">vs best</th>
                </tr></thead>
                <tbody>
                  {comparison.data?.items.map((o) => (
                    <tr key={o.supplier_id} className="border-b border-border/60 last:border-0">
                      <td className="px-4 py-2 font-bold">{o.rank ? `#${o.rank}` : "—"}</td>
                      <td className="px-4 py-2 font-medium">{o.supplier_name}</td>
                      <td className="px-4 py-2 tabular-nums">{fmtMoney(o.unit_price)}</td>
                      <td className="px-4 py-2 font-semibold tabular-nums text-primary">{fmtMoney(o.landed_cost)}</td>
                      <td className="px-4 py-2 text-xs">{o.lead_time_days ?? "—"}d{o.lead_time_ok === false && <Badge value="UNCONFIRMED" className="ml-1" />}</td>
                      <td className="px-4 py-2 text-xs">{o.payment_terms_days ? `Net ${o.payment_terms_days}` : "—"}</td>
                      <td className="px-4 py-2 text-xs">{o.premium_vs_best && Number(o.premium_vs_best) > 0 ? `+${fmtMoney(o.premium_vs_best)}` : "best"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </Card>
      )}

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} emptyTitle="No suppliers" /></Card>}

      <Modal open={open} onClose={() => setOpen(false)} title="New supplier">
        <form onSubmit={form.handleSubmit((v) => createMut.mutate(v))} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Name</Label><Input {...form.register("name")} placeholder="Sahyadri Alloys" /></div>
            <div><Label>Code</Label><Input {...form.register("code")} placeholder="SUP-011" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>City</Label><Input {...form.register("city")} placeholder="Raipur" /></div>
            <div><Label>Contact name</Label><Input {...form.register("contact_name")} placeholder="Sales head" /></div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Payment terms (days)</Label><Input {...form.register("payment_terms_days")} placeholder="30" /></div>
            <div><Label>Lead time (days)</Label><Input {...form.register("lead_time_days")} placeholder="14" /></div>
            <div><Label>Email</Label><Input {...form.register("email")} type="email" /></div>
          </div>
          <div><Label>Capabilities (comma-separated)</Label><Input {...form.register("capabilities")} placeholder="BEAM:E250, PLATE:E350" /></div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={createMut.isPending}>Create</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
