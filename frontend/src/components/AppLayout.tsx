import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, Users2, Package, Warehouse, Factory, Handshake, ShoppingCart,
  FileText, TrendingUp, FolderKanban, Truck, IndianRupee, Sparkles, ScrollText,
  Search, Bell, ChevronDown, LogOut, Menu, X, Building2, ClipboardList,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { Input } from "@/components/ui";
import { get, post } from "@/lib/api";

interface NavItem { to: string; label: string; icon: React.ElementType; profiles?: string[] }
interface NavGroup { title: string; items: NavItem[] }

const NAV: NavGroup[] = [
  {
    title: "Overview",
    items: [
      { to: "/", label: "Command Center", icon: LayoutDashboard },
      { to: "/briefing", label: "AI Briefing", icon: Sparkles },
    ],
  },
  {
    title: "Sales",
    items: [
      { to: "/customers", label: "Customers", icon: Users2 },
      { to: "/inquiries", label: "Inquiries", icon: ClipboardList },
      { to: "/quotations", label: "Quotations", icon: FileText },
      { to: "/sales-orders", label: "Sales Orders", icon: ShoppingCart },
    ],
  },
  {
    title: "Materials & Stock",
    items: [
      { to: "/materials", label: "Materials", icon: Package },
      { to: "/inventory", label: "Inventory", icon: Warehouse },
    ],
  },
  {
    title: "Procurement",
    items: [
      { to: "/suppliers", label: "Suppliers", icon: Handshake },
      { to: "/procurement", label: "Purchase Requests", icon: ShoppingCart },
      { to: "/market", label: "Market Prices", icon: TrendingUp },
    ],
  },
  {
    title: "Operations",
    items: [
      { to: "/fabrication", label: "Fabrication", icon: Factory, profiles: ["FABRICATOR"] },
      { to: "/projects", label: "Projects", icon: FolderKanban, profiles: ["CONTRACTOR", "FABRICATOR"] },
      { to: "/tenders", label: "Tenders & BOQ", icon: FileText, profiles: ["CONTRACTOR", "FABRICATOR"] },
      { to: "/logistics", label: "Logistics", icon: Truck },
    ],
  },
  {
    title: "Finance & Admin",
    items: [
      { to: "/finance", label: "Finance", icon: IndianRupee },
      { to: "/audit", label: "Audit Log", icon: ScrollText },
    ],
  },
];

