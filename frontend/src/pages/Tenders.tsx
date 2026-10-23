import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, UploadCloud, FileSearch, CheckCircle2, XCircle, CalendarClock, ClipboardList, FileText, IndianRupee, PackageCheck } from "lucide-react";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, post, api, apiUpload, type Page } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select, Label, Badge, Modal, ErrorState, CompactChartCard, MetricCard } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney, fmtQty, fmtDate, daysUntil } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface Tender { id: string; number: string; title: string; customer: string | null; project_type: string;
  location: string | null; submission_deadline: string | null; estimated_value: string | null;
  status: string; documents_count: number; boq_items_count: number; description?: string | null;
  is_demo?: boolean; data_classification?: string; source_type?: string; rate_approval_status?: string }
interface Doc { id: string; file_name: string; mime_type: string | null; size_bytes: number | null; status: string; created_at: string }
interface BoqItem { id: string; raw_description: string; form: string | null; grade: string | null;
  quantity: string | null; unit: string | null; material_id: string | null; review_status: string; source: string | null; page_ref?: string | null; specification?: Record<string, unknown> }
interface Evidence { id: string; page: number | null; field: string; raw_value: string;
  normalized_value: Record<string, unknown>; confidence: string | null; review_status: string; warnings: Record<string, unknown> }
interface Offer { supplier_quote_id:string; supplier_name:string|null; quantity:string; unit:string; unit_price:string; freight_per_unit:string; tax_pct?:string; tax_recoverable?:boolean; landed_cost_per_unit:string; total_landed_cost?:string; lead_time_days?:number|null; compatible:boolean; reasons?:string[]; valid_until?:string|null }
interface CostEstimate { id:string; tender_id:string|null; status:string; context?:{costing_reference_date?:string;historical_market_benchmark?:{observed_on:string;material_form:string;grade:string;region:string;price_basis:string;unit:string;unit_price:string}|null}; material_cost:string; fabrication_cost:string; labour_cost:string; freight_cost:string; installation_cost:string; subcontracting_cost:string; overhead_cost:string; total_cost:string; currency:string }
interface Workflow { requirement_snapshot_version?:number|null; bom_version_id?:string|null; cost_estimate_id?:string|null; quotation_id?:string|null; customer_id?:string|null; submission_status?:string; shortages?:{bom_item_id:string;snapshot_id:string|null;required_quantity:string;available_quantity:string;shortage_quantity:string;unit:string}[] }
interface Customer { id:string; code:string; name:string; is_active:boolean }
interface Material { id:string; sku:string; name:string; form:string; grade:string; standard:string|null; base_unit:string; specification:Record<string, unknown>; is_active:boolean }

