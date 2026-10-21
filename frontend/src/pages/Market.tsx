import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Plus, FlaskConical } from "lucide-react";
import { get, post, type Page } from "@/lib/api";
import type { PriceObservation } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select, Label, Badge, Modal, ErrorState, Skeleton } from "@/components/ui";
import { DataTable } from "@/components/DataTable";
import { useToast } from "@/components/Toast";
import { fmtMoney, fmtDate } from "@/lib/format";
import type { ColumnDef } from "@tanstack/react-table";

interface TrendPoint { observed_on: string; price_per_unit: string; is_synthetic: boolean }
interface Trend { points: TrendPoint[]; latest: string | null; change_pct_30d: string | null; change_pct_90d: string | null; freshness_days: number | null; data_is_synthetic: boolean }
interface Freshness { warnings: { material_form: string; grade: string; region: string; latest_observation: string; age_days: number; warning: string }[] }
interface ScenarioRes { results?: Record<string, string | boolean>; name: string }

const FORMS = ["BEAM", "CHANNEL", "ANGLE", "PLATE", "SHEET", "COIL", "BAR", "PIPE", "TMT", "FASTENER", "HRC", "CRC", "BILLET", "SCRAP"];
const GRADES = ["E250", "E350", "E410", "E450", "Fe500", "Fe550", "IS2062", "SS304", "Fe415", "Fe500D"];
const PRICE_BASIS = ["EX_WORKS", "DELIVERED", "FORWARD"];