function NavSection({ group, profiles, onNavigate }: { group: NavGroup; profiles: string[]; onNavigate?: () => void }) {
  const items = group.items.filter((i) => !i.profiles || i.profiles.some((p) => profiles.includes(p)));
  if (items.length === 0) return null;
  return (
    <div>
      <p className="px-3 pb-1.5 pt-4 text-[10px] font-semibold uppercase tracking-widest text-sidebar-muted">{group.title}</p>
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} end={item.to === "/"} onClick={onNavigate}
              className={({ isActive }) => cn(
                "group flex items-center gap-2.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors",
                isActive ? "bg-sidebar-hover text-white" : "text-sidebar-muted hover:bg-sidebar-hover/60 hover:text-slate-200")}>
              <item.icon className="h-4 w-4 shrink-0 opacity-80" />
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AppLayout() {
  const { me, orgs, activeOrg, role, switchOrg, logout } = useAuth();
  const [orgMenu, setOrgMenu] = React.useState(false);
  const [userMenu, setUserMenu] = React.useState(false);
  const [mobileNav, setMobileNav] = React.useState(false);
  const [notificationMenu, setNotificationMenu] = React.useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const [search, setSearch] = React.useState("");
  const profiles = activeOrg?.business_profiles ?? [];
  const crumbs = location.pathname.split("/").filter(Boolean);
  const notifications = useQuery({ queryKey: ["notifications", activeOrg?.id], enabled: !!activeOrg?.id,
    queryFn: () => get<{ unread_count:number; items:{id:string;title:string;body?:string;link?:string;is_read:boolean;created_at:string}[] }>("/v1/notifications") });

  React.useEffect(() => { setOrgMenu(false); setUserMenu(false); }, [location.pathname]);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar — desktop */}
      <motion.aside initial={{ x: -8, opacity: 0 }} animate={{ x: 0, opacity: 1 }}
        className="hidden w-60 shrink-0 flex-col bg-sidebar text-slate-300 lg:flex">
        <div className="flex h-14 items-center gap-2.5 border-b border-sidebar-border px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-white">
            <Factory className="h-4.5 w-4.5" />
          </div>
          <div>
            <p className="text-sm font-bold leading-tight text-white">SteelBid AI</p>
            <p className="text-[10px] text-sidebar-muted">Steel Business OS</p>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 pb-4" aria-label="Primary">
          {NAV.map((g) => <NavSection key={g.title} group={g} profiles={profiles} />)}
        </nav>
        <div className="border-t border-sidebar-border px-4 py-3">
          <p className="truncate text-xs font-medium text-slate-200">{activeOrg?.name}</p>
          <p className="text-[10px] text-sidebar-muted">{role} · {profiles.join(" + ") || "—"}</p>
        </div>
      </motion.aside>

      {/* Mobile nav drawer */}
      <AnimatePresence>
        {mobileNav && (
          <motion.div className="fixed inset-0 z-40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileNav(false)} />
            <motion.aside initial={{ x: -260 }} animate={{ x: 0 }} exit={{ x: -260 }}
              transition={{ type: "tween", duration: 0.2 }}
              className="absolute left-0 top-0 h-full w-64 overflow-y-auto bg-sidebar pb-6 text-slate-300">
              <div className="flex h-14 items-center justify-between border-b border-sidebar-border px-4">
                <p className="text-sm font-bold text-white">SteelBid AI</p>
                <button onClick={() => setMobileNav(false)} aria-label="Close menu"><X className="h-5 w-5" /></button>
              </div>
              <nav className="px-2">{NAV.map((g) => <NavSection key={g.title} group={g} profiles={profiles} onNavigate={() => setMobileNav(false)} />)}</nav>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
          <button className="lg:hidden" onClick={() => setMobileNav(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>

          {/* Org switcher */}
          <div className="relative">
            <button onClick={() => { setOrgMenu((v) => !v); setUserMenu(false); }}
              className="flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-sm hover:bg-muted"
              aria-haspopup="listbox" aria-expanded={orgMenu} aria-label="Organization switcher">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <span className="max-w-[180px] truncate font-medium">{activeOrg?.name ?? "Select organization"}</span>
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
            {orgMenu && (
              <div className="absolute left-0 top-full z-30 mt-1 w-80 rounded-md border border-border bg-card py-1 shadow-lg" role="listbox">
                {orgs.map((o) => (
                  <button key={o.id} role="option" aria-selected={o.id === activeOrg?.id}
                    onClick={async () => {
                      if (o.id === activeOrg?.id) { setOrgMenu(false); return; }
                      await switchOrg(o.id);
                      setOrgMenu(false);
                    }}
                    className={cn("flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-muted",
                      o.id === activeOrg?.id && "bg-primary-50")}>
                    <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <span>
                      <span className="block font-medium">{o.name}</span>
                      <span className="text-[11px] text-muted-foreground">{o.business_profiles.join(" · ")}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Search */}
          <div className="relative hidden flex-1 max-w-md sm:block">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && search) navigate(`/materials?search=${encodeURIComponent(search)}`); }}
              placeholder="Search materials, SKUs…" className="pl-8" aria-label="Global search" />
          </div>

          <div className="ml-auto flex items-center gap-2">
            <div className="relative"><button onClick={() => { setNotificationMenu(v => !v); setOrgMenu(false); setUserMenu(false); }} className="relative rounded-md p-2 hover:bg-muted" aria-label="Notifications"><Bell className="h-4 w-4 text-muted-foreground" />{(notifications.data?.unread_count ?? 0)>0&&<span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">{notifications.data!.unread_count}</span>}</button>{notificationMenu&&<div className="absolute right-0 top-full z-30 mt-1 w-96 rounded-md border border-border bg-card p-2 shadow-lg"><div className="mb-1 flex justify-between px-2 text-sm font-semibold"><span>Notifications</span><span className="text-xs font-normal text-muted-foreground">{notifications.data?.unread_count ?? 0} unread</span></div>{notifications.isLoading?<p className="p-3 text-xs text-muted-foreground">Loading notifications…</p>:notifications.data?.items.length?notifications.data.items.map(n=><button key={n.id} onClick={async()=>{if(!n.is_read)await post(`/v1/notifications/${n.id}/read`); await notifications.refetch(); setNotificationMenu(false); if(n.link)navigate(n.link);}} className={`block w-full rounded px-2 py-2 text-left text-xs hover:bg-muted ${n.is_read?"":"bg-blue-50"}`}><b className="block">{n.title}</b><span className="block truncate text-muted-foreground">{n.body}</span><span className="mt-1 block text-[10px] text-muted-foreground">{new Date(n.created_at).toLocaleString()}</span></button>):<p className="p-3 text-xs text-muted-foreground">No notifications.</p>}</div>}</div>
            <div className="relative">
              <button onClick={() => { setUserMenu((v) => !v); setOrgMenu(false); }}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted"
                aria-haspopup="menu" aria-expanded={userMenu} aria-label="User menu">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
                  {me?.user.full_name?.split(" ").map((s) => s[0]).slice(0, 2).join("")}
                </span>
                <span className="hidden text-left md:block">
                  <span className="block text-xs font-medium leading-tight">{me?.user.full_name}</span>
                  <span className="block text-[10px] text-muted-foreground">{role}</span>
                </span>
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
              {userMenu && (
                <div className="absolute right-0 top-full z-30 mt-1 w-52 rounded-md border border-border bg-card py-1 shadow-lg" role="menu">
                  <div className="border-b border-border px-3 py-2">
                    <p className="text-xs font-medium">{me?.user.email}</p>
                    <p className="text-[10px] text-muted-foreground">UTC · session cookie</p>
                  </div>
                  <button onClick={logout} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50" role="menuitem">
                    <LogOut className="h-4 w-4" /> Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Breadcrumbs */}
        <div className="flex items-center gap-1.5 border-b border-border bg-card/60 px-4 py-1.5 text-[11px] text-muted-foreground">
          <NavLink to="/" className="hover:text-foreground">Home</NavLink>
          {crumbs.map((c, i) => (
            <React.Fragment key={i}>
              <span>/</span>
              <span className={i === crumbs.length - 1 ? "font-medium text-foreground" : ""}>{c.replace(/-/g, " ")}</span>
            </React.Fragment>
          ))}
        </div>

        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          {/* No page transition — instant render, zero flash on navigation */}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
