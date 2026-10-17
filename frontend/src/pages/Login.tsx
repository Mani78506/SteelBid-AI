import * as React from "react";
import { useNavigate } from "react-router";
import { motion } from "framer-motion";
import { Factory } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Button, Input, Label } from "@/components/ui";
import { ApiError } from "@/lib/api";

export default function Login() {
  const { login, me } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => { if (me) navigate("/", { replace: true }); }, [me, navigate]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await login(email, password); navigate("/", { replace: true }); }
    catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed");
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
        className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-white shadow-md">
            <Factory className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">SteelBid AI</h1>
            <p className="text-xs text-slate-500">Steel Business Operating System</p>
          </div>
        </div>
        <form onSubmit={submit} className="rounded-xl border border-border bg-card p-6 shadow-card">
          <Label htmlFor="email">Work email</Label>
          <Input id="email" type="email" required autoFocus autoComplete="email"
            value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="mb-4" />
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" required autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="mb-5" />
          {error && <p className="mb-4 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700" role="alert">{error}</p>}
          <Button type="submit" className="w-full" loading={busy}>Sign in</Button>
          <p className="mt-4 text-center text-[11px] text-muted-foreground">
            Demo credentials are provided in the deployment README.
          </p>
        </form>
      </motion.div>
    </div>
  );
}
