import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Link } from "react-router";
import {
  Boxes, ShoppingCart, FileText, TrendingUp, AlertTriangle, ClipboardCheck,
  Sparkles, ArrowRight, Truck, Factory, Gavel, Quote, CalendarClock, CreditCard,
} from "lucide-react";
import { get } from "@/lib/api";
import type { DashboardSummary, Briefing } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent, Badge, Skeleton, ErrorState, Button } from "@/components/ui";
import { fmtMoney, fmtQty, fmtDate, daysUntil } from "@/lib/format";
import { useAuth } from "@/lib/auth";

const KPI_DEFS: { key: string; label: string; icon: React.ElementType; kind: "money" | "pct" | "count"; sub?: (v: Record<string, unknown>) => string | undefined }[] = [
  { key: "inventory_valuation", label: "Inventory valuation", icon: Boxes, kind: "money" },
  { key: "open_sales_order_value", label: "Open sales orders", icon: ShoppingCart, kind: "money", sub: (v) => `${v.count ?? 0} open` },
  { key: "purchase_commitments", label: "Purchase commitments", icon: CreditCard, kind: "money", sub: (v) => `${v.count ?? 0} POs` },
  { key: "pending_quotations", label: "Pending quotations", icon: Quote, kind: "count" },
  { key: "estimated_gross_margin", label: "Avg approved margin", icon: TrendingUp, kind: "pct", sub: (v) => v.basis as string },
  { key: "overdue_receivables", label: "Overdue receivables", icon: AlertTriangle, kind: "money", sub: (v) => `${v.count ?? 0} invoice(s)` },
  { key: "at_risk_orders", label: "At-risk orders", icon: CalendarClock, kind: "count" },
  { key: "pending_approvals", label: "Pending approvals", icon: ClipboardCheck, kind: "count" },
];

function KpiCard({ def, raw, index }: { def: (typeof KPI_DEFS)[number]; raw: unknown; index: number }) {
  const v = (raw ?? {}) as Record<string, unknown>;
  const display = def.kind === "money" ? fmtMoney(v.value as string, "₹")
    : def.kind === "pct" ? `${(Number(v.value ?? 0) * 100).toFixed(1)}%`
    : String(v.count ?? v.value ?? "0");
  const sub = def.sub?.(v);
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }}>
      <Card className="hover:shadow-md transition-shadow">
        <CardContent className="flex items-center gap-3 py-3.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-50 text-primary-600">
            <def.icon className="h-4.5 w-4.5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{def.label}</p>
            <p className="truncate text-lg font-bold tabular-nums">{display}</p>
            {sub && <p className="truncate text-[10px] text-muted-foreground">{sub}</p>}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

const SEVERITY_STYLE: Record<string, string> = {
  high: "border-l-red-500", medium: "border-l-amber-500", low: "border-l-primary", info: "border-l-slate-300",
};

