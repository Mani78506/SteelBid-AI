import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { AlertTriangle, CheckCircle2, Database, Info, Sparkles } from "lucide-react";
import { get } from "@/lib/api";
import type { Briefing } from "@/lib/types";
import { Card, CardContent, CompactChartCard, ErrorState, MetricCard, Skeleton } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";

const appearance: Record<string, { tone: string; icon: typeof AlertTriangle; label: string }> = {
  high: { tone: "border-red-200 bg-red-50 text-red-900", icon: AlertTriangle, label: "High priority" },
  medium: { tone: "border-amber-200 bg-amber-50 text-amber-900", icon: AlertTriangle, label: "Needs review" },
  low: { tone: "border-teal-200 bg-teal-50 text-teal-900", icon: CheckCircle2, label: "Opportunity" },
  info: { tone: "border-slate-200 bg-slate-50 text-slate-800", icon: Info, label: "Information" },
};

export default function BriefingPage() {
  const query = useQuery({ queryKey: ["briefing"], queryFn: () => get<Briefing>("/v1/ai/daily-briefing") });
  const items = query.data?.items ?? []; const high = items.filter((item) => item.severity === "high").length; const referenced = query.data?.grounded_in.length ?? 0;
  return <div className="mx-auto max-w-[1400px] space-y-5"><header><p className="text-xs font-medium uppercase tracking-[0.14em] text-primary">Decision support</p><h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight"><Sparkles className="h-5 w-5 text-accent" />AI Briefing</h1><p className="mt-1 text-sm text-muted-foreground">Generated {query.data ? fmtDateTime(query.data.generated_at) : "…"}. Every item is grounded in existing records.</p></header>{query.error ? <ErrorState error={query.error} onRetry={() => query.refetch()} /> : query.isLoading ? <div className="grid gap-3 md:grid-cols-3">{Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-28" />)}</div> : <><section className="grid gap-3 md:grid-cols-3"><MetricCard label="Briefing items" value={items.length} hint="Current actionable signals" icon={<Sparkles className="h-5 w-5" />} /><MetricCard label="High priority" value={high} hint="Items requiring attention" icon={<AlertTriangle className="h-5 w-5" />} /><MetricCard label="Source records" value={referenced} hint="Referenced stored records" icon={<Database className="h-5 w-5" />} /></section><Card className="border-primary-100 bg-primary-50/30"><CardContent className="py-4 text-sm font-medium">{query.data?.summary}</CardContent></Card><section className="grid gap-4 xl:grid-cols-[1.6fr_.9fr]"><CompactChartCard title="Priority workspace" subtitle="Evidence-backed actions, ordered by severity"><div className="space-y-2">{items.length ? items.map((item, index) => { const style = appearance[item.severity] ?? appearance.info; const Icon = style.icon; return <Link key={index} to={item.link ?? "#"} className={`flex items-start gap-3 rounded-lg border p-3 transition-shadow hover:shadow-sm ${style.tone}`}><Icon className="mt-0.5 h-4 w-4 shrink-0" /><div><p className="text-[10px] font-semibold uppercase tracking-wide opacity-70">{style.label}</p><p className="mt-0.5 text-sm font-medium">{item.text}</p></div></Link>; }) : <p className="py-12 text-center text-sm text-muted-foreground">No evidence-backed briefing items are available.</p>}</div></CompactChartCard><CompactChartCard title="Evidence coverage" subtitle="No fabricated confidence score"><div className="flex h-[220px] flex-col justify-center"><p className="text-4xl font-semibold tabular-nums">{referenced}</p><p className="mt-1 text-sm text-muted-foreground">stored records referenced</p><div className="mt-5 space-y-2">{[...new Set(query.data?.grounded_in.map((record) => record.entity) ?? [])].map((entity) => <div key={entity} className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm font-medium">{entity}</div>)}</div></div></CompactChartCard></section></>}</div>;
}
