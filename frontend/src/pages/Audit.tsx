import { useQuery } from "@tanstack/react-query";
import { get, type Page } from "@/lib/api";
import { Card, Badge, ErrorState } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface AuditEvent { id: string; created_at: string; user_id: string | null;
  action: string; entity_type: string; entity_id: string | null;
  diff: Record<string, unknown>; request_id: string | null }

export default function Audit() {
  const list = useQuery({ queryKey: ["audit"], queryFn: () => get<Page<AuditEvent>>("/v1/audit/events?page_size=100") });
  const cols: ColumnDef<AuditEvent, unknown>[] = [
    { accessorKey: "created_at", header: "When", cell: (c) => <span className="text-xs">{fmtDateTime(c.getValue() as string)}</span> },
    { accessorKey: "action", header: "Action", cell: (c) => <Badge value={c.getValue() as string} /> },
    { accessorKey: "entity_type", header: "Entity" },
    { accessorKey: "entity_id", header: "Entity ID", cell: (c) => <span className="font-mono text-[10px] text-muted-foreground">{(c.getValue() as string)?.slice(0, 8) ?? "—"}</span> },
    { id: "diff", header: "Change", cell: (c) => {
      const diff = c.row.original.diff ?? {};
      const keys = Object.keys(diff);
      return <span className="max-w-[280px] truncate text-xs text-muted-foreground" title={JSON.stringify(diff)}>{keys.length ? JSON.stringify(diff).slice(0, 80) : "—"}</span>; } },
    { accessorKey: "request_id", header: "Req", cell: (c) => <span className="font-mono text-[10px] text-muted-foreground">{(c.getValue() as string)?.slice(0, 8) ?? "—"}</span> },
  ];
  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div><h1 className="text-lg font-bold">Audit Log</h1>
        <p className="text-xs text-muted-foreground">{list.data?.total ?? "—"} events · append-only record of meaningful mutations</p></div>
      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : <Card><DataTable columns={cols} data={list.data?.items} loading={list.isLoading} dense emptyTitle="No audit events" /></Card>}
    </div>
  );
}
