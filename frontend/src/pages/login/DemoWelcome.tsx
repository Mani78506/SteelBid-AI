import { motion } from "framer-motion";
import { ArrowRight, BarChart3, ClipboardCheck, Loader2, PackageCheck, ShieldCheck } from "lucide-react";

export interface DemoWelcomeProps {
  onExplore: () => Promise<void>;
  onSignIn: () => void;
  busy?: boolean;
  error?: string | null;
}

const STEPS = [
  ["01", "Upload & extract", "Turn tender documents into reviewable BOQ requirements."],
  ["02", "Match & source", "Compare eligible stock and compatible supplier offers."],
  ["03", "Approve & submit", "Trace costing, quotation revisions and tender outcomes."],
] as const;

export default function DemoWelcome({ onExplore, onSignIn, busy, error }: DemoWelcomeProps) {
  return (
    <motion.main initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }} className="w-full max-w-[510px]">
      <section className="rounded-2xl border border-white/35 bg-white/[0.94] p-6 shadow-2xl shadow-slate-900/30 backdrop-blur-xl sm:p-8">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-blue-700"><BarChart3 className="h-4 w-4" /> SteelBid AI demonstration</div>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-slate-950 sm:text-[28px]">See the steel workflow, end to end.</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">Explore a read-only fictional workspace built to demonstrate traceable tender, inventory, procurement and commercial decisions.</p>

        <div className="mt-5 grid gap-2 sm:grid-cols-3">
          {STEPS.map(([number, title, text]) => <div key={number} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <p className="text-[10px] font-bold tracking-wider text-blue-700">{number}</p>
            <p className="mt-1 text-xs font-bold text-slate-900">{title}</p>
            <p className="mt-1 text-[11px] leading-4 text-slate-500">{text}</p>
          </div>)}
        </div>

        <div className="mt-5 rounded-xl border border-blue-100 bg-blue-50 px-3.5 py-3 text-xs text-blue-950">
          <div className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-blue-700" /><p><b>Read-only demonstration.</b> All records are fictional or labelled simulated. Creating, approving, submitting and changing business data remains unavailable to demo visitors.</p></div>
        </div>
        {error && <p role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
        <button type="button" onClick={() => void onExplore()} disabled={busy} className="mt-5 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-[#2f6fde] to-[#1d56c4] text-sm font-semibold text-white shadow-md shadow-blue-900/25 transition hover:from-[#3579ec] hover:to-[#2261d8] disabled:cursor-not-allowed disabled:opacity-70">
          {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> Opening demo…</> : <>Explore the demo <ArrowRight className="h-4 w-4" /></>}
        </button>
        <div className="mt-5 flex items-center justify-center gap-2 text-xs text-slate-500"><PackageCheck className="h-3.5 w-3.5 text-slate-400" /> Have workspace credentials? <button type="button" onClick={onSignIn} className="font-semibold text-blue-700 hover:text-blue-900">Sign in</button></div>
      </section>
    </motion.main>
  );
}
