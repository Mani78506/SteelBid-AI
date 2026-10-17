import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Sparkles, Database } from "lucide-react";
import { get } from "@/lib/api";
import type { Briefing } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent, ErrorState, Skeleton } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";

const SEVERITY: Record<string, string> = {
  high: "bg-red-50 text-red-900 border-red-200",
  medium: "bg-amber-50 text-amber-900 border-amber-200",
  low: "bg-teal-50 text-teal-900 border-teal-200",
  info: "bg-slate-50 text-slate-800 border-slate-200",
};

export default function BriefingPage() {
  const q = useQuery({ queryKey: ["briefing"], queryFn: () => get<Briefing>("/v1/ai/daily-briefing") });
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold"><Sparkles className="h-5 w-5 text-accent" /> AI Daily Briefing</h1>
        <p className="text-xs text-muted-foreground">
          Generated {q.data ? fmtDateTime(q.data.generated_at) : "…"} · {q.data?.note}
        </p>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? (
        <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : (
        <>
          <Card className="border-accent/40 bg-teal-50/30">
            <CardContent className="py-3 text-sm font-medium">{q.data?.summary}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Items requiring attention</CardTitle></CardHeader>
            <CardContent className="space-y-1.5">
              {q.data?.items.map((it, i) => (
                <Link key={i} to={it.link ?? "#"}
                  className={`block rounded-md border px-3 py-2 text-sm transition-shadow hover:shadow-sm ${SEVERITY[it.severity] ?? SEVERITY.info}`}>
                  {it.text}
                </Link>
              ))}
            </CardContent>
          </Card>
          {(q.data?.grounded_in?.length ?? 0) > 0 && (
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-1.5"><Database className="h-4 w-4" /> Grounded in records</CardTitle></CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  This briefing references {q.data?.grounded_in.length} stored record(s):{" "}
                  {[...new Set(q.data!.grounded_in.map((g) => g.entity))].join(", ")}.
                  No figures are invented — every item links to a database row.
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
