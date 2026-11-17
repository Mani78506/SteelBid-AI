import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, FileSearch, FileUp, PackageCheck, RefreshCw, RotateCcw, XCircle } from "lucide-react";
import { api, apiUpload, get, post, type Page } from "@/lib/api";
import { Badge, Button, Card, CardContent, ErrorState, Input, Select, Skeleton } from "@/components/ui";
import { fmtDate } from "@/lib/format";
import { useToast } from "@/components/Toast";
import { useAuth } from "@/lib/auth";

type Doc = { id: string; file_name: string; size_bytes: number | null; status: string; created_at: string };
type Evidence = { id: string; document_id: string; page: number | null; raw_value: string; confidence: string | null };
type Row = { id: string; raw_description: string; material_id: string | null; form: string | null; grade: string | null; specification: Record<string, unknown>; quantity: string | null; unit: string | null; review_status: string; page_ref: string | null };
type Material = { id: string; sku: string; name: string; form: string; grade: string; standard: string | null; base_unit: string; specification: Record<string, unknown>; is_active: boolean };

const dataKeys = ["workspace-documents", "workspace-boq", "workspace-evidence", "workspace-requirement-snapshots", "tender-workflow", "workspace-inventory-match"];
const qty = (value: string | null) => value === null || value === "" ? "" : Number.isFinite(Number(value)) ? String(Number(value)) : value;
const details = (value: Record<string, unknown>) => [value.standard, value.dimensions ?? value.size].filter(Boolean).flatMap(item => Array.isArray(item) ? item : [item]).join(" · ");
const normalized = (value: unknown) => (Array.isArray(value) ? value : [value]).filter(item => item !== null && item !== undefined).map(item => String(item).toUpperCase().replaceAll(" ", "")).join(" ");
// Older extracted TMT lines did not persist a form.  This is not a material
// substitution: TMT/reinforcement bar is the canonical REBAR material form.
const catalogueForm = (row: Row) => row.form ?? (/\b(tmt|rebars?|reinforcement bars?)\b/i.test(row.raw_description) ? "REBAR" : null);

function mappingReasons(row: Row, material: Material | undefined) {
  if (!material) return ["no material selected"];
  const reasons: string[] = [];
  if (row.form && material.form && row.form.toUpperCase() !== material.form.toUpperCase()) reasons.push("form");
  if (row.grade && material.grade && row.grade.toUpperCase() !== material.grade.toUpperCase()) reasons.push("grade");
  if (row.unit && material.base_unit !== row.unit) reasons.push("unit");
  const standard = row.specification.standard;
  if (standard && material.standard && String(standard).toUpperCase() !== material.standard.toUpperCase()) reasons.push("standard");
  const requiredDimensions = row.specification.dimensions ?? row.specification.size;
  const actualDimensions = material.specification?.dimensions ?? material.specification?.size;
  if (requiredDimensions && actualDimensions && normalized(requiredDimensions) !== normalized(actualDimensions)) reasons.push("dimensions");
  return reasons;
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone: "amber" | "emerald" | "slate" }) {
  const colors = { amber: "border-amber-200 bg-amber-50 text-amber-800", emerald: "border-emerald-200 bg-emerald-50 text-emerald-800", slate: "border-slate-200 bg-white text-slate-700" };
  return <div className={`rounded-lg border px-3 py-2 ${colors[tone]}`}><span className="text-[10px] font-bold uppercase tracking-wide">{label}</span><b className="ml-2 text-lg">{value}</b></div>;
}

