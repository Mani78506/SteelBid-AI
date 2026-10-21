import { useQuery } from "@tanstack/react-query";
import MarketIntelligencePanel from "@/components/dashboard/MarketIntelligencePanel";
import { ErrorState, Skeleton } from "@/components/ui";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EnhancedDashboardSummary } from "@/lib/types";

/**
 * The workspace deliberately reuses the Command Center panel.  Keeping one
 * component prevents the old table/chart view from drifting visually or
 * showing a different market experience from the main dashboard.
 */
export default function Market() {
  const { activeOrg } = useAuth();
  const overview = useQuery({
    queryKey: ["dashboard", "enhanced", activeOrg?.id, 30],
    enabled: !!activeOrg?.id,
    queryFn: () => get<EnhancedDashboardSummary>("/v1/dashboard/enhanced?days=30"),
    staleTime: 60_000,
  });

  if (overview.error) return <ErrorState error={overview.error} onRetry={() => overview.refetch()} />;
  if (!overview.data) return <Skeleton className="h-[520px]" />;

  return (
    <div className="mx-auto max-w-[1450px] pb-4">
      <MarketIntelligencePanel key={activeOrg?.id} series={overview.data.market_trends} />
    </div>
  );
}
