import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import type { Customer } from "@/lib/types";
import { Card, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney, fmtDate } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface Project { id: string; code: string; name: string; project_type: string; location: string | null;
  customer_id: string | null; status: string; estimated_value: string | null;
  start_date: string | null; end_date: string | null; currency: string }

export default function Projects() {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = React.useState(false);
  const [f, setF] = React.useState({ code: "", name: "", project_type: "INDUSTRIAL", location: "", estimated_value: "", customer_id: "" });

  const list = useQuery({ queryKey: ["projects"], queryFn: () => get<Page<Project>>("/v1/projects") });
  const customers = useQuery({ queryKey: ["customers"], queryFn: () => get<Page<Customer>>("/v1/customers?page_size=100") });
  const createMut = useMutation({
    mutationFn: () => post("/v1/projects", {
      ...f, customer_id: f.customer_id || undefined, estimated_value: f.estimated_value || undefined,
    }),
    onSuccess: () => { toast.push("success", "Project created"); setOpen(false); qc.invalidateQueries({ queryKey: ["projects"] }); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });

  const custName = (id: string | null) => customers.data?.items.find((c) => c.id === id)?.name ?? "—";
  const cols: ColumnDef<Project, unknown>[] = [
    { accessorKey: "code", header: "Project #", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "name", header: "Name" },
    { accessorKey: "project_type", header: "Type", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "location", header: "Location" },
    { id: "customer", header: "Customer", cell: (c) => custName(c.row.original.customer_id) },
    { id: "budget", header: "Est. value", cell: (c) => <span className="tabular-nums">{fmtMoney(c.row.original.estimated_value)}</span> },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "window", header: "Window", cell: (c) => <span className="text-xs text-muted-foreground">{fmtDate(c.row.original.start_date)} → {fmtDate(c.row.original.end_date)}</span> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Projects</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} projects</p></div>
        <Button size="sm" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New project</Button>
      </div>
      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} emptyTitle="No projects" /></Card>}

      <Modal open={open} onClose={() => setOpen(false)} title="New project">
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Code</Label><Input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="PRJ-2026-04" /></div>
            <div><Label>Type</Label>
              <Select value={f.project_type} onChange={(e) => setF({ ...f, project_type: e.target.value })}>
                {["RAILWAY", "BRIDGE", "BUILDING", "INDUSTRIAL", "FABRICATION"].map((t) => <option key={t}>{t}</option>)}
              </Select></div>
          </div>
          <div><Label>Project name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Customer</Label>
              <Select value={f.customer_id} onChange={(e) => setF({ ...f, customer_id: e.target.value })}>
                <option value="">—</option>
                {customers.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select></div>
            <div><Label>Location</Label><Input value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} /></div>
          </div>
          <div><Label>Estimated value ₹</Label><Input value={f.estimated_value} onChange={(e) => setF({ ...f, estimated_value: e.target.value })} /></div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button loading={createMut.isPending} disabled={!f.code || !f.name} onClick={() => createMut.mutate()}>Create</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