function ReviewCard({ row, materials, evidence, writable, canManageMaterials, busy, creating, onSave, onCreateExact }: {
  row: Row; materials: Material[]; evidence: Evidence[]; writable: boolean; canManageMaterials: boolean; busy: boolean; creating: boolean;
  onSave: (status: "CONFIRMED" | "REJECTED", materialId?: string, quantity?: string) => void; onCreateExact: () => void;
}) {
  const [materialId, setMaterialId] = React.useState(row.material_id ?? "");
  const [quantity, setQuantity] = React.useState(qty(row.quantity));
  React.useEffect(() => { setMaterialId(row.material_id ?? ""); setQuantity(qty(row.quantity)); }, [row.id, row.material_id, row.quantity]);
  const pending = row.review_status === "PENDING";
  const confirmed = row.review_status === "CONFIRMED";
  const rejected = row.review_status === "REJECTED";
  const page = evidence[0]?.page ?? row.page_ref ?? "—";
  const selected = materials.find(item => item.id === materialId);
  const exact = materials.filter(item => item.is_active && mappingReasons(row, item).length === 0);
  const selectedReasons = mappingReasons(row, selected);
  const validMapping = !!materialId && selectedReasons.length === 0;
  const options = selected && !exact.some(item => item.id === selected.id) ? [selected, ...exact] : exact;
  const createForm = catalogueForm(row);
  const canCreateExact = canManageMaterials && !!createForm && !!row.grade && !!row.unit && !rejected;
  const requiresCorrection = !rejected && !validMapping;

  return <Card className={`overflow-hidden border-l-4 ${rejected ? "border-l-rose-500" : validMapping ? "border-l-emerald-500" : "border-l-amber-400"}`}>
    <CardContent className="p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0"><p className="line-clamp-2 text-sm font-semibold leading-snug text-slate-900">{row.raw_description}</p><div className="mt-1.5 flex flex-wrap gap-1">{createForm && <Badge value={createForm} />}<Badge value={row.grade ?? "GRADE MISSING"} />{row.unit && <Badge value={row.unit} />}</div></div>
        <Badge value={row.review_status} />
      </div>
      <div className="mt-3 flex items-end justify-between rounded-lg bg-slate-50 px-2.5 py-1.5"><div><p className="text-[9px] font-bold uppercase tracking-wide text-slate-500">Quantity</p>{pending ? <Input aria-label={`Quantity for ${row.raw_description}`} className="mt-0.5 h-7 w-24 bg-white text-base font-bold" value={quantity} disabled={!writable} onChange={event => setQuantity(event.target.value)} /> : <b className="mt-0.5 block text-xl text-slate-950">{quantity || "—"}</b>}</div><b className="pb-1 text-xs text-slate-600">{row.unit ?? "Unit missing"}</b></div>
      <div className="mt-2"><p className="text-[9px] font-bold uppercase tracking-wide text-slate-500">Exact material mapping</p><Select aria-label={`Material mapping for ${row.raw_description}`} className="mt-0.5 h-9 text-xs" value={materialId} disabled={rejected || !writable} onChange={event => setMaterialId(event.target.value)}><option value="">{exact.length ? "Select exact compatible material" : "No exact catalogue material"}</option>{options.map(item => <option value={item.id} key={item.id}>{item.name}{mappingReasons(row, item).length ? " — incompatible current mapping" : ""}</option>)}</Select></div>
      <div className="mt-2 flex items-center justify-between gap-2 text-[11px]"><span className="truncate text-slate-500">{details(row.specification) || "Specification needs review"}</span><span className="shrink-0 text-slate-500">p.{page}</span></div>
      {requiresCorrection && <div className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900"><span className="font-semibold">Catalogue action needed.</span> {selectedReasons.includes("no material selected") ? "No exact material is mapped." : `Current mapping differs by ${selectedReasons.join(", ")}.`}</div>}
      {pending && <div className="mt-3 grid grid-cols-2 gap-2"><Button size="sm" loading={busy} disabled={!writable || !validMapping || !quantity || !row.unit} onClick={() => onSave("CONFIRMED", materialId, quantity)}><CheckCircle2 className="h-3.5" /> Approve</Button><Button size="sm" variant="outline" disabled={!writable || busy} onClick={() => onSave("REJECTED")}><XCircle className="h-3.5" /> Reject</Button></div>}
      {confirmed && <div className="mt-3 flex flex-wrap items-center justify-between gap-2">{validMapping ? <p className="flex items-center gap-1 text-[11px] font-medium text-emerald-700"><CheckCircle2 className="h-3.5" /> Ready for BOM</p> : <p className="flex items-center gap-1 text-[11px] font-medium text-amber-800"><CircleAlert className="h-3.5" /> Correct mapping before BOM</p>}{writable && <Button size="sm" variant="outline" loading={busy} disabled={!validMapping || materialId === row.material_id} onClick={() => onSave("CONFIRMED", materialId)}><RotateCcw className="h-3.5" /> Update mapping</Button>}</div>}
      {requiresCorrection && canCreateExact && <Button className="mt-2 w-full" size="sm" variant="outline" loading={creating} disabled={busy || creating} onClick={onCreateExact}>Create and map exact material</Button>}
      {requiresCorrection && !canManageMaterials && <p className="mt-2 text-[11px] text-amber-800">A Materials administrator must add the exact catalogue item before this line can enter the BOM.</p>}
      {rejected && <p className="mt-3 flex items-center gap-1 text-[11px] font-medium text-rose-700"><XCircle className="h-3.5" /> Excluded from BOM</p>}
    </CardContent>
  </Card>;
}

export function TenderDocumentsRequirements({ tenderId, section }: { tenderId: string; section: "documents" | "requirements" }) {
  const qc = useQueryClient(); const toast = useToast(); const fileRef = React.useRef<HTMLInputElement>(null); const { can } = useAuth();
  const canReview = can("tenders.write"); const canBuild = can("fabrication.write"); const canManageMaterials = can("materials.write");
  const invalidate = () => dataKeys.forEach(key => qc.invalidateQueries({ queryKey: [key, tenderId] }));
  const docs = useQuery({ queryKey: ["workspace-documents", tenderId], queryFn: () => get<Doc[]>(`/v1/tenders/${tenderId}/documents`) });
  const boq = useQuery({ queryKey: ["workspace-boq", tenderId], queryFn: () => get<Row[]>(`/v1/tenders/${tenderId}/boq`) });
  const evidence = useQuery({ queryKey: ["workspace-evidence", tenderId], queryFn: () => get<Evidence[]>(`/v1/tenders/${tenderId}/evidence`) });
  const snapshots = useQuery({ queryKey: ["workspace-requirement-snapshots", tenderId], queryFn: () => get<{ id: string }[]>(`/v1/tenders/${tenderId}/requirement-snapshots`) });
  const workflow = useQuery({ queryKey: ["tender-workflow", tenderId], queryFn: () => get<{ bom_version_id?: string | null }>(`/v1/tenders/${tenderId}/workflow`) });
  const materials = useQuery({ queryKey: ["workspace-materials"], queryFn: () => get<Page<Material>>("/v1/materials?page_size=100") });
  const upload = useMutation({ mutationFn: (file: File) => apiUpload<Doc>(`/v1/tenders/${tenderId}/documents`, file), onSuccess: () => { toast.push("success", "Tender source uploaded. AI extraction is queued."); invalidate(); }, onError: error => toast.push("error", error instanceof Error ? error.message : "Upload failed") });
  const extract = useMutation({ mutationFn: (id: string) => post(`/v1/tenders/${tenderId}/documents/${id}/extract`), onSuccess: () => { toast.push("success", "Extraction queued."); invalidate(); }, onError: error => toast.push("error", error instanceof Error ? error.message : "Extraction failed") });
  const review = useMutation({ mutationFn: ({ row, status, materialId, quantity }: { row: Row; status: "CONFIRMED" | "REJECTED"; materialId?: string; quantity?: string }) => { if (!canReview) throw new Error("This demonstration is read-only. Sign in as an Estimator or Administrator to review BOQ lines."); return api(`/v1/tenders/${tenderId}/boq/${row.id}/review`, { method: "PATCH", body: { review_status: status, material_id: materialId, quantity } }); }, onSuccess: () => { toast.push("success", "BOQ line saved."); invalidate(); }, onError: error => toast.push("error", error instanceof Error ? error.message : "Review failed") });
  const createExact = useMutation({ mutationFn: async (row: Row) => {
    if (!canManageMaterials) throw new Error("A Materials administrator is required to add this catalogue item.");
    const form = catalogueForm(row);
    if (!form || !row.grade || !row.unit) throw new Error("Form, grade and unit must be reviewed before creating a catalogue material.");
    const specification = { ...row.specification };
    const material = await post<Material>("/v1/materials", { sku: `TENDER-${row.id.replaceAll("-", "").slice(0, 12).toUpperCase()}`, name: row.raw_description.slice(0, 255), form, grade: row.grade, standard: typeof specification.standard === "string" ? specification.standard : undefined, base_unit: row.unit, specification });
    await api(`/v1/tenders/${tenderId}/boq/${row.id}/review`, { method: "PATCH", body: { review_status: "CONFIRMED", material_id: material.id } });
    return material;
  }, onSuccess: () => { toast.push("success", "Exact catalogue material created and mapped."); qc.invalidateQueries({ queryKey: ["workspace-materials"] }); invalidate(); }, onError: error => toast.push("error", error instanceof Error ? error.message : "Material creation failed") });
  const generate = useMutation({ mutationFn: async () => { if (!canReview) throw new Error("Sign in as an Estimator or Administrator to create the approved requirements snapshot."); if (!canBuild) throw new Error("Sign in as an Administrator or Fabrication user to generate a BOM."); if (snapshots.isLoading) throw new Error("Checking snapshot status. Try again in a moment."); if (!(snapshots.data ?? []).length) await post(`/v1/tenders/${tenderId}/requirement-snapshots`); return post(`/v1/tenders/${tenderId}/workflow/bom`); }, onSuccess: () => { toast.push("success", "Approved requirements snapshot created and BOM generated."); invalidate(); }, onError: error => toast.push("error", error instanceof Error ? error.message : "BOM generation failed") });
  if (docs.isLoading || boq.isLoading) return <Skeleton className="h-72 w-full" />;
  if (docs.error || boq.error) return <ErrorState error={docs.error ?? boq.error!} onRetry={() => { docs.refetch(); boq.refetch(); }} />;
  const rows = boq.data ?? []; const pending = rows.filter(row => row.review_status === "PENDING"); const confirmed = rows.filter(row => row.review_status === "CONFIRMED"); const rejected = rows.filter(row => row.review_status === "REJECTED"); const reviewed = confirmed.length + rejected.length; const percent = rows.length ? Math.round(reviewed / rows.length * 100) : 0;
  if (section === "documents") return <section aria-label="Documents and extraction" className="space-y-3"><Card className="border-blue-100 bg-gradient-to-br from-blue-50 via-white to-cyan-50"><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4"><div className="flex items-center gap-3"><span className="rounded-xl bg-blue-100 p-3 text-blue-700"><FileSearch className="h-5 w-5" /></span><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-700">Source &amp; AI</p><h2 className="font-semibold text-slate-950">Upload → extract → review</h2></div></div><input ref={fileRef} className="hidden" type="file" accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xlsx" onChange={event => { const file = event.target.files?.[0]; if (file) upload.mutate(file); event.target.value = ""; }} /><Button loading={upload.isPending} onClick={() => fileRef.current?.click()}><FileUp className="h-4" /> Upload source</Button></CardContent></Card><div className="grid gap-3 md:grid-cols-2">{!(docs.data ?? []).length ? <Card className="md:col-span-2"><CardContent className="py-12 text-center text-sm text-slate-500">No tender source yet.</CardContent></Card> : docs.data!.map(doc => { const retry = doc.status === "UPLOADED" || doc.status === "FAILED"; return <Card key={doc.id}><CardContent className="flex items-center justify-between gap-3 p-3"><div className="min-w-0"><b className="block truncate">{doc.file_name}</b><span className="text-xs text-slate-500">{fmtDate(doc.created_at)} · {doc.size_bytes ?? "—"} bytes</span></div><div className="flex items-center gap-2"><Badge value={doc.status} />{retry && <Button size="sm" variant="outline" loading={extract.isPending} onClick={() => extract.mutate(doc.id)}><RefreshCw className="h-3.5" /> Retry</Button>}</div></CardContent></Card>; })}</div></section>;
  return <section aria-label="Material requirements and BOM" className="space-y-3"><Card className="border-blue-100 bg-gradient-to-br from-blue-50 via-white to-cyan-50"><CardContent className="p-3"><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><div className="grid h-14 w-14 place-items-center rounded-full" style={{ background: `conic-gradient(#2563eb ${percent}%, #dbeafe ${percent}% 100%)` }}><div className="grid h-10 w-10 place-items-center rounded-full bg-white text-center"><b className="text-sm">{reviewed}/{rows.length}</b><span className="text-[7px] font-bold uppercase text-slate-500">done</span></div></div><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-blue-700">Review &amp; BOM</p><h2 className="text-lg font-bold">Material requirements</h2><p className="text-xs text-slate-600">Confirm exact catalogue lines, then generate BOM.</p></div></div><Button size="sm" loading={generate.isPending} disabled={!confirmed.length} onClick={() => generate.mutate()}><PackageCheck className="h-3.5" /> Generate BOM</Button></div><div className="mt-3 grid gap-2 sm:grid-cols-3"><Metric label="Needs review" value={pending.length} tone="amber" /><Metric label="Approved" value={confirmed.length} tone="emerald" /><Metric label="BOM" value={workflow.data?.bom_version_id ? "Ready" : "Waiting"} tone="slate" /></div></CardContent></Card>{!canReview && <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">Read-only demo: sign in as an Estimator or Administrator to approve or correct a material mapping.</p>}<div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{rows.map(row => <ReviewCard key={row.id} row={row} materials={materials.data?.items ?? []} evidence={(evidence.data ?? []).filter(item => item.raw_value === row.raw_description)} writable={canReview} canManageMaterials={canManageMaterials} busy={review.isPending} creating={createExact.isPending} onSave={(status, materialId, quantity) => review.mutate({ row, status, materialId, quantity })} onCreateExact={() => createExact.mutate(row)} />)}</div></section>;
}
