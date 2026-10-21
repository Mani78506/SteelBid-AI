import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "@/lib/api";
import type { Me, Org } from "@/lib/types";

interface AuthState {
  me: Me | null;
  orgs: Org[];
  activeOrg: Org | null;
  role: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  switchOrg: (orgId: string) => Promise<void>;
  can: (perm: string) => boolean;
}

const PERMS: Record<string, string[]> = {
  ADMIN: ["*"],
  ESTIMATOR: ["sales.read", "sales.write", "crm.read", "crm.write", "inventory.read", "materials.read", "materials.write", "tenders.read", "tenders.write", "procurement.read", "market.read", "ai.read"],
  PROCUREMENT: ["procurement.read", "procurement.write", "inventory.read", "materials.read", "suppliers.read", "suppliers.write", "market.read", "crm.read", "ai.read"],
  INVENTORY: ["inventory.read", "inventory.write", "materials.read", "materials.write", "procurement.read", "market.read"],
  FABRICATION: ["fabrication.read", "fabrication.write", "inventory.read", "materials.read", "procurement.read", "sales.read"],
  FINANCE: ["finance.read", "finance.write", "sales.read", "procurement.read", "inventory.read", "crm.read", "approvals.write"],
  VIEWER: ["dashboard.read", "materials.read", "inventory.read", "crm.read", "sales.read", "procurement.read", "market.read", "fabrication.read", "tenders.read", "finance.read", "ai.read"],
};

const AuthCtx = React.createContext<AuthState>(null as unknown as AuthState);
export const useAuth = () => React.useContext(AuthCtx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const fetchMe = React.useCallback(() => get<Me>("/v1/auth/me"), []);
  const meQ = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    retry: false,
    staleTime: 60_000,
  });
  const orgsQ = useQuery({
    queryKey: ["orgs"],
    queryFn: () => get<Org[]>("/v1/auth/organizations"),
    enabled: !!meQ.data,
    retry: false,
  });

  const me = meQ.data ?? null;
  const orgs = orgsQ.data ?? [];
  const activeOrg = me?.active_organization ?? null;
  const role = me?.role ?? null;

  const login = async (email: string, password: string) => {
    await post("/v1/auth/login", { email, password });
    await qc.invalidateQueries();
  };
  const logout = async () => {
    await post("/v1/auth/logout");
    qc.clear();
    window.location.href = "/login";
  };
  const switchOrg = async (orgId: string) => {
    await post("/v1/auth/switch-organization", { organization_id: orgId });
    // The organization is held in the session.  Clear every response that may
    // belong to the previous tenant, then fetch the new session identity before
    // the dashboard is allowed to render again.
    // Keep the observed identity query mounted. Removing it creates a new cache
    // entry without notifying the existing useQuery observer in some React Query
    // render timings, which left the org picker showing the old tenant.
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" && q.queryKey[0] !== "orgs" });
    await qc.invalidateQueries({ queryKey: ["me"] });
    await qc.refetchQueries({ queryKey: ["me"], type: "active" });
    await qc.invalidateQueries({ queryKey: ["orgs"] });
  };
  const can = (perm: string) => {
    if (!role) return false;
    const list = PERMS[role] ?? [];
    return list.includes("*") || list.includes(perm);
  };

  return (
    <AuthCtx.Provider value={{ me, orgs, activeOrg, role, loading: meQ.isLoading, login, logout, switchOrg, can }}>
      {children}
    </AuthCtx.Provider>
  );
}