export default function CommandCenter() {
  const { activeOrg, me } = useAuth();
  const summary = useQuery({ queryKey: ["dashboard"], queryFn: () => get<DashboardSummary>("/v1/dashboard/summary") });
  const briefing = useQuery({ queryKey: ["briefing"], queryFn: () => get<Briefing>("/v1/ai/daily-briefing") });
  const d = summary.data;
  const profiles = d?.organization.profiles ?? [];

  if (summary.error) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;

  return (
    <div className="mx-auto max-w-[1400px] space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Command Center</h1>
          <p className="text-xs text-muted-foreground">
            {d?.organization.name ?? activeOrg?.name} · {profiles.join(" + ") || "—"} · {me?.user.full_name}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/inquiries?new=1"><Button size="sm"><FileText className="h-3.5 w-3.5" /> New inquiry</Button></Link>
          <Link to="/procurement"><Button size="sm" variant="outline">Procurement</Button></Link>
        </div>
      </div>

      {/* KPI grid */}
      {summary.isLoading ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-[82px]" />)}</div>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4" role="list" aria-label="Key metrics">
          {KPI_DEFS.map((def, i) => <KpiCard key={def.key} def={def} raw={d?.kpis?.[def.key]} index={i} />)}
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        {/* Left 2/3 */}
        <div className="space-y-5 xl:col-span-2">
          {/* Priorities */}
          <Card>
            <CardHeader><CardTitle>Today's priorities</CardTitle>
              <Badge value={`${d?.priorities?.length ?? 0}`} /></CardHeader>
            <CardContent className="space-y-1.5">
              {summary.isLoading ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-11" />)
                : (d?.priorities.length ?? 0) === 0 ? <p className="py-4 text-center text-xs text-muted-foreground">All clear — no urgent items.</p>
                : d?.priorities.slice(0, 6).map((p, i) => (
                  <Link key={i} to={p.link ?? "#"}
                    className={`flex items-center gap-3 rounded-md border-l-4 bg-muted/40 px-3 py-2 transition-colors hover:bg-muted ${SEVERITY_STYLE[p.severity] ?? "border-l-primary"}`}>
                    <p className="min-w-0 flex-1 truncate text-sm font-medium">{p.text}</p>
                    <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  </Link>
                ))}
            </CardContent>
          </Card>

          {/* Recent inquiries */}
          <Card>
            <CardHeader><CardTitle>Recent sales inquiries</CardTitle>
              <Link to="/inquiries" className="text-xs font-medium text-primary hover:underline">View all</Link></CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2">Reference</th><th className="px-4 py-2">Customer</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Received</th>
                </tr></thead>
                <tbody>
                  {(d?.recent_inquiries ?? []).slice(0, 5).map((i) => (
                    <tr key={i.id} className="border-b border-border/60 last:border-0 hover:bg-muted/40">
                      <td className="px-4 py-2 font-medium text-primary"><Link to="/inquiries">{i.reference}</Link></td>
                      <td className="px-4 py-2">{i.customer}</td>
                      <td className="px-4 py-2"><Badge value={i.status} /></td>
                      <td className="px-4 py-2 text-muted-foreground">{fmtDate(i.received_at)}</td>
                    </tr>
                  ))}
                  {(d?.recent_inquiries?.length ?? 0) === 0 && !summary.isLoading &&
                    <tr><td colSpan={4} className="px-4 py-6 text-center text-xs text-muted-foreground">No inquiries yet.</td></tr>}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Shortages + Dispatches side by side */}
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Procurement shortages</CardTitle>
                <Link to="/procurement" className="text-xs font-medium text-primary hover:underline">Manage</Link></CardHeader>
              <CardContent className="space-y-1.5">
                {(d?.procurement_shortages?.length ?? 0) === 0
                  ? <p className="py-3 text-center text-xs text-muted-foreground">No open purchase requests.</p>
                  : d?.procurement_shortages.slice(0, 4).map((s) => (
                    <div key={s.pr_id} className="flex items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-sm">
                      <div className="min-w-0"><p className="truncate font-medium">{s.material}</p>
                        <p className="text-[11px] text-muted-foreground">{s.pr_number}{s.needed_by ? ` · needed ${fmtDate(s.needed_by)}` : ""}</p></div>
                      <div className="text-right"><p className="font-semibold tabular-nums">{fmtQty(s.quantity)}</p>
                        <Badge value={s.status} /></div>
                    </div>
                  ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="flex items-center gap-1.5"><Truck className="h-4 w-4" /> Upcoming dispatches</CardTitle></CardHeader>
              <CardContent className="space-y-1.5">
                {(d?.upcoming_dispatches?.length ?? 0) === 0
                  ? <p className="py-3 text-center text-xs text-muted-foreground">Nothing scheduled.</p>
                  : d?.upcoming_dispatches.slice(0, 4).map((x) => (
                    <div key={x.id} className="flex items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-sm">
                      <div className="min-w-0"><p className="truncate font-medium">{x.number}</p>
                        <p className="truncate text-[11px] text-muted-foreground">{x.transporter ?? "—"}</p></div>
                      <div className="text-right"><Badge value={x.status} />
                        <p className="mt-0.5 text-[11px] text-muted-foreground">{fmtDate(x.dispatch_date)}</p></div>
                    </div>
                  ))}
              </CardContent>
            </Card>
          </div>

          {/* Production status (fabricator) */}
          {(d?.production_status?.length ?? 0) > 0 && (
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-1.5"><Factory className="h-4 w-4" /> Production status</CardTitle>
                <Link to="/fabrication" className="text-xs font-medium text-primary hover:underline">Fabrication</Link></CardHeader>
              <CardContent className="space-y-1.5">
                {d?.production_status.map((w) => {
                  const planned = Number(w.planned_qty) || 0;
                  const produced = Number(w.produced_qty) || 0;
                  const pct = planned > 0 ? Math.min(100, (produced / planned) * 100) : 0;
                  return (
                    <div key={w.id} className="flex items-center gap-3 rounded-md bg-muted/40 px-3 py-2 text-sm">
                      <div className="min-w-0 flex-1"><p className="font-medium">{w.number}</p>
                        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                          <motion.div className="h-full rounded-full bg-accent"
                            initial={{ width: 0 }} animate={{ width: `${pct}%` }} />
                        </div>
                      </div>
                      <p className="text-xs text-muted-foreground tabular-nums">{produced}/{planned} MT</p>
                      <Badge value={w.status} />
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {/* Tender deadlines (contractor) */}
          {(d?.tender_deadlines?.length ?? 0) > 0 && (
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-1.5"><Gavel className="h-4 w-4" /> Tender deadlines</CardTitle>
                <Link to="/tenders" className="text-xs font-medium text-primary hover:underline">Tenders</Link></CardHeader>
              <CardContent className="space-y-1.5">
                {d?.tender_deadlines.map((t) => {
                  const days = daysUntil(t.deadline);
                  return (
                    <Link key={t.id} to="/tenders" className="flex items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-sm hover:bg-muted">
                      <div className="min-w-0"><p className="truncate font-medium">{t.title}</p>
                        <p className="text-[11px] text-muted-foreground">{t.number} · due {fmtDate(t.deadline)}</p></div>
                      <Badge value={days !== null && days <= 3 ? "OVERDUE" : days !== null && days <= 10 ? "PENDING_APPROVAL" : t.status} />
                    </Link>
                  );
                })}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right column: AI briefing + market + activity */}
        <div className="space-y-5">
          <Card className="border-accent/30">
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5"><Sparkles className="h-4 w-4 text-accent" /> AI Daily Briefing</CardTitle>
              <Link to="/briefing" className="text-xs font-medium text-primary hover:underline">Full briefing</Link>
            </CardHeader>
            <CardContent className="space-y-2">
              {briefing.isLoading ? <><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-4/5" /><Skeleton className="h-4 w-3/5" /></>
                : (briefing.data?.items ?? []).slice(0, 5).map((a, i) => (
                  <Link key={i} to={a.link ?? "#"}
                    className="block rounded-md bg-teal-50 px-2.5 py-1.5 text-xs leading-snug text-teal-900 hover:bg-teal-100">
                    {a.text}</Link>
                ))}
              {briefing.data?.summary && <p className="pt-1 text-[10px] text-muted-foreground">{briefing.data.summary}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Steel price observations</CardTitle>
              <Link to="/market" className="text-xs font-medium text-primary hover:underline">Market</Link></CardHeader>
            <CardContent className="space-y-1.5">
              {(d?.price_observations?.length ?? 0) === 0
                ? <p className="py-3 text-center text-xs text-muted-foreground">No recent observations.</p>
                : d?.price_observations.slice(0, 5).map((o, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <div className="min-w-0"><p className="truncate font-medium">{o.form}{o.grade ? ` ${o.grade}` : ""}</p>
                      <p className="text-[10px] text-muted-foreground">{o.region} · {fmtDate(o.observed_on)}{o.is_synthetic ? " · synthetic" : ""}</p></div>
                    <p className="font-semibold tabular-nums">{fmtMoney(o.price)}/{o.unit}</p>
                  </div>
                ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Recent activity</CardTitle>
              <Link to="/audit" className="text-xs font-medium text-primary hover:underline">Audit log</Link></CardHeader>
            <CardContent>
              <ul className="space-y-2.5">
                {(d?.recent_activity ?? []).slice(0, 6).map((e) => (
                  <li key={e.id} className="flex gap-2.5 text-xs">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    <div className="min-w-0">
                      <p className="truncate text-foreground">{e.action.replace(/_/g, " ").toLowerCase()}</p>
                      <p className="text-[10px] text-muted-foreground">{e.entity_type} · {fmtDate(e.created_at)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
