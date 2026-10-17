import * as React from "react";
import { motion } from "framer-motion";
import { Eye, EyeOff, Factory, Loader2, Lock, Mail, MoveRight } from "lucide-react";
import { ApiError } from "@/lib/api";

export interface LoginFormProps {
  onSubmit: (email: string, password: string) => Promise<void>;
}

export default function LoginForm({ onSubmit }: LoginFormProps) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPw, setShowPw] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [fieldErr, setFieldErr] = React.useState<{ email?: string; password?: string }>({});
  const [busy, setBusy] = React.useState(false);

  const validate = () => {
    const errs: typeof fieldErr = {};
    if (!email.trim()) errs.email = "Work email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) errs.email = "Enter a valid email address";
    if (!password) errs.password = "Password is required";
    setFieldErr(errs);
    return Object.keys(errs).length === 0;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!validate()) return;
    setBusy(true);
    try {
      await onSubmit(email.trim(), password);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Incorrect email or password."
          : err instanceof ApiError
            ? err.message
            : "Sign-in failed. Please try again."
      );
      setBusy(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.55, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="w-full max-w-[400px]">
      <div className="rounded-2xl border border-white/40 bg-white/[0.92] p-8 shadow-2xl shadow-slate-900/30 backdrop-blur-xl sm:p-9">
        {/* Card logo */}
        <div className="mb-7 flex flex-col items-center text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-[#2f6fde] to-[#1d56c4] shadow-md shadow-blue-900/30">
            <Factory className="h-6 w-6 text-white" />
          </div>
          <h1 className="mt-3 text-xl font-bold text-slate-900">SteelBid AI</h1>
          <p className="mt-0.5 text-xs text-slate-500">Steel Business Operating System</p>
        </div>

        <form onSubmit={submit} noValidate>
          {/* Email */}
          <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-slate-700">Work email</label>
          <div className="relative mb-1">
            <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              id="email" type="email" autoFocus autoComplete="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setFieldErr((p) => ({ ...p, email: undefined })); }}
              placeholder="you@company.com"
              aria-invalid={!!fieldErr.email} aria-describedby={fieldErr.email ? "email-err" : undefined}
              className={`h-11 w-full rounded-lg border bg-white pl-10 pr-3.5 text-sm text-slate-900 placeholder:text-slate-400
                focus:outline-none focus:ring-2 transition-colors
                ${fieldErr.email
                  ? "border-red-300 focus:border-red-400 focus:ring-red-100"
                  : "border-slate-200 focus:border-[#2f6fde] focus:ring-blue-100"}`}
            />
          </div>
          {fieldErr.email && <p id="email-err" className="mb-1 text-[11px] text-red-600" role="alert">{fieldErr.email}</p>}
          <div className="mb-4" />

          {/* Password */}
          <label htmlFor="password" className="mb-1.5 block text-xs font-medium text-slate-700">Password</label>
          <div className="relative mb-1">
            <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              id="password" type={showPw ? "text" : "password"} autoComplete="current-password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setFieldErr((p) => ({ ...p, password: undefined })); }}
              placeholder="••••••••"
              aria-invalid={!!fieldErr.password} aria-describedby={fieldErr.password ? "pw-err" : undefined}
              className={`h-11 w-full rounded-lg border bg-white pl-10 pr-11 text-sm text-slate-900 placeholder:text-slate-400
                focus:outline-none focus:ring-2 transition-colors
                ${fieldErr.password
                  ? "border-red-300 focus:border-red-400 focus:ring-red-100"
                  : "border-slate-200 focus:border-[#2f6fde] focus:ring-blue-100"}`}
            />
            <button type="button" onClick={() => setShowPw((v) => !v)}
              aria-label={showPw ? "Hide password" : "Show password"}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 hover:text-slate-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-300">
              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {fieldErr.password && <p id="pw-err" className="mb-1 text-[11px] text-red-600" role="alert">{fieldErr.password}</p>}
          <div className="mb-4" />

          {error && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs text-red-700" role="alert">
              {error}
            </div>
          )}

          <button
            type="submit" disabled={busy}
            className="group flex h-11 w-full items-center justify-center gap-2 rounded-lg
              bg-gradient-to-r from-[#2f6fde] to-[#1d56c4] text-sm font-semibold text-white
              shadow-md shadow-blue-900/25 transition-all
              hover:from-[#3579ec] hover:to-[#2261d8] hover:shadow-lg hover:shadow-blue-900/30
              focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2
              disabled:cursor-not-allowed disabled:opacity-70">
            {busy ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Signing in…</>
            ) : (
              <>Sign in <MoveRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" /></>
            )}
          </button>
        </form>

        <p className="mt-6 text-center text-[11px] leading-relaxed text-slate-400">
          Demo credentials are provided in the deployment README.
        </p>
      </div>
    </motion.div>
  );
}
