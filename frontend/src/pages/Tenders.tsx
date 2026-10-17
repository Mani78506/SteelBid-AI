import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, UploadCloud, FileSearch, CheckCircle2, XCircle } from "lucide-react";
import { get, post, api, apiUpload, type Page } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select, Label, Badge, Modal, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney, fmtQty, fmtDate, daysUntil } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface Tender { id: string; number: string; title: string; customer: string | null; project_type: string;
  location: string | null; submission_deadline: string | null; estimated_value: string | null;
  status: string; documents_count: number; boq_items_count: number }
interface Doc { id: string; file_name: string; mime_type: string | null; size_bytes: number | null; status: string; created_at: string }
interface BoqItem { id: string; raw_description: string; form: string | null; grade: string | null;
  quantity: string | null; unit: string | null; material_id: string | null; review_status: string; source: string | null }
interface Evidence { id: string; page: number | null; field: string; raw_value: string;
  normalized_value: Record<string, unknown>; confidence: string | null; review_status: string; warnings: Record<string, unknown> }

export default function Tenders() {
  const qc = useQueryClient();
  const toast = useToast();
  const [detail, setDetail] = React.useState<Tender | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [f, setF] = React.useState({ number: "", title: "", customer: "", project_type: "BRIDGE", location: "", submission_deadline: "", estimated_value: "" });
  const fileRef = React.useRef<HTMLInputElement>(null);

  const list = useQuery({ queryKey: ["tenders"], queryFn: () => get<Page<Tender>>("/v1/tenders") });
  const docs = useQuery({ queryKey: ["tender-docs", detail?.id], queryFn: () => get<Doc[]>(`/v1/tenders/${detail?.id}/documents`), enabled: !!detail });
  const boq = useQuery({ queryKey: ["tender-boq", detail?.id], queryFn: () => get<BoqItem[]>(`/v1/tenders/${detail?.id}/boq`), enabled: !!detail });
  const evidence = useQuery({ queryKey: ["tender-evidence", detail?.id], queryFn: () => get<Evidence[]>(`/v1/tenders/${detail?.id}/evidence`), enabled: !!detail });
  const reqPreview = useQuery({
    queryKey: ["tender-req", detail?.id],
    queryFn: () => get<{ items: { boq_item_id: string; description: string; required: string; available: string; shortage: string }[] }>(`/v1/tenders/${detail?.id}/boq/requirements-preview`),
    enabled: !!detail,
  });
  const refresh = () => { ["tenders", "tender-docs", "tender-boq", "tender-evidence", "tender-req", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); };

  const createMut = useMutation({
    mutationFn: () => post("/v1/tenders", { ...f, estimated_value: f.estimated_value || undefined, submission_deadline: f.submission_deadline || undefined }),
    onSuccess: () => { toast.push("success", "Tender created"); setCreateOpen(false); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Create failed"),
  });
  const uploadMut = useMutation({
    mutationFn: (file: File) => apiUpload<Doc>(`/v1/tenders/${detail?.id}/documents`, file),
    onSuccess: () => { toast.push("success", "Document uploaded — run extraction next"); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Upload failed"),
  });
  const extractMut = useMutation({
    mutationFn: (docId: string) => post<{ job_id: string; status: string; candidates: number }>(`/v1/tenders/${detail?.id}/documents/${docId}/extract`),
    onSuccess: (r) => { toast.push("success", `Extraction complete — ${r.candidates} candidate line(s), all PENDING review`); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Extraction failed"),
  });
  const reviewMut = useMutation({
    mutationFn: ({ itemId, decision }: { itemId: string; decision: "CONFIRMED" | "REJECTED" }) =>
      api(`/v1/tenders/${detail?.id}/boq/${itemId}/review`, { method: "PATCH", body: { review_status: decision } }),
    onSuccess: () => refresh(),
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Review failed"),
  });

  const cols: ColumnDef<Tender, unknown>[] = [
    { accessorKey: "number", header: "Tender #", cell: (c) => <span className="font-medium text-primary">{c.getValue() as string}</span> },
    { accessorKey: "title", header: "Title" },
    { accessorKey: "project_type", header: "Type", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "value", header: "Est. value", cell: (c) => <span className="tabular-nums">{fmtMoney(c.row.original.estimated_value)}</span> },
    { id: "due", header: "Deadline", cell: (c) => {
      const days = daysUntil(c.row.original.submission_deadline);
      return <span className={`text-xs ${days !== null && days <= 3 ? "font-semibold text-red-600" : ""}`}>{fmtDate(c.row.original.submission_deadline)}{days !== null ? ` (${days}d)` : ""}</span>; } },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "boq", header: "Docs / BOQ", cell: (c) => <span className="text-xs text-muted-foreground">{c.row.original.documents_count} / {c.row.original.boq_items_count}</span> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Tenders & BOQ</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} tenders · extraction results always require human review</p></div>
        <Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="h-3.5 w-3.5" /> New tender</Button>
      </div>

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading}
            onRowClick={setDetail} emptyTitle="No tenders" /></Card>}

      {/* Tender detail */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={`${detail?.number ?? ""} — ${detail?.title ?? ""}`} wide>
        {detail && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <Badge value={detail.status} /><span>{detail.customer}</span>
              <span className="text-xs text-muted-foreground">{detail.location} · due {fmtDate(detail.submission_deadline)}</span>
              <span className="ml-auto font-semibold">{fmtMoney(detail.estimated_value)}</span>
            </div>

            {/* Documents */}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Documents</p>
              {(docs.data ?? []).map((d) => (
                <div key={d.id} className="mb-1.5 flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
                  <span className="font-medium">{d.file_name}</span>
                  <div className="flex items-center gap-2">
                    <Badge value={d.status} />
                    {d.status !== "EXTRACTED" && (
                      <Button size="sm" variant="outline" onClick={() => extractMut.mutate(d.id)} loading={extractMut.isPending}>
                        <FileSearch className="h-3.5 w-3.5" /> Extract BOQ</Button>)}
                  </div>
                </div>
              ))}
              <input ref={fileRef} type="file" accept=".pdf,.xlsx,.xls,.csv,.txt" className="hidden"
                onChange={(e) => { const fl = e.target.files?.[0]; if (fl) uploadMut.mutate(fl); e.target.value = ""; }} />
              <Button size="sm" variant="outline" className="mt-1" loading={uploadMut.isPending}
                onClick={() => fileRef.current?.click()}>
                <UploadCloud className="h-3.5 w-3.5" /> Upload document</Button>
            </div>

            {/* BOQ review */}
            {(boq.data?.length ?? 0) > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Extracted BOQ lines — confirm or reject each ({boq.data!.filter((b) => b.review_status === "PENDING").length} pending)
                </p>
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                    <th className="py-1.5">Extracted line</th><th>Form/Grade</th><th>Qty</th><th>Mapped</th><th>Review</th><th /></tr></thead>
                  <tbody>
                    {boq.data!.map((b) => (
                      <tr key={b.id} className="border-b border-border/50">
                        <td className="max-w-[280px] truncate py-1.5 font-medium" title={b.raw_description}>{b.raw_description}</td>
                        <td className="text-xs">{b.form ?? "?"}/{b.grade ?? "?"}</td>
                        <td className="tabular-nums">{b.quantity ? fmtQty(b.quantity, b.unit ?? "MT") : "—"}</td>
                        <td>{b.material_id ? <Badge value="VERIFIED" /> : <Badge value="UNCONFIRMED" />}</td>
                        <td><Badge value={b.review_status} /></td>
                        <td className="text-right">
                          {b.review_status === "PENDING" && (
                            <span className="flex justify-end gap-1">
                              <Button size="sm" variant="ghost" aria-label="Confirm"
                                onClick={() => reviewMut.mutate({ itemId: b.id, decision: "CONFIRMED" })}><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /></Button>
                              <Button size="sm" variant="ghost" aria-label="Reject"
                                onClick={() => reviewMut.mutate({ itemId: b.id, decision: "REJECTED" })}><XCircle className="h-3.5 w-3.5 text-red-600" /></Button>
                            </span>)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Requirements preview */}
            {(reqPreview.data?.items?.length ?? 0) > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Material requirements vs stock</p>
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                    <th className="py-1.5">Item</th><th>Required</th><th>Available</th><th>Shortage</th></tr></thead>
                  <tbody>
                    {reqPreview.data!.items.map((r) => (
                      <tr key={r.boq_item_id} className="border-b border-border/50">
                        <td className="max-w-[240px] truncate py-1.5">{r.description}</td>
                        <td className="tabular-nums">{fmtQty(r.required)}</td>
                        <td className="tabular-nums">{fmtQty(r.available)}</td>
                        <td className={`tabular-nums font-semibold ${Number(r.shortage) > 0 ? "text-red-600" : "text-emerald-700"}`}>{fmtQty(r.shortage)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Evidence */}
            {(evidence.data?.length ?? 0) > 0 && (
              <details className="rounded-md border border-border p-3">
                <summary className="cursor-pointer text-xs font-semibold text-muted-foreground">
                  Extraction evidence ({evidence.data!.length} rows — raw values, page refs, confidence)
                </summary>
                <table className="mt-2 w-full text-xs">
                  <tbody>
                    {evidence.data!.map((e) => (
                      <tr key={e.id} className="border-b border-border/40">
                        <td className="py-1">p.{e.page ?? "?"}</td>
                        <td className="max-w-[300px] truncate" title={e.raw_value}>{e.raw_value}</td>
                        <td className="tabular-nums">{e.confidence !== null ? `${(Number(e.confidence) * 100).toFixed(0)}%` : "—"}</td>
                        <td><Badge value={e.review_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </div>
        )}
      </Modal>

      {/* Create */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New tender">
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Tender #</Label><Input value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} placeholder="RBI/TND/2026/07" /></div>
            <div><Label>Project type</Label>
              <Select value={f.project_type} onChange={(e) => setF({ ...f, project_type: e.target.value })}>
                {["RAILWAY", "BRIDGE", "BUILDING", "INDUSTRIAL", "FABRICATION"].map((t) => <option key={t}>{t}</option>)}
              </Select></div>
          </div>
          <div><Label>Title</Label><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Railway foot-over-bridge steelwork" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Customer</Label><Input value={f.customer} onChange={(e) => setF({ ...f, customer: e.target.value })} /></div>
            <div><Label>Location</Label><Input value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Submission deadline</Label><Input type="date" value={f.submission_deadline} onChange={(e) => setF({ ...f, submission_deadline: e.target.value })} /></div>
            <div><Label>Estimated value ₹</Label><Input value={f.estimated_value} onChange={(e) => setF({ ...f, estimated_value: e.target.value })} /></div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button loading={createMut.isPending} disabled={!f.number || !f.title} onClick={() => createMut.mutate()}>Create</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
