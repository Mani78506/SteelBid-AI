import * as React from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { cn } from "@/lib/utils";
import { Skeleton, Empty } from "@/components/ui";

export function DataTable<T>({ columns, data, loading, onRowClick, emptyTitle, emptyHint, dense }: {
  columns: ColumnDef<T, unknown>[];
  data: T[] | undefined;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  emptyTitle?: string;
  emptyHint?: string;
  dense?: boolean;
}) {
  const table = useReactTable({ data: data ?? [], columns, getCoreRowModel: getCoreRowModel() });

  if (loading) {
    return (
      <div className="space-y-2 p-1">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
      </div>
    );
  }
  if (!data || data.length === 0) {
    return <Empty title={emptyTitle ?? "No records"} hint={emptyHint} />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-border bg-muted/50">
              {hg.headers.map((h) => (
                <th key={h.id} className="whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}
              onClick={onRowClick ? () => onRowClick(row.original) : undefined}
              className={cn("border-b border-border/60 last:border-0 transition-colors",
                onRowClick && "cursor-pointer hover:bg-primary-50/50")}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className={cn("whitespace-nowrap px-3 align-middle", dense ? "py-1.5 text-[13px]" : "py-2.5")}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
