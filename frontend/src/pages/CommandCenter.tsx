import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Area, AreaChart, Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, ArrowRight, BellRing, Boxes, CalendarDays, CheckCircle2, ClipboardCheck, FileText, Gavel, PackageSearch, Plus, Quote, RefreshCw, Sparkles, TrendingUp, Warehouse } from "lucide-react";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Briefing, DashboardSummary, EnhancedDashboardSummary } from "@/lib/types";
import { fmtDate, fmtMoney, fmtQty } from "@/lib/format";
import { Button, Card, CardContent, ErrorState, Skeleton, Select } from "@/components/ui";

const MarketIntelligencePanel = React.lazy(() => import("@/components/dashboard/MarketIntelligencePanel"));
const stages = ["DRAFT", "IN_REVIEW", "ESTIMATING", "BID_SUBMITTED", "WON"];
const stageNames: Record<string, string> = { DRAFT: "Draft", IN_REVIEW: "Review", ESTIMATING: "Estimating", BID_SUBMITTED: "Submitted", WON: "Won" };
const colours = ["#cbd5e1", "#1682e8", "#36c5df", "#ff6a15", "#1dbb78"];

function Metric({ label, value, hint: _hint, icon: Icon, tone = "blue" }: { label: string; value: string; hint: string; icon: React.ElementType; tone?: string }) {
  const toneClass: Record<string, string> = { blue: "bg-blue-100 text-blue-600", green: "bg-emerald-100 text-emerald-600", amber: "bg-amber-100 text-amber-600", cyan: "bg-cyan-100 text-cyan-600" };
  return <Card className="min-w-0 rounded-xl border-slate-200 shadow-[0_5px_18px_rgba(56,111,180,.07)]">
<CardContent className="flex h-[86px] items-start gap-3 px-4 py-3">
<span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${toneClass[tone]}`}>
<Icon className="h-5 w-5" />
</span>
<div className="min-w-0">
<p className="truncate text-[11px] font-semibold text-slate-700">{label}</p>
<p className="mt-0.5 text-[22px] font-bold leading-tight tracking-tight text-slate-950">{value}</p>
</div>
</CardContent>
</Card>;
}

function Ring({ percent, label, color = "#22c55e" }: { percent: number; label: string; color?: string }) { return <div className="grid h-24 w-24 shrink-0 place-items-center rounded-full" style={{ background: `conic-gradient(${color} ${percent}%, #e5edf7 0)` }}>
<div className="grid h-[76px] w-[76px] place-items-center rounded-full bg-white text-center">
<b className="text-2xl">{percent}%</b>
<span className="text-[10px] font-semibold text-slate-600">{label}</span>
</div>
</div>; }

function TenderCard({ d }: { d: EnhancedDashboardSummary }) {
  const counts = stages.map(s => Number(d.tender_pipeline[s] ?? 0)); const active = counts.reduce((a, b) => a + b, 0);
  const pie = counts.map((value, i) => ({ value, name: stageNames[stages[i]], fill: colours[i] }));
  return <Card className="rounded-xl border-slate-200">
<div className="flex items-center justify-between border-b px-4 py-3">
<h2 className="text-lg font-bold">Tender Intelligence</h2>
<Link to="/tenders" className="text-xs font-bold text-blue-600">View Tenders <ArrowRight className="inline h-3.5" />
</Link>
</div>
<div className="grid min-h-[240px] grid-cols-1 md:grid-cols-[1.1fr_.9fr]">
<div className="flex items-center justify-center gap-5 p-3">
<div className="relative h-40 w-40">
<ResponsiveContainer>
<PieChart>
<Pie data={pie} dataKey="value" innerRadius={52} outerRadius={78} paddingAngle={1}>{pie.map((x, i) => <Cell key={i} fill={x.fill} />)}</Pie>
</PieChart>
</ResponsiveContainer>
<div className="absolute inset-0 grid place-items-center text-center">
<div>
<b className="text-2xl">{active}</b>
<p className="text-[11px] font-semibold leading-3">Active<br />Tenders</p>
</div>
</div>
</div>
<div className="space-y-3">{pie.map(x => <div key={x.name} className="flex w-28 items-center justify-between text-xs">
<span className="flex items-center gap-2">
<i className="h-2.5 w-2.5 rounded-full" style={{ background: x.fill }} />{x.name}</span>
<b>{x.value}</b>
</div>)}</div>
</div>
<div className="border-l border-slate-100 p-4">
<p className="mb-3 text-sm font-bold">Upcoming Deadlines</p>{d.new_tenders.slice(0, 3).map(t => <Link to="/tenders" key={t.id} className="mb-3 flex gap-2 text-xs hover:text-blue-600">
<CalendarDays className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
<span>
<b className="block">{fmtDate(t.deadline)}</b>
<span>{t.title} (Submission)</span>
</span>
</Link>)}{!d.new_tenders.length && <p className="text-xs text-slate-500">No upcoming submission deadlines.</p>}</div>
</div>
</Card>;
}

export default function CommandCenter() {
  const { activeOrg } = useAuth();
  const orgId = activeOrg?.id;
  const [selectedTender, setSelectedTender] = React.useState("");
  const tenders = useQuery({ queryKey:["dashboard-tenders",orgId], enabled:!!orgId, queryFn:()=>get<{items:{id:string;number:string;title:string}[]}>("/v1/tenders?page_size=100") });
  React.useEffect(()=>{ if (!selectedTender && tenders.data?.items.length) setSelectedTender(tenders.data.items.find(t=>t.number==="DEMO-JRS-WH-001")?.id ?? tenders.data.items[0].id); },[selectedTender,tenders.data]);
  const tenderContext = useQuery({ queryKey:["tender-context",selectedTender], enabled:!!selectedTender, queryFn:()=>get<{status:string;coverage:Record<string,{required:string;available:string;covered:string;uncovered:string;percent:string}>;unit_totals:Record<string,string>;materials:{name:string;unit:string;required:string;available:string;covered:string;uncovered:string}[];grade_distribution:{grade:string;quantity:string}[]}>(`/v1/dashboard/tender-context/${selectedTender}`) });
  const selectedBoq = useQuery({ queryKey:["command-center-boq", selectedTender], enabled:!!selectedTender, queryFn:()=>get<{quantity:string|null;unit:string|null;review_status:string}[]>(`/v1/tenders/${selectedTender}/boq`) });
  const summary = useQuery({ queryKey: ["dashboard", "enhanced", orgId, 30], enabled: !!orgId, staleTime: 60_000, queryFn: async () => { try { return await get<EnhancedDashboardSummary>("/v1/dashboard/enhanced?days=30"); } catch { const base = await get<DashboardSummary>("/v1/dashboard/summary"); return { ...base, market_trends: [], market_comparisons: [], scenario_summary: { total_scenarios: 0, period_days: 30 }, new_tenders: [], tender_pipeline: {}, tender_amendments: [], boq_review_status: { pending_review: 0 }, bom_readiness: [], tender_shortages: [], inventory_breakdown: { on_hand: "0", available: "0", reserved: "0", quality_held: "0", unit: "MT" }, atp_by_material: [], active_costing_quotes: [], margin_exposure: { total_pending_value: "0", at_risk_margin: null }, pricing_scenarios: { total_scenarios: 0, tender_related: null }, open_rfqs: { count: 0 }, pending_quotes: { count: 0 }, delivery_risks: [], approval_queue: [], price_alerts: { stale_observations: 0, stale_threshold_days: 14 } } satisfies EnhancedDashboardSummary; } } });
  const briefing = useQuery({ queryKey: ["briefing", orgId], enabled: !!orgId, queryFn: () => get<Briefing>("/v1/ai/daily-briefing"), staleTime: 60_000 });
  if (summary.error) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  if (!summary.data) return <div className="grid grid-cols-3 gap-4">{Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} className="h-32" />)}</div>;
  const d = summary.data, inv = d.inventory_breakdown, active = stages.reduce((n, s) => n + Number(d.tender_pipeline[s] ?? 0), 0), shortage = d.tender_shortages.reduce((n, x) => n + Number(x.shortage_qty || 0), 0), context=tenderContext.data;
  const mtCoverage=context?.coverage.MT, coveragePercent=mtCoverage?Math.round(Number(mtCoverage.percent)):0;
  const selectedTenderName=tenders.data?.items.find(t=>t.id===selectedTender)?.title;
  const boqMt = Number(context?.unit_totals?.MT ?? 0) || (selectedBoq.data ?? []).filter(x=>x.unit === "MT" && x.review_status !== "REJECTED").reduce((sum,x)=>sum + Number(x.quantity ?? 0), 0);
  const readiness = !selectedTender ? "Select a tender" : context?.status === "AWAITING_APPROVED_BOM" ? (boqMt ? `${fmtQty(boqMt, "MT")} in BOQ — BOM pending` : "BOQ demand awaiting review") : !mtCoverage ? "No approved MT BOM requirement" : Number(mtCoverage.uncovered) > 0 ? "Procurement action needed" : "Fully covered by eligible stock";
  const atp = d.atp_by_material.slice(0, 5).map(x => ({ name: x.name.split(" ")[0], amount: Number(x.available_atp) }));
  const cost = d.active_costing_quotes.slice(0, 3).map((x, i) => ({ name: ["Material", "Fabrication", "Overheads"][i], value: Number(x.estimated_cost || 0) / 100000 }));
  const totalCost = cost.reduce((n, x) => n + x.value, 0);
  return <div className="tender-aware-dashboard mx-auto max-w-[1450px] space-y-3 pb-4">
    <section className="flex flex-wrap items-end justify-between gap-3">