export default function Market() {
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = React.useState("BEAM");
  const [grade, setGrade] = React.useState("E250");
  const [region, setRegion] = React.useState("West India");
  const [priceBasis, setPriceBasis] = React.useState("EX_WORKS");
  const [obsOpen, setObsOpen] = React.useState(false);
  const [scenOpen, setScenOpen] = React.useState(false);
  const [importOpen, setImportOpen] = React.useState(false);
  const [price, setPrice] = React.useState("");
  const [obsDate, setObsDate] = React.useState(new Date().toISOString().slice(0, 10));
  const [scName, setScName] = React.useState("Scenario");
  const [qty, setQty] = React.useState("100");
  const [pct, setPct] = React.useState("0.05");
  const [scenario, setScenario] = React.useState<ScenarioRes | null>(null);
  const [importFile, setImportFile] = React.useState<File | null>(null);

  const freshness = useQuery({ queryKey: ["market-freshness"], queryFn: () => get<Freshness>("/v1/market/freshness-warnings") });
  const obs = useQuery({
    queryKey: ["observations", form, grade, region, priceBasis],
    queryFn: () => get<Page<PriceObservation>>(`/v1/market/observations?form=${form}&grade=${grade}&region=${encodeURIComponent(region)}&price_basis=${priceBasis}`),
  });
  const trend = useQuery({
    queryKey: ["trend", form, grade, region],
    queryFn: () => get<Trend>(`/v1/market/trends?form=${form}&grade=${grade}&region=${encodeURIComponent(region)}`),
  });

  const obsMut = useMutation({
    mutationFn: () => post("/v1/market/observations", {
      material_form: form, grade, region, price_basis: priceBasis, price_per_unit: price, unit: "MT", observed_on: obsDate,
    }),
    onSuccess: () => {
      toast.push("success", "Observation recorded");
      setObsOpen(false);
      ["observations", "trend", "market-freshness", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Failed"),
  });
  const importMut = useMutation({
    mutationFn: () => {
      if (!importFile) return Promise.reject("No file selected");
      const formData = new FormData();
      formData.append("file", importFile);
      return fetch("/api/v1/market/observations/import", {
        method: "POST",
        credentials: "include",
        body: formData,
      }).then((r) => r.json());
    },
    onSuccess: (res) => {
      toast.push("success", `Imported ${res.imported} observations${res.errors.length > 0 ? ` (${res.errors.length} errors)` : ""}`);
      setImportOpen(false);
      setImportFile(null);
      ["observations", "trend", "market-freshness", "dashboard"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Import failed"),
  });
  const scenMut = useMutation({
    mutationFn: () => post("/v1/market/scenarios", {
      name: scName, material_form: form, grade, region,
      planned_qty: qty, unit: "MT", price_delta_pct: pct,
    }),
    onSuccess: (r) => setScenario(r as ScenarioRes),
    onError: (e) => toast.push("error", e instanceof Error ? e.message : "Scenario failed"),
  });

  const chartData = (trend.data?.points ?? []).map((p) => ({ date: fmtDate(p.observed_on), price: Number(p.price_per_unit) }));
  const res = scenario?.results as Record<string, string | boolean> | undefined;

  const cols: ColumnDef<PriceObservation, unknown>[] = [
    { accessorKey: "observed_on", header: "Date", cell: (c) => fmtDate(c.getValue() as string) },
    { accessorKey: "material_form", header: "Form" },
    { accessorKey: "grade", header: "Grade" },
    { accessorKey: "region", header: "Region" },
    { accessorKey: "price_basis", header: "Basis", cell: (c) => <span className="text-xs">{c.getValue() as string}</span> },
    { id: "price", header: "Price", cell: (c) => <span className="font-semibold tabular-nums">{fmtMoney(c.row.original.price_per_unit)}/{c.row.original.unit}</span> },
    { accessorKey: "source_name", header: "Source", cell: (c) => <span className="text-xs">{c.getValue() as string ?? "—"}</span> },
    { id: "synthetic", header: "Label", cell: (c) => <Badge value={c.row.original.is_synthetic ? "UNCONFIRMED" : "VERIFIED"} /> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">Steel Market Intelligence</h1>
          <p className="text-xs text-muted-foreground">
            {freshness.data?.warnings.length
              ? <span className="text-amber-700">{freshness.data.warnings.length} stale series — treat as indicative only.</span>
              : "All tracked series are fresh."}
            {trend.data?.data_is_synthetic && <span className="ml-2 italic">Synthetic demo observations — not live market data.</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setScenOpen(true)}><FlaskConical className="h-3.5 w-3.5" /> Scenario</Button>
          <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}><Plus className="h-3.5 w-3.5" /> Import CSV</Button>
          <Button size="sm" onClick={() => setObsOpen(true)}><Plus className="h-3.5 w-3.5" /> Record observation</Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="w-40"><Select value={form} onChange={(e) => setForm(e.target.value)}>{FORMS.map((f) => <option key={f}>{f}</option>)}</Select></div>
        <div className="w-40"><Select value={grade} onChange={(e) => setGrade(e.target.value)}>{GRADES.map((g) => <option key={g}>{g}</option>)}</Select></div>
        <div className="w-40"><Select value={priceBasis} onChange={(e) => setPriceBasis(e.target.value)}>{PRICE_BASIS.map((b) => <option key={b}>{b}</option>)}</Select></div>
        <div className="w-48"><Input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="Region" /></div>
        {trend.data?.latest && (
          <div className="flex items-center gap-3 text-sm">
            <span>Latest <b className="tabular-nums">{fmtMoney(trend.data.latest)}/MT</b></span>
            {trend.data.change_pct_30d && <Badge value={(Number(trend.data.change_pct_30d) >= 0 ? "+" : "") + (Number(trend.data.change_pct_30d) * 100).toFixed(1) + "% 30d"} />}
            {trend.data.freshness_days !== null && <span className="text-xs text-muted-foreground">{trend.data.freshness_days}d old</span>}
          </div>
        )}
      </div>

      <Card>
        <CardHeader><CardTitle>Price trend — {form} {grade}, {region}</CardTitle>
          {chartData.length > 0 && <Badge value={`${chartData.length} points`} />}</CardHeader>
        <CardContent>
          {trend.isLoading ? <Skeleton className="h-56 w-full" />
            : chartData.length === 0 ? <p className="py-10 text-center text-xs text-muted-foreground">No observations for this series.</p>
            : (
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={["dataMin - 500", "dataMax + 500"]} tickFormatter={(v) => `₹${(v / 1000).toFixed(1)}k`} />
                  <Tooltip formatter={(v) => [`₹${Number(v).toLocaleString("en-IN")}`, "₹/MT"]} />
                  <Line type="monotone" dataKey="price" stroke="#1d5e96" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
        </CardContent>
      </Card>

      {res && (
        <Card className="border-accent/40">
          <CardHeader><CardTitle>Scenario: {scenario?.name}</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-6 text-sm">
            <span>Base <b className="tabular-nums">{fmtMoney(res.base_price as string)}</b></span>
            <span>Scenario <b className="tabular-nums text-primary">{fmtMoney(res.scenario_price as string)}</b></span>
            <span>Baseline exposure <b className="tabular-nums">{fmtMoney(res.baseline_exposure as string)}</b></span>
            <span>Scenario exposure <b className="tabular-nums">{fmtMoney(res.scenario_exposure as string)}</b></span>
            <span>Δ <b className={`tabular-nums ${Number(res.exposure_delta) > 0 ? "text-red-600" : "text-emerald-600"}`}>{fmtMoney(res.exposure_delta as string)}</b></span>
          </CardContent>
          <p className="px-4 pb-3 text-[11px] text-muted-foreground">{res.disclaimer as string}</p>
        </Card>
      )}

      {(freshness.data?.warnings?.length ?? 0) > 0 && (
        <Card className="border-amber-300">
          <CardHeader><CardTitle>Freshness warnings</CardTitle></CardHeader>
          <CardContent className="space-y-1">
            {freshness.data!.warnings.map((w, i) => (
              <p key={i} className="rounded bg-amber-50 px-3 py-1.5 text-xs text-amber-800">
                {w.material_form} {w.grade} · {w.region} — last seen {w.latest_observation} ({w.age_days}d ago). {w.warning}
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      {obs.error ? <ErrorState error={obs.error} onRetry={() => obs.refetch()} />
        : <Card><DataTable columns={cols} data={obs.data?.items} loading={obs.isLoading} dense emptyTitle="No price observations for this series" /></Card>}

      <Modal open={obsOpen} onClose={() => setObsOpen(false)} title="Record price observation">
        <div className="space-y-3">
          <p className="rounded bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-800">
            Manual observations are attributed to your team and labelled non-synthetic only if entered by a human.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Form</Label><Select value={form} onChange={(e) => setForm(e.target.value)}>{FORMS.map((f) => <option key={f}>{f}</option>)}</Select></div>
            <div><Label>Grade</Label><Select value={grade} onChange={(e) => setGrade(e.target.value)}>{GRADES.map((g) => <option key={g}>{g}</option>)}</Select></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Price basis</Label><Select value={priceBasis} onChange={(e) => setPriceBasis(e.target.value)}>{PRICE_BASIS.map((b) => <option key={b}>{b}</option>)}</Select></div>
            <div><Label>Region</Label><Input value={region} onChange={(e) => setRegion(e.target.value)} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Observed on</Label><Input type="date" value={obsDate} onChange={(e) => setObsDate(e.target.value)} /></div>
            <div><Label>Size/spec (optional)</Label><Input placeholder="e.g. 200x100mm" /></div>
          </div>
          <div><Label>Price ₹/MT</Label><Input value={price} onChange={(e) => setPrice(e.target.value)} placeholder="56800" /></div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setObsOpen(false)}>Cancel</Button>
            <Button loading={obsMut.isPending} disabled={!price} onClick={() => obsMut.mutate()}>Record</Button>
          </div>
        </div>
      </Modal>

      <Modal open={importOpen} onClose={() => setImportOpen(false)} title="Import price observations from CSV">
        <div className="space-y-3">
          <p className="rounded bg-blue-50 px-2.5 py-1.5 text-[11px] text-blue-800">
            Upload a CSV file with columns: material_form, grade, region, dimension_note (optional), price_basis, price_per_unit, unit, currency, observed_on
          </p>
          <div>
            <Label>CSV file</Label>
            <Input type="file" accept=".csv" onChange={(e) => setImportFile(e.target.files?.[0] ?? null)} />
          </div>
          {importFile && <p className="text-xs text-muted-foreground">Selected: {importFile.name}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setImportOpen(false)}>Cancel</Button>
            <Button loading={importMut.isPending} disabled={!importFile} onClick={() => importMut.mutate()}>Import</Button>
          </div>
        </div>
      </Modal>

      <Modal open={scenOpen} onClose={() => { setScenOpen(false); setScenario(null); }} title={`Price scenario — ${form} ${grade}`}>
        <div className="space-y-3">
          <div><Label>Scenario name</Label><Input value={scName} onChange={(e) => setScName(e.target.value)} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Planned quantity (MT)</Label><Input value={qty} onChange={(e) => setQty(e.target.value)} /></div>
            <div><Label>Price delta % (e.g. 0.05 = +5%)</Label><Input value={pct} onChange={(e) => setPct(e.target.value)} /></div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setScenOpen(false)}>Cancel</Button>
            <Button loading={scenMut.isPending} onClick={() => scenMut.mutate()}>Run scenario</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
