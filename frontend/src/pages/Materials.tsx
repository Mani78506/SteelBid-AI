import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Search, Package } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import type { Material, Availability } from "@/lib/types";
import { Card, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtQty } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

const schema = z.object({
  sku: z.string().min(2), name: z.string().min(3),
  form: z.string().min(1), grade: z.string().min(1, "Grade is required"), standard: z.string().optional(),
  base_unit: z.string().default("MT"), density: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

export default function Materials() {
  const qc = useQueryClient();
  const toast = useToast();
  const [params] = useSearchParams();
  const [search, setSearch] = React.useState(params.get("search") ?? "");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [expanded, setExpanded] = React.useState<string | null>(null);

  const list = useQuery({
    queryKey: ["materials", search],
    queryFn: () => get<Page<Material>>(`/v1/materials?search=${encodeURIComponent(search)}`),
  });

  const avail = useQuery({
    queryKey: ["availability", expanded],
    queryFn: () => get<Availability[]>(`/v1/materials/availability?material_id=${expanded}`),
    enabled: !!expanded,
  });

  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { form: "BEAM", base_unit: "MT" } });
  const createMut = useMutation({
    mutationFn: (v: FormValues) => post("/v1/materials", { ...v, density: v.density || undefined }),
    onSuccess: () => { toast.push("success", "Material created"); setCreateOpen(false); form.reset(); qc.invalidateQueries({ queryKey: ["materials"] }); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });

  const columns: ColumnDef<Material, unknown>[] = [
    { accessorKey: "sku", header: "SKU", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "name", header: "Material" },
    { accessorKey: "form", header: "Form", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "grade", header: "Grade" },
    { accessorKey: "standard", header: "Std" },
    { accessorKey: "base_unit", header: "Unit" },
    { id: "status", header: "Status", cell: (c) => <Badge value={c.row.original.is_active ? "ACTIVE" : "CANCELLED"} /> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Material Master</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} materials · organization-scoped catalog</p></div>
        <Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="h-3.5 w-3.5" /> New material</Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search SKU, name, grade…" className="pl-8" />
      </div>

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : (
        <Card>
          <DataTable columns={columns} data={list.data?.items} loading={list.isLoading}
            onRowClick={(m) => setExpanded(expanded === m.id ? null : m.id)}
            emptyTitle="No materials found" emptyHint="Adjust search or create a material." />
          {expanded && (
            <div className="border-t border-border bg-muted/30 px-4 py-3">
              {avail.isLoading ? <p className="text-xs text-muted-foreground">Loading availability…</p> : (
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  {avail.data?.[0] && [
                    ["On hand", avail.data[0].on_hand], ["Reserved", avail.data[0].reserved],
                    ["Quality held", avail.data[0].quality_held], ["Available", avail.data[0].available],
                  ].map(([label, v]) => (
                    <div key={label} className="rounded-md border border-border bg-card px-3 py-2">
                      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
                      <p className="text-sm font-bold tabular-nums">{fmtQty(v as string)}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New material">
        <form onSubmit={form.handleSubmit((v) => createMut.mutate(v))} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>SKU</Label><Input {...form.register("sku")} placeholder="APX-PLATE-10-E250" />
              {form.formState.errors.sku && <p className="mt-1 text-[11px] text-red-600">{form.formState.errors.sku.message}</p>}</div>
            <div><Label>Base unit</Label>
              <Select {...form.register("base_unit")}><option>MT</option><option>KG</option><option>NOS</option><option>MTR</option></Select></div>
          </div>
          <div><Label>Name</Label><Input {...form.register("name")} placeholder="Plate 10mm E250" />
            {form.formState.errors.name && <p className="mt-1 text-[11px] text-red-600">{form.formState.errors.name.message}</p>}</div>
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Form</Label>
              <Select {...form.register("form")}>
                {["BEAM", "CHANNEL", "ANGLE", "PLATE", "SHEET", "COIL", "BAR", "PIPE", "TMT", "FASTENER", "OTHER"].map((f) => <option key={f}>{f}</option>)}
              </Select></div>
            <div><Label>Grade</Label><Input {...form.register("grade")} placeholder="E250" />
              {form.formState.errors.grade && <p className="mt-1 text-[11px] text-red-600">{form.formState.errors.grade.message}</p>}</div>
            <div><Label>Standard</Label><Input {...form.register("standard")} placeholder="IS 2062" /></div>
          </div>
          <div><Label>Density kg/m³ (optional)</Label><Input {...form.register("density")} placeholder="7850" /></div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button type="submit" loading={createMut.isPending}>Create</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