<div>
<h1 className="text-[26px] font-bold tracking-tight text-slate-950">Command Center</h1>
<p className="text-sm font-medium text-slate-500">Real-time steel intelligence, smarter decisions</p>
</div>
<div className="flex items-center gap-2">
<span className="text-xs font-semibold text-slate-700">
<i className="mr-1 inline-block h-3 w-3 rounded-full bg-emerald-500" />Live Ã‚Â· {new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</span>
<Button variant="outline" size="sm" onClick={() => summary.refetch()} loading={summary.isFetching}>
<RefreshCw className="h-4 w-4" />Refresh</Button>
<Link to="/tenders">
<Button size="sm">
<Plus className="h-4 w-4" />New Tender</Button>
</Link>
</div>
</section>
    <section className="grid grid-cols-2 gap-2 xl:grid-cols-6">
<Metric label="Active Tenders" value={String(active)} hint="Persisted tender records" icon={TrendingUp} />
<Metric label="Pipeline Value" value={d.tender_pipeline.active_estimated_value ? fmtMoney(String(d.tender_pipeline.active_estimated_value)) : "-"} hint="Recorded official estimates" icon={TrendingUp} tone="blue" />
<Metric label="Eligible Inventory" value={fmtQty(inv.available, inv.unit)} hint="Portfolio-wide eligible stock" icon={Warehouse} tone="cyan" />
<Metric label="Procurement Shortage" value={shortage ? fmtQty(String(shortage), "MT") : "0 MT"} hint="Jayraj approved BOMs" icon={AlertTriangle} tone="amber" />
<Metric label="Pending Quotations" value={String(d.pending_quotes.count)} hint="Persisted quotation workflow" icon={Quote} />
<Metric label="Pending Approvals" value={String(d.approval_queue.length)} hint={d.approval_queue.length ? "Needs review" : "All clear"} icon={ClipboardCheck} tone="green" />
</section>
    <section className="space-y-3">
<React.Suspense fallback={<Skeleton className="h-[520px]" />}>
<MarketIntelligencePanel key={orgId} series={d.market_trends} />
</React.Suspense>
<TenderCard d={d} />
</section>
    <section className="grid gap-3 lg:grid-cols-3">
<Card className="rounded-xl border-slate-200">
<div className="flex items-center justify-between border-b px-4 py-3">
<h2 className="text-lg font-bold">Inventory Overview</h2>
<Link to="/inventory" className="text-xs font-bold text-blue-600">View Inventory <ArrowRight className="inline h-3.5" />
</Link>
</div>
<CardContent className="pt-3">
<div className="flex items-center gap-5">
<Ring percent={Math.min(100, Math.round(Number(inv.available) / Math.max(Number(inv.on_hand), 1) * 100))} label="Utilisation" />
<div className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs">
<p>
<i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />Eligible Stock<br />
<b className="ml-4">{fmtQty(inv.available, inv.unit)}</b>
</p>
<p>
<i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-blue-500" />Reserved<br />
<b className="ml-4">{fmtQty(inv.reserved, inv.unit)}</b>
</p>
<p>
<i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />Quality Held<br />
<b className="ml-4">{fmtQty(inv.quality_held, inv.unit)}</b>
</p>
</div>
</div>
<ResponsiveContainer width="100%" height={95}>
<BarChart data={atp}>
<XAxis dataKey="name" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
<YAxis hide />
<Tooltip />
<Bar dataKey="amount" radius={[4,4,0,0]} fill="#1d9bf0" />
</BarChart>
</ResponsiveContainer>
</CardContent>
</Card>
<Card className="rounded-xl border-slate-200">
<div className="flex items-center justify-between border-b px-4 py-3">
<div><h2 className="text-lg font-bold">Procurement Readiness</h2><p className="text-[11px] text-slate-500">Selected tender only</p></div>
<Link to="/procurement" className="text-xs font-bold text-blue-600">View Details <ArrowRight className="inline h-3.5" />
</Link>
</div>
<CardContent className="pt-4">
<div className="flex gap-6">
<Ring percent={coveragePercent} label="Coverage" color={Number(mtCoverage?.uncovered ?? 0) > 0 ? "#f59e0b" : "#22c55e"} />
<div className="space-y-4 text-xs">
<p>
<i className="mr-2 inline-block h-3 w-3 rounded-full bg-emerald-500" />Required / covered<br />
<b className="ml-5 text-sm">{mtCoverage ? `${fmtQty(mtCoverage.required, "MT")} / ${fmtQty(mtCoverage.covered, "MT")}` : `${fmtQty(boqMt, "MT")} in BOQ`}</b>
</p>
<p>
<i className="mr-2 inline-block h-3 w-3 rounded-full bg-blue-500" />Open RFQs<br />
<b className="ml-5 text-sm">{d.open_rfqs.count}</b>
</p>
<p>
<i className="mr-2 inline-block h-3 w-3 rounded-full bg-amber-500" />Uncovered<br />
<b className="ml-5 text-sm">{mtCoverage ? fmtQty(mtCoverage.uncovered, "MT") : "BOM pending"}</b>
</p>
</div>
</div>
<div className={`mt-4 rounded-lg px-3 py-3 text-xs font-semibold ${context?.status === "AWAITING_APPROVED_BOM" || Number(mtCoverage?.uncovered ?? 0) > 0 ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-800"}`}>
<CheckCircle2 className="mr-2 inline h-4 w-4" />{context?.status === "AWAITING_APPROVED_BOM" ? `${fmtQty(boqMt, "MT")} in BOQ â€” BOM pending` : readiness}</div>
</CardContent>
</Card>
<Card className="rounded-xl border-slate-200">
<div className="flex items-center justify-between border-b px-4 py-3">
<h2 className="text-lg font-bold">Costing & Profitability</h2>
<Link to="/quotations" className="text-xs font-bold text-blue-600">View Analysis <ArrowRight className="inline h-3.5" />
</Link>
</div>
<CardContent className="pt-3">
<ResponsiveContainer width="100%" height={125}>
<BarChart data={cost}>
<XAxis dataKey="name" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
<YAxis hide />
<Tooltip formatter={(v) => fmtMoney(String(Number(v) * 100000))} />
<Bar dataKey="value" radius={[4,4,0,0]} fill="#1769e0" />
</BarChart>
</ResponsiveContainer>
<div className="grid grid-cols-2 rounded-lg bg-gradient-to-r from-emerald-50 to-blue-50 p-3 text-xs">
<p>Target Margin<br />
<b className="text-lg text-emerald-700">{d.margin_exposure.at_risk_margin ? `${(Number(d.margin_exposure.at_risk_margin) * 100).toFixed(1)}%` : "Ã¢â‚¬â€"}</b>
</p>
<p>Pending Value<br />
<b className="text-lg">{fmtMoney(d.margin_exposure.total_pending_value)}</b>
</p>
</div>
</CardContent>
</Card>
</section>
    <section className="grid gap-3 xl:grid-cols-[1.45fr_1fr_.75fr]">
<Card className="rounded-xl border-blue-100 bg-blue-50/60">
<CardContent className="flex min-h-[104px] items-center gap-4 py-4">
<Sparkles className="h-7 w-7 shrink-0 text-blue-600" />
<div className="min-w-0 flex-1">
<h2 className="font-bold">AI Insights</h2>{briefing.data?.items.slice(0, 2).map((x, i) => <p className="mt-1 truncate text-xs" key={i}>Ã¢â‚¬Â¢ {x.text}</p>) || <p className="mt-1 text-xs">Market and operational signals will appear here.</p>}</div>
<Link to="/briefing">
<Button size="sm">Recommendations <ArrowRight className="h-3.5" />
</Button>
</Link>
</CardContent>
</Card>
<Card className="rounded-xl">
<CardContent className="py-3">
<div className="mb-2 flex justify-between">
<h2 className="font-bold">Recent Notifications</h2>
<Link to="/briefing" className="text-xs text-blue-600">View All Ã¢â€ â€™</Link>
</div>{d.priorities.slice(0, 3).map((x, i) => <Link key={i} to={x.link || "/briefing"} className="block truncate py-1 text-xs">
<BellRing className="mr-2 inline h-3.5 text-amber-500" />{x.text}</Link>)}</CardContent>
</Card>
<Card className={`rounded-xl ${Number(mtCoverage?.uncovered || 0) > 0 || context?.status === "AWAITING_APPROVED_BOM" ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
<CardContent className="flex h-full items-center gap-3 py-3">
<TrendingUp className="h-10 w-10 text-blue-500" />
<p className="text-sm font-bold text-slate-900">{selectedTenderName ?? "Tender not selected"}<br />{readiness}<br />
<span className="text-xs font-medium">{mtCoverage ? `${coveragePercent}% MT coverage Ã‚Â· ${fmtQty(mtCoverage.uncovered, "MT")} uncovered` : "Select a tender with an approved BOM"}</span>
</p>
</CardContent>
</Card>
</section>
  </div>;
}
