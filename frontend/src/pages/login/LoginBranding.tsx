import { motion } from "framer-motion";
import { BarChart3, ClipboardList, Factory, Factory as Logo, Warehouse } from "lucide-react";

const FEATURES = [
  { icon: BarChart3, title: "Market Intelligence", desc: "Track prices, trends and opportunities" },
  { icon: Warehouse, title: "Inventory & Procurement", desc: "Optimize stock and purchasing" },
  { icon: Factory, title: "Fabrication & Production", desc: "Plan, track and deliver efficiently" },
  { icon: ClipboardList, title: "Projects & Tenders", desc: "Estimate, bid and execute with confidence" },
];

export default function LoginBranding() {
  return (
    <div className="relative z-10 hidden lg:flex flex-col justify-between px-12 xl:px-16 py-10">
      {/* Logo */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
        className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#2f6fde] shadow-lg shadow-blue-900/40">
          <Logo className="h-6 w-6 text-white" />
        </div>
        <div>
          <p className="text-lg font-bold leading-tight text-white">SteelBid <span className="text-[#5b9dff]">AI</span></p>
          <p className="text-[11px] text-slate-400">Steel Business Operating System</p>
        </div>
      </motion.div>

      {/* Headline + features */}
      <div className="max-w-xl">
        <motion.h1
          initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.15 }}
          className="text-4xl xl:text-[42px] font-bold leading-[1.12] tracking-tight text-white">
          Smarter Decisions<br />
          for a <span className="text-white">Stronger</span><br />
          <span className="bg-gradient-to-r from-[#5b9dff] to-[#38bdf8] bg-clip-text text-transparent">Steel Business</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="mt-4 max-w-md text-sm leading-relaxed text-slate-300">
          From market insights to material procurement, fabrication to
          project delivery — all in one platform.
        </motion.p>

        <motion.ul
          initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.45 }}
          className="mt-8 space-y-4">
          {FEATURES.map((f) => (
            <li key={f.title} className="flex items-center gap-3.5">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.07] backdrop-blur-sm">
                <f.icon className="h-4 w-4 text-[#6da8ff]" />
              </div>
              <div>
                <p className="text-[13px] font-semibold text-white leading-tight">{f.title}</p>
                <p className="text-[11px] text-slate-400 leading-tight">{f.desc}</p>
              </div>
            </li>
          ))}
        </motion.ul>
      </div>

      {/* Stats strip */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.6 }}
        className="flex items-center gap-6">
        {[
          { v: "4+", l: "Business Types" },
          { v: "1", l: "Unified Platform" },
          { v: "∞", l: "Growth Opportunities" },
        ].map((s, i) => (
          <div key={s.l} className="flex items-center gap-3">
            {i > 0 && <div className="h-8 w-px bg-white/10 mr-3" />}
            <div>
              <p className="text-xl font-bold text-[#5b9dff]">{s.v}</p>
              <p className="text-[10px] text-slate-400">{s.l}</p>
            </div>
          </div>
        ))}
      </motion.div>
    </div>
  );
}
