import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Globe2 } from "lucide-react";
import { get } from "@/lib/api";
import { Card, CardContent, Select, Skeleton } from "@/components/ui";

type Point = { price_value: string; currency: string; original_unit: string; observed_on: string; publication_date?: string | null; source: string; source_url: string };
type Listing = { classification: string; attribution: string; items: Array<Point & { commodity_name: string; checksum: string }> };

export default function GlobalCommodityBenchmarks() {
  const [commodity, setCommodity] = React.useState("");
  const [months, setMonths] = React.useState(60);
  const list = useQuery({ queryKey: ["global-benchmarks"], queryFn: () => get<Listing>("/v1/market/benchmarks") });
  React.useEffect(() => { if (!commodity && list.data?.items[0]) setCommodity(list.data.items[0].commodity_name); }, [commodity, list.data]);
  const history = useQuery({ enabled: !!commodity, queryKey: ["global-benchmark-history", commodity, months], queryFn: () => get<{ points: Point[] }>(`/v1/market/benchmarks/history?commodity_name=${encodeURIComponent(commodity)}&months=${months}`) });
  if (list.isLoading) return <Skeleton className="h-[310px]" />;
  if (!list.data?.items.length) return null;
  const current = list.data.items.find((x) => x.commodity_name === commodity) ?? list.data.items[0];
  const chart = (history.data?.points ?? []).map((point) => ({ ...point, value: Number(point.price_value), month: point.observed_on.slice(0, 7) }));
  return <Card className="border-sky-200 bg-gradient-to-br from-sky-50 to-white"><CardContent className="space-y-4 p-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2 text-sm font-semibold text-sky-800"><Globe2 className="h-4 w-4" />Global Commodity Benchmarks</div><p className="mt-1 text-xs text-slate-600">Real World Bank monthly benchmarks — not Indian steel prices and not a live feed.</p></div><div className="flex items-center gap-2"><div className="flex rounded-md border bg-white p-0.5">{[12,36,60].map(value => <button key={value} type="button" onClick={() => setMonths(value)} className={`rounded px-2 py-1 text-xs font-semibold ${months === value ? "bg-sky-700 text-white" : "text-slate-600"}`}>{value}M</button>)}</div><Select value={commodity} onChange={(e) => setCommodity(e.target.value)} className="w-56">{list.data.items.map((item) => <option key={item.commodity_name}>{item.commodity_name}</option>)}</Select></div></div>
    <div className="grid gap-3 sm:grid-cols-3"><div><p className="text-xs text-slate-500">Latest benchmark</p><p className="text-xl font-bold text-slate-900">{current.currency} {Number(current.price_value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</p><p className="text-xs text-slate-500">{current.original_unit} · {current.observed_on}</p></div><div><p className="text-xs text-slate-500">Publication</p><p className="text-sm font-semibold text-slate-800">{current.publication_date?.slice(0, 10) ?? "Not supplied"}</p><p className="text-xs text-slate-500">Monthly observation</p></div><div><p className="text-xs text-slate-500">Source</p><a className="text-sm font-semibold text-sky-700 underline" href={current.source_url} target="_blank" rel="noreferrer">{current.source}</a><p className="text-xs text-slate-500">CC BY 4.0 · attribution required</p></div></div>
    <div className="h-48"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chart}><defs><linearGradient id="benchmarkFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#0284c7" stopOpacity={.3}/><stop offset="100%" stopColor="#0284c7" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} strokeDasharray="3 3"/><XAxis dataKey="month" tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 11 }} width={62}/><Tooltip formatter={(value) => [`${current.currency} ${Number(value).toLocaleString()} ${current.original_unit}`, "Benchmark"]}/><Area type="monotone" dataKey="value" stroke="#0284c7" fill="url(#benchmarkFill)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div>
    <p className="text-[11px] text-slate-500">{list.data.attribution} Original unit and currency are preserved. These benchmarks never appear in Indian steel-price cards or price analytics.</p>
  </CardContent></Card>;
}