export default function Tenders() {
  const qc = useQueryClient();
  const toast = useToast();
  const [detail, setDetail] = React.useState<Tender | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [offersFor, setOffersFor] = React.useState<{id:string; form:string|null; grade:string|null; quantity:string; unit:string}|null>(null);
  const [f, setF] = React.useState({ number: "", title: "", customer: "", project_type: "BRIDGE", location: "", submission_deadline: "", estimated_value: "" });
  const [customerId, setCustomerId] = React.useState("");
  const [demoRates, setDemoRates] = React.useState<Record<string, string>>({});
  const [materialSearch, setMaterialSearch] = React.useState<Record<string, string>>({});
  const [mappedMaterial, setMappedMaterial] = React.useState<Record<string, string>>({});
  const [createMaterialFor, setCreateMaterialFor] = React.useState<BoqItem | null>(null);
  const [materialForm, setMaterialForm] = React.useState({ sku: "", name: "", form: "", grade: "", standard: "", base_unit: "MT" });
  const [customerForm, setCustomerForm] = React.useState({ code: "", name: "", category: "", gstin: "" });
  const [createCustomerOpen, setCreateCustomerOpen] = React.useState(false);
  const [submissionRef, setSubmissionRef] = React.useState("");
  const [costOpen, setCostOpen] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const newTenderFileRef = React.useRef<HTMLInputElement>(null);

  const list = useQuery({ queryKey: ["tenders"], queryFn: () => get<Page<Tender>>("/v1/tenders") });
  const docs = useQuery({ queryKey: ["tender-docs", detail?.id], queryFn: () => get<Doc[]>(`/v1/tenders/${detail?.id}/documents`), enabled: !!detail });
  const boq = useQuery({ queryKey: ["tender-boq", detail?.id], queryFn: () => get<BoqItem[]>(`/v1/tenders/${detail?.id}/boq`), enabled: !!detail });
  const evidence = useQuery({ queryKey: ["tender-evidence", detail?.id], queryFn: () => get<Evidence[]>(`/v1/tenders/${detail?.id}/evidence`), enabled: !!detail });
  const reqPreview = useQuery({
    queryKey: ["tender-req", detail?.id],
    queryFn: () => get<{ items: { boq_item_id: string; description: string; required: string; available: string; shortage: string }[] }>(`/v1/tenders/${detail?.id}/boq/requirements-preview`),
    enabled: !!detail,
  });
  const snapshots = useQuery({ queryKey: ["tender-snapshots", detail?.id], queryFn: () => get<{ id: string; version: number; material_id: string; form: string | null; grade: string | null; quantity: string; unit: string }[]>(`/v1/tenders/${detail?.id}/requirement-snapshots`), enabled: !!detail });
  const selections = useQuery({ queryKey: ["tender-selections", detail?.id], queryFn: () => get<{ id: string; snapshot_id: string; supplier_quote_id:string; selected_qty: string; unit: string; landed_cost_per_unit: string; total_landed_cost: string; status: string }[]>(`/v1/tenders/${detail?.id}/supplier-selections`), enabled: !!detail });
  const offers = useQuery({ queryKey:["tender-offers",detail?.id,offersFor?.id], queryFn:()=>get<{items:Offer[]}>(`/v1/tenders/${detail?.id}/requirement-snapshots/${offersFor?.id}/supplier-offers`),enabled:!!detail&&!!offersFor });
  const estimates = useQuery({ queryKey:["tender-estimates",detail?.id],queryFn:()=>get<Page<CostEstimate>>("/v1/finance/cost-estimates?page_size=100"),enabled:!!detail });
  const workflow = useQuery({ queryKey:["tender-workflow",detail?.id],queryFn:()=>get<Workflow>(`/v1/tenders/${detail?.id}/workflow`),enabled:!!detail });
  const customers = useQuery({ queryKey:["workflow-customers"],queryFn:()=>get<Page<Customer>>("/v1/customers?page_size=100"),enabled:!!detail });
  const materials = useQuery({ queryKey:["workflow-materials"], queryFn:()=>get<Page<Material>>("/v1/materials?page_size=100"), enabled:!!detail });
  const refresh = () => { ["tenders", "tender-docs", "tender-boq", "tender-evidence", "tender-req", "tender-snapshots", "tender-selections", "tender-workflow", "workflow-materials", "workflow-customers", "estimates", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); };

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
  const uploadNewTenderMut = useMutation({
    mutationFn: async (file: File) => {
      const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
      const tender = await post<Tender>("/v1/tenders", { number: `JRS-UPLOAD-${stamp}`, title: file.name.replace(/\.[^.]+$/, ""), project_type: "INDUSTRIAL", description: "Original document uploaded for review and extraction." });
      await apiUpload<Doc>(`/v1/tenders/${tender.id}/documents`, file);
      return tender;
    },
    onSuccess: (tender) => { setDetail(tender); toast.push("success", "Tender uploaded. Review the source document, then select Extract BOQ."); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Tender upload failed"),
  });
  const extractMut = useMutation({
    mutationFn: (docId: string) => post<{ job_id: string; status: string; candidates: number }>(`/v1/tenders/${detail?.id}/documents/${docId}/extract`),
    onSuccess: (r) => { toast.push("success", `Extraction complete — ${r.candidates} candidate line(s), all PENDING review`); refresh(); },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Extraction failed"),
  });
  const reviewMut = useMutation({
    mutationFn: ({ itemId, decision, materialId }: { itemId: string; decision: "CONFIRMED" | "REJECTED"; materialId?: string }) =>
      api(`/v1/tenders/${detail?.id}/boq/${itemId}/review`, { method: "PATCH", body: { review_status: decision, ...(materialId ? { material_id: materialId } : {}) } }),
    onSuccess: () => refresh(),
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Review failed"),
  });
  const snapshotMut = useMutation({ mutationFn:()=>post(`/v1/tenders/${detail?.id}/requirement-snapshots`), onSuccess:()=>{toast.push("success","Approved requirements saved");refresh();}, onError:(e)=>toast.push("error",e instanceof Error?e.message:"Snapshot failed") });
  const bomMut = useMutation({ mutationFn:()=>post<Workflow>(`/v1/tenders/${detail?.id}/workflow/bom`), onSuccess:()=>{toast.push("success","Tender BOM generated");refresh();}, onError:(e)=>toast.push("error",e instanceof Error?e.message:"BOM failed") });
  const customerMut = useMutation({ mutationFn:()=>post<Workflow>(`/v1/tenders/${detail?.id}/workflow/customer`,{customer_id:customerId}), onSuccess:()=>{toast.push("success","Quotation customer selected");refresh();}, onError:(e)=>toast.push("error",e instanceof Error?e.message:"Customer selection failed") });
  const estimateMut = useMutation({ mutationFn:()=>{ const rows=snapshots.data??[]; const version=workflow.data?.requirement_snapshot_version ?? Math.max(...rows.map(s=>s.version)); return post<Workflow>(`/v1/tenders/${detail?.id}/workflow/estimate`,{demo_rates:rows.filter(s=>s.version===version).map(s=>({tender_requirement_snapshot_id:s.id,unit_rate:demoRates[s.id]})),processing_cost:0,freight_cost:0,testing_cost:0,overhead_cost:0,contingency_pct:0}); }, onSuccess:()=>{toast.push("success","Draft demo-rate estimate created");refresh();}, onError:(e)=>toast.push("error",e instanceof Error?e.message:"Estimate failed") });
  const quotationMut = useMutation({ mutationFn:()=>post<Workflow>(`/v1/tenders/${detail?.id}/workflow/quotation`,{}), onSuccess:()=>{toast.push("success","Quotation generated");refresh();}, onError:(e)=>toast.push("error",e instanceof Error?e.message:"Quotation failed") });
  const createMaterialMut = useMutation({ mutationFn:()=>post<Material>("/v1/materials", materialForm), onSuccess:(m)=>{ if (createMaterialFor) setMappedMaterial(v=>({...v,[createMaterialFor.id]:m.id})); setCreateMaterialFor(null); toast.push("success","Material created; review and approve the BOQ line to save its mapping"); refresh(); }, onError:(e)=>toast.push("error",e instanceof Error?e.message:"Material creation failed") });
  const createCustomerMut = useMutation({ mutationFn:()=>post<Customer>("/v1/customers", customerForm), onSuccess:(c)=>{ setCustomerId(c.id); setCreateCustomerOpen(false); toast.push("success","Customer created; select it to attach it to this tender workflow"); refresh(); }, onError:(e)=>toast.push("error",e instanceof Error?e.message:"Customer creation failed") });
  const submissionMut = useMutation({ mutationFn:()=>post<Workflow>(`/v1/tenders/${detail?.id}/workflow/submission`, { status:"MANUALLY_SUBMITTED", external_submission_reference:submissionRef }), onSuccess:()=>{toast.push("success","External submission reference saved"); refresh();}, onError:(e)=>toast.push("error",e instanceof Error?e.message:"Submission update failed") });

  const cols: ColumnDef<Tender, unknown>[] = [
    { accessorKey: "number", header: "Tender #", cell: (c) => <div className="space-y-1"><span className="font-medium text-primary">{c.getValue() as string}</span>{c.row.original.is_demo && <div><span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">TRAINING TENDER</span></div>}</div> },
    { accessorKey: "title", header: "Title", cell: (c) => <div><span>{c.getValue() as string}</span>{c.row.original.is_demo && <p className="mt-1 text-[11px] text-amber-700">SIMULATED — not a live government opportunity</p>}</div> },
    { accessorKey: "project_type", header: "Type", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "value", header: "Est. value", cell: (c) => <span className="tabular-nums">{fmtMoney(c.row.original.estimated_value)}</span> },
    { id: "due", header: "Deadline", cell: (c) => {
      const days = daysUntil(c.row.original.submission_deadline);
      return <span className={`text-xs ${days !== null && days <= 3 ? "font-semibold text-red-600" : ""}`}>{fmtDate(c.row.original.submission_deadline)}{days !== null ? ` (${days}d)` : ""}</span>; } },
    { accessorKey: "status", header: "Status", cell: (c) => <Badge value={c.getValue() as string} /> },
    { id: "boq", header: "Docs / BOQ", cell: (c) => <span className="text-xs text-muted-foreground">{c.row.original.documents_count} / {c.row.original.boq_items_count}</span> },
  ];
  const tenders = list.data?.items ?? [];
  const totalValue = tenders.reduce((sum, tender) => sum + Number(tender.estimated_value || 0), 0);
  const active = tenders.filter((tender) => !["LOST", "WON", "CANCELLED"].includes(tender.status)).length;
  const dueSoon = tenders.filter((tender) => { const days = daysUntil(tender.submission_deadline); return days !== null && days >= 0 && days <= 14; }).length;
  const statusData = Object.entries(tenders.reduce<Record<string, number>>((result, tender) => { result[tender.status] = (result[tender.status] ?? 0) + 1; return result; }, {})).map(([name, value]) => ({ name, value }));
  const typeData = Object.entries(tenders.reduce<Record<string, number>>((result, tender) => { result[tender.project_type] = (result[tender.project_type] ?? 0) + 1; return result; }, {})).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
  const cleanQuantity = (value: string | number | null | undefined, unit = "MT") => value === null || value === undefined || value === "" ? "Not available" : fmtQty(Number(value), unit);
  const boqByUnit = Object.entries((boq.data ?? []).reduce<Record<string, number>>((totals, item) => {
    if (item.unit && item.quantity) totals[item.unit] = (totals[item.unit] ?? 0) + Number(item.quantity);
    return totals;
  }, {})).map(([unit, quantity]) => ({ unit, quantity }));
  const materialDistribution = Object.entries((boq.data ?? []).filter(item => item.unit === "MT" && item.quantity).reduce<Record<string, number>>((totals, item) => {
    const label = item.form || item.raw_description || "Unclassified"; totals[label] = (totals[label] ?? 0) + Number(item.quantity); return totals;
  }, {})).map(([name, value]) => ({ name, value }));
  const gradeDistribution = Object.entries((boq.data ?? []).filter(item => item.quantity).reduce<Record<string, number>>((totals, item) => {
    const label = item.grade || "Unspecified"; totals[label] = (totals[label] ?? 0) + Number(item.quantity); return totals;
  }, {})).map(([name, value]) => ({ name, value }));

  return (
    <div className="mx-auto max-w-[1450px] space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-lg font-bold">Tender Discovery & BOQ</h1>
          <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} Jayraj-scoped tenders · extraction results always require human review</p></div>
        <div className="flex gap-2"><input ref={newTenderFileRef} type="file" accept=".pdf,.xlsx,.xls,.csv,.txt" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadNewTenderMut.mutate(file); e.target.value = ""; }} /><Button size="sm" variant="outline" loading={uploadNewTenderMut.isPending} onClick={() => newTenderFileRef.current?.click()}><UploadCloud className="h-3.5 w-3.5" /> Upload Tender</Button><Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="h-3.5 w-3.5" /> New tender</Button></div>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Tender portfolio" value={list.data?.total ?? "—"} hint="Organization-scoped tenders" icon={<ClipboardList className="h-5 w-5" />} /><MetricCard label="Active workflow" value={list.data ? active : "—"} hint="Not won, lost or cancelled" icon={<FileText className="h-5 w-5" />} /><MetricCard label="Deadline within 14 days" value={list.data ? dueSoon : "—"} hint="Based on recorded submission dates" icon={<CalendarClock className="h-5 w-5" />} /><MetricCard label="Estimated portfolio value" value={list.data ? fmtMoney(totalValue) : "—"} hint="Only records with an estimated value" icon={<IndianRupee className="h-5 w-5" />} /></section>
      <section className="grid gap-4 xl:grid-cols-2"><CompactChartCard title="Tender status" subtitle="Current workflow distribution"><div className="h-[220px]">{statusData.length ? <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={statusData} dataKey="value" nameKey="name" innerRadius={52} outerRadius={78} paddingAngle={2}>{statusData.map((item, index) => <Cell key={item.name} fill={["#1769aa", "#0f9f75", "#d98a14", "#b45309", "#94a3b8"][index % 5]} />)}</Pie><Tooltip formatter={(value) => [`${value} tenders`, "Count"]} /></PieChart></ResponsiveContainer> : <p className="grid h-full place-items-center text-sm text-muted-foreground">No tender statuses to chart.</p>}</div></CompactChartCard><CompactChartCard title="Tender types" subtitle="Project categories from current records"><div className="h-[220px]">{typeData.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={typeData} layout="vertical" margin={{ left: 4, right: 12 }}><XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} /><YAxis dataKey="name" type="category" width={95} tick={{ fontSize: 11 }} /><Tooltip formatter={(value) => [`${value} tenders`, "Count"]} /><Bar dataKey="value" fill="#1769aa" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer> : <p className="grid h-full place-items-center text-sm text-muted-foreground">No tender types to chart.</p>}</div></CompactChartCard></section>

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><CardHeader><div><CardTitle>Tender workspace</CardTitle><p className="mt-1 text-xs text-muted-foreground">Open a tender to review its BOQ, BOM, inventory fit and commercial workflow.</p></div></CardHeader><CardContent>{list.isLoading ? <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{Array.from({length:6}).map((_,i)=><div key={i} className="h-40 animate-pulse rounded-xl bg-slate-100" />)}</div> : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{tenders.map(t=>{const days=daysUntil(t.submission_deadline);const training=t.is_demo||t.title.startsWith("[TRAINING]");return <button key={t.id} type="button" onClick={()=>setDetail(t)} className="group rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md"><div className="flex items-start justify-between gap-2"><span className="text-xs font-bold text-blue-700">{t.number}</span><Badge value={t.status} /></div><h3 className="mt-3 line-clamp-2 font-semibold text-slate-950">{t.title.replace(/^\[TRAINING TENDER\]\s*/, "")}</h3><div className="mt-3 flex flex-wrap gap-2">{training&&<span className="rounded-full bg-amber-100 px-2 py-1 text-[10px] font-semibold text-amber-800">TRAINING</span>}<span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-700">{t.project_type}</span></div><div className="mt-4 grid grid-cols-3 border-t border-slate-100 pt-3 text-xs"><span><b className="block text-sm text-slate-900">{t.boq_items_count}</b>BOQ lines</span><span><b className="block text-sm text-slate-900">{t.documents_count}</b>documents</span><span><b className={`block text-sm ${days!==null&&days<=14?"text-amber-700":"text-slate-900"}`}>{days===null?"—":`${days}d`}</b>to deadline</span></div><p className="mt-3 text-xs font-semibold text-blue-700">Open tender analysis →</p></button>})}</div>}</CardContent></Card>}

      {/* Tender detail */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail?.title ?? "Tender analysis"} wide>
        {detail && (
          <div className="tender-analysis space-y-5">
            <style>{`.tender-analysis .bg-slate-900 { display: none; } .tender-analysis > div:nth-child(2) { display: none; }`}</style>
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-5 py-4"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><Badge value={detail.status} />{(detail.title.startsWith("[DEMO]") || detail.number.startsWith("JRS-UPLOAD")) && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">TRAINING / USER UPLOADED</span>}</div><h2 className="mt-2 text-xl font-bold text-slate-950">{detail.title}</h2><p className="mt-1 text-sm text-slate-600">{detail.description || "Project description is not recorded in the source tender."}</p><p className="mt-2 text-xs text-slate-500">Reference {detail.number} · {detail.project_type} · {detail.location || "Location not documented"} · Issuer/customer: {detail.customer || "Not documented"} · Deadline: {fmtDate(detail.submission_deadline)}</p></div><div className="min-w-[230px] rounded-lg bg-slate-900 px-4 py-3 text-white"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-300">Official tender estimated value</p><p className="mt-1 text-lg font-bold">{detail.estimated_value ? fmtMoney(detail.estimated_value) : "Not stated in source"}</p><p className="mt-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-300">SteelBid calculated bid estimate</p><p className="mt-1 text-sm font-semibold">{workflow.data?.cost_estimate_id ? "Draft estimate available below" : "Pending BOQ approval and commercial rates."}</p></div></div></div><div className="grid divide-x divide-slate-100 sm:grid-cols-4"><div className="p-3"><p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Source documents</p><p className="mt-1 text-sm font-semibold text-slate-800">{docs.data?.length ?? 0} attached</p></div><div className="p-3"><p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Extraction</p><p className="mt-1 text-sm font-semibold text-slate-800">{(docs.data??[]).some(d=>d.status==="EXTRACTED") ? "Complete — review required" : "Awaiting extraction"}</p></div><div className="p-3"><p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">BOQ review</p><p className="mt-1 text-sm font-semibold text-slate-800">{boq.data?.filter(x => x.review_status === "CONFIRMED").length ?? 0}/{boq.data?.length ?? 0} approved</p></div><div className="p-3"><p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Next action</p><p className="mt-1 text-sm font-semibold text-slate-800">{(boq.data??[]).some(b=>!b.material_id) ? "Map extracted materials" : workflow.data?.bom_version_id ? "Enter commercial rates" : "Approve BOQ requirements"}</p></div></div></div>
            <div className="rounded-lg border border-border bg-muted/30 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Badge value={detail.status} />{detail.title.startsWith("[DEMO]") && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">DEMO RECORD</span>}</div><p className="mt-2 text-sm font-medium">{detail.customer || "Customer not recorded"}</p><p className="mt-1 text-xs text-muted-foreground">{detail.location || "Location not recorded"} · Submission {fmtDate(detail.submission_deadline)}</p></div><div className="text-right"><p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Estimated value</p><p className="mt-1 text-xl font-semibold">{fmtMoney(detail.estimated_value)}</p></div></div></div>
            <div className="hidden">
              <Badge value={detail.status} /><span>{detail.customer}</span>
              <span className="text-xs text-muted-foreground">{detail.location} · due {fmtDate(detail.submission_deadline)}</span>
              <span className="ml-auto font-semibold">{fmtMoney(detail.estimated_value)}</span>
            </div>

            <section className="grid gap-3 lg:grid-cols-3" aria-label="Tender analysis visualizations">
              <CompactChartCard title="Material distribution" subtitle="MT requirements only; non-compatible units are separate"><div className="h-52">{materialDistribution.length ? <ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={materialDistribution} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75}>{materialDistribution.map((row, index) => <Cell key={row.name} fill={["#1769aa", "#0f9f75", "#d98a14", "#7c3aed", "#db2777"][index % 5]} />)}</Pie><Tooltip formatter={(value) => [fmtQty(Number(value), "MT"), "Required"]} /></PieChart></ResponsiveContainer> : <p className="grid h-full place-items-center text-xs text-muted-foreground">No MT BOQ quantities available.</p>}</div></CompactChartCard>
              <CompactChartCard title="BOQ quantities by unit" subtitle="Units remain uncombined"><div className="h-52">{boqByUnit.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={boqByUnit}><XAxis dataKey="unit" tick={{fontSize:11}} /><YAxis tick={{fontSize:11}} /><Tooltip formatter={(value, _name, item) => [fmtQty(Number(value), String(item.payload.unit)), "Quantity"]} /><Bar dataKey="quantity" fill="#1769aa" radius={[4,4,0,0]} /></BarChart></ResponsiveContainer> : <p className="grid h-full place-items-center text-xs text-muted-foreground">No reviewed quantities available.</p>}</div></CompactChartCard>
              <CompactChartCard title="Grade distribution" subtitle="Persisted BOQ grade values"><div className="h-52">{gradeDistribution.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={gradeDistribution} layout="vertical"><XAxis type="number" /><YAxis type="category" dataKey="name" width={70} tick={{fontSize:11}} /><Tooltip /><Bar dataKey="value" fill="#0f9f75" radius={[0,4,4,0]} /></BarChart></ResponsiveContainer> : <p className="grid h-full place-items-center text-xs text-muted-foreground">No grades available.</p>}</div></CompactChartCard>
            </section>
            <section className="grid gap-3 md:grid-cols-4" aria-label="Tender readiness">
              <Card className="border-blue-200 bg-blue-50/40"><CardContent className="py-4"><p className="text-[11px] font-semibold uppercase tracking-wide text-blue-800">BOQ demand</p><p className="mt-2 text-2xl font-bold">{fmtQty((boq.data??[]).filter(x=>x.unit==="MT").reduce((sum,x)=>sum+Number(x.quantity??0),0), "MT")}</p><p className="mt-1 text-xs text-slate-600">{Object.entries((boq.data??[]).filter(x=>x.unit&&x.unit!=="MT").reduce<Record<string,number>>((a,x)=>{a[x.unit!]=(a[x.unit!]??0)+Number(x.quantity??0);return a;},{})).map(([u,q])=>fmtQty(q,u)).join(" · ") || "No other-unit demand"}</p></CardContent></Card>
              <Card className={workflow.data?.bom_version_id ? "border-emerald-200 bg-emerald-50/50" : "border-amber-200 bg-amber-50/50"}><CardContent className="py-4"><p className="text-[11px] font-semibold uppercase tracking-wide">BOM status</p><p className="mt-2 text-lg font-bold">{workflow.data?.bom_version_id ? "Generated" : "Pending approval"}</p><p className="mt-1 text-xs text-slate-600">{workflow.data?.bom_version_id ? `BOM ${workflow.data.bom_version_id.slice(0,8)} is the inventory basis.` : "Approve mapped BOQ requirements to generate it."}</p></CardContent></Card>
              <Card><CardContent className="py-4"><p className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Inventory availability</p><p className="mt-2 text-lg font-bold">{workflow.data?.bom_version_id ? "Checked against BOM" : "Not calculated"}</p><p className="mt-1 text-xs text-slate-600">{workflow.data?.bom_version_id ? `${workflow.data.shortages?.filter(x=>Number(x.shortage_quantity)>0).length??0} material shortage(s)` : "No approved BOM yet — not zero demand."}</p></CardContent></Card>
              <Card><CardContent className="py-4"><p className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Next action</p><p className="mt-2 text-lg font-bold">{workflow.data?.bom_version_id ? "Review shortages" : "Approve BOQ"}</p><p className="mt-1 text-xs text-slate-600">{workflow.data?.bom_version_id ? "Continue to supplier comparison and costing." : "Map each material and confirm the BOQ."}</p></CardContent></Card>
            </section>
            <section className="rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50 to-white p-5">
              <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-blue-800">Steel materials required</p><p className="mt-1 text-sm text-slate-600">Extracted requirements are visible before approval. Review and map them before downstream costing.</p></div><span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-blue-800 shadow-sm">{boq.data?.length ?? 0} extracted material lines</span></div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><div className="rounded-lg border border-blue-100 bg-white p-3"><p className="text-[11px] text-slate-500">Extracted lines</p><b className="mt-1 block text-xl">{boq.data?.length ?? 0}</b></div><div className="rounded-lg border border-blue-100 bg-white p-3"><p className="text-[11px] text-slate-500">Approved</p><b className="mt-1 block text-xl text-emerald-700">{boq.data?.filter(b=>b.review_status==="CONFIRMED").length ?? 0}</b></div><div className="rounded-lg border border-blue-100 bg-white p-3"><p className="text-[11px] text-slate-500">Unmapped</p><b className="mt-1 block text-xl text-amber-700">{boq.data?.filter(b=>!b.material_id).length ?? 0}</b></div><div className="rounded-lg border border-blue-100 bg-white p-3"><p className="text-[11px] text-slate-500">Required MT</p><b className="mt-1 block text-xl">{(boq.data??[]).filter(b=>b.unit==="MT").reduce((sum,b)=>sum+Number(b.quantity??0),0).toFixed(2)} MT</b></div><div className="rounded-lg border border-blue-100 bg-white p-3"><p className="text-[11px] text-slate-500">Other units</p><b className="mt-1 block text-xl">{Object.entries((boq.data??[]).filter(b=>b.unit&&b.unit!=="MT").reduce<Record<string,number>>((a,b)=>{a[b.unit!]=(a[b.unit!]??0)+Number(b.quantity??0);return a;},{})).map(([u,q])=>`${q} ${u}`).join(" · ") || "None"}</b></div></div>
              {(boq.data??[]).length ? <div className="mt-4 overflow-x-auto rounded-lg border border-blue-100 bg-white"><table className="w-full min-w-[900px] text-xs"><thead className="bg-slate-50 text-left uppercase tracking-wide text-slate-500"><tr><th className="p-3">Material / original BOQ</th><th>Grade</th><th>Standard</th><th>Size</th><th>Quantity</th><th>Source</th><th>Review</th><th>Mapping</th></tr></thead><tbody>{boq.data!.map(b=><tr key={b.id} className="border-t border-slate-100"><td className="max-w-[280px] p-3 font-medium" title={b.raw_description}>{b.raw_description}</td><td>{b.grade??"Requires review"}</td><td>{String(b.specification?.standard??"Not extracted")}</td><td>{String(b.specification?.dimensions??b.specification?.size??"Not extracted")}</td><td className="font-semibold">{b.quantity?`${b.quantity} ${b.unit??""}`:"Requires review"}</td><td>{b.page_ref??b.source??"Not recorded"}</td><td><Badge value={b.review_status}/></td><td><Badge value={b.material_id?"MAPPED":"UNMAPPED"}/></td></tr>)}</tbody></table></div> : <p className="mt-4 rounded-lg border border-dashed border-blue-200 bg-white p-4 text-sm text-slate-600">No extracted requirements yet. Upload a source document and run Extract BOQ; downstream estimation remains blocked until requirements are reviewed and mapped.</p>}
            </section>

            {(docs.data?.length ?? 0) === 0 && (boq.data?.length ?? 0) > 0 && <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"><b>Training BOQ available — source document not attached.</b><span className="ml-1">BOQ records can be reviewed and mapped, but document extraction has not occurred.</span></div>}
            <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-end justify-between gap-2"><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-700">Tender workflow</p><p className="mt-1 text-xs text-slate-500">Status is calculated from saved documents, reviewed BOQ lines and persisted workflow records.</p></div><span className="text-xs font-medium text-slate-500">No step is marked complete until its record is saved.</span></div>
              <div className="mt-4 grid gap-2 sm:grid-cols-3 xl:grid-cols-5">{[
                ["Tender selected", true], ["Documents analyzed", (docs.data??[]).some(d=>d.status==="EXTRACTED")], ["BOQ reviewed", (boq.data??[]).length>0 && (boq.data??[]).every(b=>b.review_status!=="PENDING")], ["Materials mapped", (boq.data??[]).length>0 && (boq.data??[]).every(b=>!!b.material_id)], ["BOM generated", !!workflow.data?.bom_version_id], ["Inventory checked", !!workflow.data?.bom_version_id], ["Suppliers compared", (snapshots.data??[]).length>0], ["Estimate prepared", !!workflow.data?.cost_estimate_id], ["Quotation ready", !!workflow.data?.quotation_id],
              ].map(([label, complete])=><div key={String(label)} className={`rounded-lg border px-3 py-2 text-xs ${complete?"border-emerald-200 bg-emerald-50 text-emerald-800":"border-amber-200 bg-white text-amber-800"}`}><span className="font-semibold">{complete?"Complete":"Requires attention"}</span><span className="mt-1 block text-slate-700">{String(label)}</span></div>)}</div>
            </section>

            {/* Documents */}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">1 · Source documents</p>
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
              <Button size="sm" variant="outline" className="mt-2" loading={uploadMut.isPending}
                onClick={() => fileRef.current?.click()}>
                <UploadCloud className="h-3.5 w-3.5" /> Upload Tender</Button>
            </div>

            <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
              <div className="flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-wide text-primary">Tender commercial workflow</p><p className="mt-1 text-xs text-muted-foreground">Progress is based on saved Jayraj records; training rates are clearly non-approved.</p></div><span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-primary">{workflow.data?.quotation_id ? "Quotation ready" : workflow.data?.cost_estimate_id ? "Estimate ready" : workflow.data?.bom_version_id ? "BOM ready" : "BOQ review"}</span></div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" loading={snapshotMut.isPending} onClick={()=>snapshotMut.mutate()}>Approve BOQ requirements</Button>
                <Button size="sm" variant="outline" loading={bomMut.isPending} onClick={()=>bomMut.mutate()} disabled={!snapshots.data?.length}>Generate BOM</Button>
              </div>
              {(workflow.data?.shortages?.length ?? 0) > 0 && <div className="mt-4 grid gap-2 sm:grid-cols-2"><div className="sm:col-span-2 flex items-center justify-between"><b className="text-sm">Inventory & shortages</b><span className="text-xs text-muted-foreground">Eligible stock only</span></div>{workflow.data!.shortages!.map(s=>{const pct=Number(s.required_quantity)>0?Math.min(100,Number(s.available_quantity)/Number(s.required_quantity)*100):0;return <div key={s.bom_item_id} className="rounded-lg border bg-white p-3 text-xs"><div className="flex justify-between"><span>Required <b>{fmtQty(s.required_quantity,s.unit)}</b></span><span className={Number(s.shortage_quantity)>0?"font-semibold text-red-600":"font-semibold text-emerald-700"}>{fmtQty(s.shortage_quantity,s.unit)} short</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-emerald-500" style={{width:`${pct}%`}} /></div><p className="mt-1 text-slate-500">{fmtQty(s.available_quantity,s.unit)} eligible stock</p></div>})}</div>}
              {workflow.data?.bom_version_id && !workflow.data?.cost_estimate_id && <div className="mt-3 space-y-2 rounded border bg-white p-3"><p className="text-xs font-medium">Enter demo commercial rates (not supplier quotations)</p>{(snapshots.data??[]).filter(s=>s.version===(workflow.data?.requirement_snapshot_version ?? Math.max(...(snapshots.data??[]).map(x=>x.version)))).map(s=><div key={s.id} className="flex items-center gap-2 text-xs"><span className="w-40 truncate">{s.form} {s.grade??""} · {s.quantity} {s.unit}</span><Input aria-label={`Demo rate ${s.id}`} value={demoRates[s.id]??""} onChange={e=>setDemoRates(v=>({...v,[s.id]:e.target.value}))} placeholder="INR / unit" /></div>)}<Button size="sm" loading={estimateMut.isPending} onClick={()=>estimateMut.mutate()}>Create Estimate</Button></div>}
              <div className="mt-3 flex flex-wrap gap-2"><Button size="sm" variant="ghost" onClick={()=>window.open(`/api/v1/tenders/${detail.id}/workflow/boq.xlsx`,`_blank`,`noopener`)}>Download BOQ Excel</Button>{workflow.data?.bom_version_id&&<Button size="sm" variant="ghost" onClick={()=>window.open(`/api/v1/tenders/${detail.id}/workflow/bom.xlsx`,`_blank`,`noopener`)}>Download BOM Excel</Button>}{workflow.data?.cost_estimate_id&&<Button size="sm" variant="ghost" onClick={()=>window.open(`/api/v1/tenders/${detail.id}/workflow/estimate.xlsx`,`_blank`,`noopener`)}>Download Estimate Excel</Button>}</div>
              <section className="mt-5 rounded-xl border border-slate-200 bg-white p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">Documents &amp; Reports</p><p className="mt-1 text-xs text-slate-500">Tenant-scoped, persisted-data exports. Training reports carry their simulated-data disclaimer.</p></div><Badge value={detail.data_classification ?? "OPERATIONAL"} /></div><div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3"><Button size="sm" variant="outline" onClick={()=>window.open(`/api/v1/tenders/${detail.id}/reports/analysis.pdf`,`_blank`,`noopener`)}>Tender analysis PDF</Button><Button size="sm" variant="outline" onClick={()=>window.open(`/api/v1/tenders/${detail.id}/reports/boq.pdf`,`_blank`,`noopener`)}>BOQ PDF</Button><Button size="sm" variant="outline" onClick={()=>window.open(`/api/v1/tenders/${detail.id}/workflow/boq.xlsx`,`_blank`,`noopener`)}>BOQ XLSX</Button><Button size="sm" variant="outline" disabled={!workflow.data?.bom_version_id} onClick={()=>window.open(`/api/v1/tenders/${detail.id}/reports/bom.pdf`,`_blank`,`noopener`)}>BOM PDF</Button><Button size="sm" variant="outline" disabled={!workflow.data?.bom_version_id} onClick={()=>window.open(`/api/v1/tenders/${detail.id}/workflow/bom.xlsx`,`_blank`,`noopener`)}>BOM XLSX</Button><Button size="sm" variant="outline" disabled={!workflow.data?.bom_version_id} onClick={()=>window.open(`/api/v1/tenders/${detail.id}/reports/inventory.pdf`,`_blank`,`noopener`)}>Inventory &amp; shortage PDF</Button><Button size="sm" variant="outline" onClick={()=>window.open(`/api/v1/tenders/${detail.id}/reports/supplier-comparison.pdf`,`_blank`,`noopener`)}>Supplier comparison PDF</Button><Button size="sm" variant="outline" disabled={!workflow.data?.cost_estimate_id} onClick={()=>window.open(`/api/v1/tenders/${detail.id}/reports/estimate.pdf`,`_blank`,`noopener`)}>Estimate PDF</Button><Button size="sm" variant="outline" disabled={!workflow.data?.cost_estimate_id} onClick={()=>window.open(`/api/v1/tenders/${detail.id}/workflow/estimate.xlsx`,`_blank`,`noopener`)}>Estimate XLSX</Button><Button size="sm" variant="outline" disabled={!workflow.data?.quotation_id} onClick={()=>window.open(`/api/v1/tenders/${detail.id}/workflow/quotation.pdf`,`_blank`,`noopener`)}>Draft quotation PDF</Button></div>{!(docs.data?.length) && <p className="mt-3 text-xs text-slate-500">Original tender documents: Source document not attached.</p>}</section>
              {workflow.data?.cost_estimate_id && <div className="mt-3 space-y-2 rounded border bg-white p-3"><p className="text-xs font-medium">Quotation customer</p><div className="flex flex-wrap items-center gap-2"><Select aria-label="Quotation customer" value={customerId || workflow.data.customer_id || ""} onChange={e=>setCustomerId(e.target.value)}><option value="">Select existing customer</option>{(customers.data?.items??[]).filter(c=>c.is_active).map(c=><option value={c.id} key={c.id}>{c.name} ({c.code})</option>)}</Select><Button size="sm" variant="outline" onClick={()=>setCreateCustomerOpen(true)}>Create customer</Button><Button size="sm" variant="outline" loading={customerMut.isPending} disabled={!customerId} onClick={()=>customerMut.mutate()}>Select Customer</Button>{(workflow.data.customer_id || customerId)&&<Button size="sm" loading={quotationMut.isPending} onClick={()=>quotationMut.mutate()} disabled={!!workflow.data.quotation_id}>Generate Quotation</Button>}{workflow.data.quotation_id&&<Button size="sm" variant="outline" onClick={()=>window.open(`/api/v1/tenders/${detail.id}/workflow/quotation.pdf`,`_blank`,`noopener`)}>Download quotation PDF</Button>}</div>{workflow.data.quotation_id&&<div className="flex flex-wrap items-center gap-2 pt-2"><Input aria-label="External submission reference" value={submissionRef} onChange={e=>setSubmissionRef(e.target.value)} placeholder="Actual external submission reference" /><Button size="sm" disabled={!submissionRef} loading={submissionMut.isPending} onClick={()=>submissionMut.mutate()}>Record manual submission</Button><span className="text-xs text-muted-foreground">{workflow.data.submission_status ?? "READY"}</span></div>}</div>}
            </div>

            {/* Material mapping must precede approval: extracted text is never silently converted into a catalogue item. */}
            {(boq.data?.length ?? 0) > 0 && <section className="rounded-xl border border-blue-200 bg-blue-50/40 p-4">
              <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-blue-900">2 · Material mapping & approval</p><p className="mt-1 text-xs text-slate-600">Map each extracted requirement to Jayraj's tenant material catalogue, then explicitly approve it.</p></div><div className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-blue-900 shadow-sm">{boq.data!.filter(b=>b.material_id).length} of {boq.data!.length} BOQ items mapped</div></div>
              <div className="mt-3 grid gap-3">
                {boq.data!.filter(b=>!b.material_id || b.review_status === "PENDING").map((b) => { const term=(materialSearch[b.id]??"").toLowerCase(); const matches=(materials.data?.items??[]).filter(m=>m.is_active && (!term || `${m.sku} ${m.name} ${m.form} ${m.grade} ${m.standard??""}`.toLowerCase().includes(term))).slice(0,30); const selected=mappedMaterial[b.id] ?? b.material_id ?? ""; return <div key={b.id} className="rounded-lg border border-blue-100 bg-white p-3 shadow-sm"><div className="grid gap-3 lg:grid-cols-[1.2fr_.8fr]"><div><p className="text-sm font-semibold text-slate-900">{b.raw_description}</p><div className="mt-2 flex flex-wrap gap-2 text-[11px]"><span className="rounded bg-slate-100 px-2 py-1">Grade: {b.grade ?? "needs review"}</span><span className="rounded bg-slate-100 px-2 py-1">Standard: {String(b.specification?.standard ?? b.specification?.standard_code ?? "not extracted")}</span><span className="rounded bg-slate-100 px-2 py-1">Size: {String(b.specification?.size ?? b.specification?.dimensions ?? "not extracted")}</span><span className="rounded bg-slate-100 px-2 py-1">Qty: {b.quantity ? `${b.quantity} ${b.unit ?? ""}` : "needs review"}</span><span className="rounded bg-amber-50 px-2 py-1 text-amber-800">Source: {b.source ?? "document"}{b.page_ref ? ` · page ${b.page_ref}` : " · page not extracted"}</span></div></div><div className="space-y-2"><Input aria-label={`Search compatible material ${b.id}`} value={materialSearch[b.id]??""} onChange={e=>setMaterialSearch(v=>({...v,[b.id]:e.target.value}))} placeholder="Search Jayraj material catalogue" /><Select aria-label={`Material mapping ${b.id}`} value={selected} onChange={e=>setMappedMaterial(v=>({...v,[b.id]:e.target.value}))}><option value="">Select compatible material</option>{matches.map(m=><option key={m.id} value={m.id}>{m.sku} · {m.name} · {m.grade}{m.standard?` / ${m.standard}`:""}</option>)}</Select><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={()=>{setCreateMaterialFor(b);setMaterialForm({sku:"",name:b.raw_description.slice(0,120),form:b.form??"",grade:b.grade??"",standard:String(b.specification?.standard??""),base_unit:b.unit??"MT"});}}>Create material</Button><Button size="sm" disabled={!selected || b.review_status === "CONFIRMED"} loading={reviewMut.isPending} onClick={()=>reviewMut.mutate({itemId:b.id,decision:"CONFIRMED",materialId:selected})}>Approve mapping</Button>{b.review_status === "CONFIRMED" && <Badge value="CONFIRMED" />}</div></div></div></div>; })}
              </div>
            </section>}

            {/* BOQ review */}
            {(boq.data?.length ?? 0) > 0 && (
              <div>
                <div className="mb-3 grid gap-2 sm:grid-cols-3"><div className="rounded-md border border-border p-3"><p className="text-[11px] text-muted-foreground">Extracted lines</p><p className="mt-1 text-lg font-semibold">{boq.data!.length}</p></div><div className="rounded-md border border-border p-3"><p className="text-[11px] text-muted-foreground">Confirmed</p><p className="mt-1 text-lg font-semibold text-emerald-700">{boq.data!.filter((item) => item.review_status === "CONFIRMED").length}</p></div><div className="rounded-md border border-border p-3"><p className="text-[11px] text-muted-foreground">Mapped materials</p><p className="mt-1 text-lg font-semibold text-primary">{boq.data!.filter((item) => item.material_id).length}</p></div></div>
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
                              <Button size="sm" variant="ghost" aria-label="Confirm" disabled={!b.material_id} title={b.material_id ? "Confirm mapped BOQ item" : "Map a tenant material before approval"}
                                onClick={() => reviewMut.mutate({ itemId: b.id, decision: "CONFIRMED", materialId: b.material_id ?? undefined })}><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /></Button>
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
                <div className="mb-2"><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">3 · Stock feasibility</p><p className="mt-1 text-sm text-slate-600">Required quantity compared with available, allocatable stock.</p></div>
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

            <div>
              <div className="mb-2"><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">4 · Supplier allocation</p><p className="mt-1 text-sm text-slate-600">Compare compatible landed-cost offers after a requirement set is approved.</p></div>
              {snapshots.data?.length ? snapshots.data.map((s) => {
                const allocated = (selections.data ?? []).filter((x) => x.snapshot_id === s.id && x.status === "SELECTED").reduce((sum, x) => sum + Number(x.selected_qty), 0);
                return <div key={s.id} className="mb-2 rounded-md border border-border p-2 text-xs"><div className="flex justify-between"><b>v{s.version} · {s.form} {s.grade ?? ""}</b><span>{s.quantity} {s.unit} requirement · {allocated} allocated</span></div><Button size="sm" variant="outline" className="mt-2" onClick={()=>setOffersFor(s)}>Compare supplier offers</Button></div>;
              }) : <p className="text-xs text-muted-foreground">Create an approved requirement snapshot before selecting suppliers.</p>}
              {(selections.data ?? []).map((s) => <div key={s.id} className="flex justify-between rounded bg-muted/50 px-2 py-1 text-xs"><span>{s.selected_qty} {s.unit} · {s.status}</span><span>{fmtMoney(s.total_landed_cost)}</span></div>)}
            </div>

            {(() => { const estimate=estimates.data?.items.find(x=>x.tender_id===detail.id); const benchmark=estimate?.context?.historical_market_benchmark; return estimate?<div><p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Draft tender cost estimate</p><div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs"><div className="mb-2 flex justify-between"><b>Versioned estimate</b><Badge value={estimate.status}/></div>{benchmark&&<div className="mb-3 rounded border border-blue-200 bg-blue-50 p-2 text-blue-950"><b>Historical market benchmark</b><span className="ml-2">{benchmark.material_form} {benchmark.grade} · {fmtMoney(benchmark.unit_price)}/{benchmark.unit} · {benchmark.region} · {benchmark.price_basis}</span><small className="mt-1 block text-blue-800">Observed {fmtDate(benchmark.observed_on)} for costing reference {fmtDate(estimate.context?.costing_reference_date)}. Reference market price only — not a supplier purchase price.</small></div>}<div className="grid grid-cols-2 gap-2 sm:grid-cols-4"><span>Material<b className="block">{fmtMoney(estimate.material_cost)}</b></span><span>Fabrication<b className="block">{fmtMoney(estimate.fabrication_cost)}</b></span><span>Freight<b className="block">{fmtMoney(estimate.freight_cost)}</b></span><span>Overheads<b className="block">{fmtMoney(estimate.overhead_cost)}</b></span></div><p className="mt-2 border-t border-amber-200 pt-2 font-semibold">Total estimated cost <span className="float-right">{fmtMoney(estimate.total_cost)}</span></p><p className="mt-1 text-[10px] text-amber-800">Draft only — not an approved quotation.</p></div></div>:null; })()}

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

      <Modal open={!!offersFor} onClose={()=>setOffersFor(null)} title={`Supplier comparison — ${offersFor?.form ?? ""} ${offersFor?.grade ?? ""}`} wide>
        <p className="mb-3 text-xs text-muted-foreground">Requirement: {offersFor?.quantity} {offersFor?.unit}. Landed costs use persisted quoted price, freight and applicable charges.</p>
        {offers.isLoading?<p className="text-sm">Loading offers…</p>:offers.data?.items.length?<div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr className="border-b text-left"><th className="py-2">Supplier</th><th>Quote</th><th>Freight / charges</th><th>Landed</th><th>Total landed</th><th>Qty</th><th>Valid until</th><th>Selection / compatibility</th></tr></thead><tbody>{offers.data.items.map(o=>{const selected=(selections.data??[]).some(s=>s.snapshot_id===offersFor?.id&&s.supplier_quote_id===o.supplier_quote_id&&s.status==="SELECTED");return <tr key={o.supplier_quote_id} className="border-b"><td className="py-2 font-semibold">{o.supplier_name}</td><td>{fmtMoney(o.unit_price)}/{o.unit}</td><td>{fmtMoney(o.freight_per_unit)}{o.tax_pct&&Number(o.tax_pct)>0?` + ${o.tax_pct}% tax${o.tax_recoverable?" (recoverable)":""}`:""}</td><td className="font-semibold">{fmtMoney(o.landed_cost_per_unit)}/{o.unit}</td><td className="font-semibold">{fmtMoney(o.total_landed_cost)}</td><td>{o.quantity} {o.unit}</td><td>{fmtDate(o.valid_until)}</td><td className="space-y-1">{selected&&<Badge value="SELECTED"/>}<Badge value={o.compatible?"COMPATIBLE":"UNCONFIRMED"}/></td></tr>})}</tbody></table></div>:<p className="text-sm text-muted-foreground">No supplier offers are available for this requirement.</p>}
      </Modal>

      <Modal open={!!createMaterialFor} onClose={()=>setCreateMaterialFor(null)} title="Create tenant material for BOQ mapping">
        <p className="mb-3 text-xs text-muted-foreground">This creates a Jayraj catalogue record from details entered and reviewed by the user; no missing specification is inferred.</p>
        <div className="space-y-3"><div className="grid grid-cols-2 gap-3"><div><Label>SKU</Label><Input value={materialForm.sku} onChange={e=>setMaterialForm(v=>({...v,sku:e.target.value}))} placeholder="JRS-..." /></div><div><Label>Form</Label><Input value={materialForm.form} onChange={e=>setMaterialForm(v=>({...v,form:e.target.value}))} /></div></div><div><Label>Material name</Label><Input value={materialForm.name} onChange={e=>setMaterialForm(v=>({...v,name:e.target.value}))} /></div><div className="grid grid-cols-2 gap-3"><div><Label>Grade</Label><Input value={materialForm.grade} onChange={e=>setMaterialForm(v=>({...v,grade:e.target.value}))} /></div><div><Label>Standard</Label><Input value={materialForm.standard} onChange={e=>setMaterialForm(v=>({...v,standard:e.target.value}))} placeholder="Enter if known" /></div></div><div className="flex justify-end gap-2"><Button variant="outline" onClick={()=>setCreateMaterialFor(null)}>Cancel</Button><Button loading={createMaterialMut.isPending} disabled={!materialForm.sku||!materialForm.name||!materialForm.form||!materialForm.grade} onClick={()=>createMaterialMut.mutate()}>Create material</Button></div></div>
      </Modal>

      <Modal open={createCustomerOpen} onClose={()=>setCreateCustomerOpen(false)} title="Create customer">
        <p className="mb-3 text-xs text-muted-foreground">Enter authorized customer information. This record is saved only to the active tenant.</p><div className="space-y-3"><div className="grid grid-cols-2 gap-3"><div><Label>Customer code</Label><Input value={customerForm.code} onChange={e=>setCustomerForm(v=>({...v,code:e.target.value}))} /></div><div><Label>Category</Label><Input value={customerForm.category} onChange={e=>setCustomerForm(v=>({...v,category:e.target.value}))} /></div></div><div><Label>Customer name</Label><Input value={customerForm.name} onChange={e=>setCustomerForm(v=>({...v,name:e.target.value}))} /></div><div><Label>GSTIN (optional)</Label><Input value={customerForm.gstin} onChange={e=>setCustomerForm(v=>({...v,gstin:e.target.value}))} /></div><div className="flex justify-end gap-2"><Button variant="outline" onClick={()=>setCreateCustomerOpen(false)}>Cancel</Button><Button loading={createCustomerMut.isPending} disabled={!customerForm.code||!customerForm.name} onClick={()=>createCustomerMut.mutate()}>Create customer</Button></div></div>
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
