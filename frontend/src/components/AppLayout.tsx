import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bell, Building2, ChevronDown, ChevronLeft, ChevronRight, ClipboardList, Factory,
  FileText, FolderKanban, Handshake, IndianRupee, LayoutDashboard, LogOut, Menu,
  Package, ScrollText, Search, ShoppingCart, Sparkles, TrendingUp, Truck, Users2,
  Warehouse, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { Input } from "@/components/ui";
import { get, post } from "@/lib/api";

interface NavItem { to: string; label: string; icon: React.ElementType; profiles?: string[] }
interface NavGroup { title: string; items: NavItem[] }

const NAV: NavGroup[] = [
  { title: "Overview", items: [{ to: "/", label: "Command Center", icon: LayoutDashboard }, { to: "/briefing", label: "AI Briefing", icon: Sparkles }] },
  { title: "Sales", items: [{ to: "/customers", label: "Customers", icon: Users2 }, { to: "/inquiries", label: "Inquiries", icon: ClipboardList }, { to: "/quotations", label: "Quotations", icon: FileText }, { to: "/sales-orders", label: "Sales Orders", icon: ShoppingCart }] },
  { title: "Materials & Stock", items: [{ to: "/materials", label: "Materials", icon: Package }, { to: "/inventory", label: "Inventory", icon: Warehouse }] },
  { title: "Procurement", items: [{ to: "/suppliers", label: "Suppliers", icon: Handshake }, { to: "/procurement", label: "Purchase Requests", icon: ShoppingCart }, { to: "/market", label: "Market Prices", icon: TrendingUp }] },
  { title: "Operations", items: [{ to: "/fabrication", label: "Fabrication", icon: Factory, profiles: ["FABRICATOR"] }, { to: "/projects", label: "Projects", icon: FolderKanban, profiles: ["CONTRACTOR", "FABRICATOR"] }, { to: "/tenders", label: "Tenders & BOQ", icon: FileText, profiles: ["CONTRACTOR", "FABRICATOR"] }, { to: "/logistics", label: "Logistics", icon: Truck }] },
  { title: "Finance & Admin", items: [{ to: "/finance", label: "Finance", icon: IndianRupee }, { to: "/audit", label: "Audit Log", icon: ScrollText }] },
];

function NavSection({ group, profiles, collapsed, open, onToggle, onNavigate }: {
  group: NavGroup; profiles: string[]; collapsed?: boolean; open: boolean; onToggle: () => void; onNavigate?: () => void;
}) {
  const items = group.items.filter((item) => !item.profiles || item.profiles.some((profile) => profiles.includes(profile)));
  if (!items.length) return null;
  return <section className="pt-2">
    <button type="button" onClick={onToggle} aria-expanded={open} title={collapsed ? group.title : undefined}
      aria-label={`${open ? "Collapse" : "Expand"} ${group.title} navigation`}
      className={cn("flex w-full items-center rounded-md px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted transition-colors hover:bg-sidebar-hover/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400", collapsed && "justify-center px-2")}>
      {!collapsed && <span className="flex-1 text-left">{group.title}</span>}
      {!collapsed ? (open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />) : <span className="h-1.5 w-1.5 rounded-full bg-sidebar-muted" />}
    </button>
    <ul className={cn("space-y-0.5", !open && "hidden")}>
      {items.map((item) => <li key={item.to}><NavLink to={item.to} end={item.to === "/"} onClick={onNavigate} title={collapsed ? item.label : undefined}
        aria-label={collapsed ? item.label : undefined}
        className={({ isActive }) => cn("group flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400", collapsed && "justify-center px-2", isActive ? "bg-blue-500/18 text-white shadow-[inset_3px_0_0_#3b82f6]" : "text-sidebar-muted hover:bg-sidebar-hover/60 hover:text-slate-200")}>
        <item.icon className="h-4 w-4 shrink-0 opacity-80" />{!collapsed && item.label}
      </NavLink></li>)}
    </ul>
  </section>;
}

export default function AppLayout() {
  const { me, orgs, activeOrg, role, switchOrg, logout } = useAuth();
  const navigate = useNavigate(); const location = useLocation();
  const [orgMenu, setOrgMenu] = React.useState(false); const [userMenu, setUserMenu] = React.useState(false); const [notificationMenu, setNotificationMenu] = React.useState(false); const [mobileNav, setMobileNav] = React.useState(false); const [search, setSearch] = React.useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => localStorage.getItem("steelbid.sidebar.collapsed") === "true");
  const [groupOpen, setGroupOpen] = React.useState<Record<string, boolean>>(() => { try { return JSON.parse(localStorage.getItem("steelbid.sidebar.groups") ?? "{}") as Record<string, boolean>; } catch { return {}; } });
  const profiles = activeOrg?.business_profiles ?? []; const crumbs = location.pathname.split("/").filter(Boolean);
  const notifications = useQuery({ queryKey: ["notifications", activeOrg?.id], enabled: !!activeOrg?.id, queryFn: () => get<{ unread_count: number; items: { id: string; title: string; body?: string; link?: string; is_read: boolean; created_at: string }[] }>("/v1/notifications") });
  React.useEffect(() => { setOrgMenu(false); setUserMenu(false); }, [location.pathname]);
  React.useEffect(() => { localStorage.setItem("steelbid.sidebar.collapsed", String(sidebarCollapsed)); }, [sidebarCollapsed]);
  React.useEffect(() => { localStorage.setItem("steelbid.sidebar.groups", JSON.stringify(groupOpen)); }, [groupOpen]);
  const isGroupOpen = (title: string) => groupOpen[title] ?? true;
  const toggleGroup = (title: string) => setGroupOpen((value) => ({ ...value, [title]: !isGroupOpen(title) }));
  const sections = (collapsed = false, mobile = false) => NAV.map((group) => <NavSection key={group.title} group={group} profiles={profiles} collapsed={collapsed} open={isGroupOpen(group.title)} onToggle={() => toggleGroup(group.title)} onNavigate={mobile ? () => setMobileNav(false) : undefined} />);

  return <div className="flex h-screen overflow-hidden bg-background">
    <motion.aside initial={{ x: -8, opacity: 0 }} animate={{ x: 0, opacity: 1 }} className={cn("relative hidden shrink-0 flex-col bg-sidebar text-slate-300 transition-[width] duration-200 lg:flex", sidebarCollapsed ? "w-[72px]" : "w-[260px]")}>
      <div className={cn("flex h-16 items-center gap-2.5 border-b border-sidebar-border px-4", sidebarCollapsed && "justify-center px-2")}><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-white"><Factory className="h-[18px] w-[18px]" /></div>{!sidebarCollapsed && <div><p className="text-sm font-bold leading-tight text-white">SteelBid AI</p><p className="text-[10px] text-sidebar-muted">Steel Business OS</p></div>}</div>
      <button type="button" onClick={() => setSidebarCollapsed((value) => !value)} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} className="absolute -right-3 top-[52px] z-10 grid h-6 w-6 place-items-center rounded-full border border-sidebar-border bg-sidebar text-sidebar-muted shadow-sm transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400">{sidebarCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}</button>
      <nav className="flex-1 overflow-y-auto px-2 pb-4" aria-label="Primary">{sections(sidebarCollapsed)}</nav>
      <div className={cn("border-t border-sidebar-border px-4 py-3", sidebarCollapsed && "px-2 text-center")}>{sidebarCollapsed ? <span title={activeOrg?.name}><Building2 className="mx-auto h-4 w-4 text-sidebar-muted" /></span> : <><p className="truncate text-xs font-medium text-slate-200">{activeOrg?.name}</p><p className="text-[10px] text-sidebar-muted">{role} · {profiles.join(" + ") || "—"}</p></>}</div>
    </motion.aside>
    <AnimatePresence>{mobileNav && <motion.div className="fixed inset-0 z-40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileNav(false)} /><motion.aside initial={{ x: -260 }} animate={{ x: 0 }} exit={{ x: -260 }} transition={{ type: "tween", duration: 0.2 }} className="absolute left-0 top-0 h-full w-64 overflow-y-auto bg-sidebar pb-6 text-slate-300"><div className="flex h-16 items-center justify-between border-b border-sidebar-border px-4"><p className="text-sm font-bold text-white">SteelBid AI</p><button onClick={() => setMobileNav(false)} aria-label="Close menu" className="rounded p-1 focus-visible:ring-2 focus-visible:ring-blue-400"><X className="h-5 w-5" /></button></div><nav className="px-2" aria-label="Mobile primary">{sections(false, true)}</nav></motion.aside></motion.div>}</AnimatePresence>
    <div className="flex min-w-0 flex-1 flex-col"><header className="flex h-16 shrink-0 items-center gap-3 border-b border-border bg-card px-4"><button className="rounded p-1 lg:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => setMobileNav(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
      <div className="relative"><button onClick={() => { setOrgMenu((value) => !value); setUserMenu(false); }} className="flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-sm hover:bg-muted" aria-haspopup="listbox" aria-expanded={orgMenu}><Building2 className="h-4 w-4 text-muted-foreground" /><span className="max-w-[180px] truncate font-medium">{activeOrg?.name ?? "Select organization"}</span><ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /></button>{orgMenu && <div className="absolute left-0 top-full z-30 mt-1 w-80 rounded-md border border-border bg-card py-1 shadow-lg" role="listbox">{orgs.map((org) => <button key={org.id} role="option" aria-selected={org.id === activeOrg?.id} onClick={async () => { if (org.id !== activeOrg?.id) await switchOrg(org.id); setOrgMenu(false); }} className={cn("flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-muted", org.id === activeOrg?.id && "bg-primary-50")}><Building2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" /><span><span className="block font-medium">{org.name}</span><span className="text-[11px] text-muted-foreground">{org.business_profiles.join(" · ")}</span></span></button>)}</div>}</div>
      <div className="relative hidden max-w-md flex-1 sm:block"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && search) navigate(`/materials?search=${encodeURIComponent(search)}`); }} placeholder="Search materials, SKUs…" className="pl-8" aria-label="Global search" /></div>
      <div className="ml-auto flex items-center gap-2"><div className="relative"><button onClick={() => { setNotificationMenu((value) => !value); setOrgMenu(false); setUserMenu(false); }} className="relative rounded-md p-2 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Notifications"><Bell className="h-4 w-4 text-muted-foreground" />{(notifications.data?.unread_count ?? 0) > 0 && <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">{notifications.data!.unread_count}</span>}</button>{notificationMenu && <div className="absolute right-0 top-full z-30 mt-1 w-80 rounded-md border border-border bg-card p-2 shadow-lg"><div className="mb-1 flex justify-between px-2 text-sm font-semibold"><span>Notifications</span><span className="text-xs font-normal text-muted-foreground">{notifications.data?.unread_count ?? 0} unread</span></div>{notifications.isLoading ? <p className="p-3 text-xs text-muted-foreground">Loading notifications…</p> : notifications.data?.items.length ? notifications.data.items.map((notice) => <button key={notice.id} onClick={async () => { if (!notice.is_read) await post(`/v1/notifications/${notice.id}/read`); await notifications.refetch(); setNotificationMenu(false); if (notice.link) navigate(notice.link); }} className={cn("block w-full rounded px-2 py-2 text-left text-xs hover:bg-muted", !notice.is_read && "bg-blue-50")}><b className="block">{notice.title}</b><span className="block truncate text-muted-foreground">{notice.body}</span></button>) : <p className="p-3 text-xs text-muted-foreground">No notifications.</p>}</div>}</div>
      <div className="relative"><button onClick={() => { setUserMenu((value) => !value); setOrgMenu(false); }} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted" aria-haspopup="menu" aria-expanded={userMenu}><span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">{me?.user.full_name?.split(" ").map((name) => name[0]).slice(0, 2).join("")}</span><span className="hidden text-left md:block"><span className="block text-xs font-medium leading-tight">{me?.user.full_name}</span><span className="block text-[10px] text-muted-foreground">{role}</span></span><ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /></button>{userMenu && <div className="absolute right-0 top-full z-30 mt-1 w-52 rounded-md border border-border bg-card py-1 shadow-lg" role="menu"><div className="border-b border-border px-3 py-2"><p className="text-xs font-medium">{me?.user.email}</p></div><button onClick={logout} className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50" role="menuitem"><LogOut className="h-4 w-4" />Sign out</button></div>}</div></div>
    </header><div className="flex items-center gap-1.5 border-b border-border bg-card/60 px-4 py-1.5 text-[11px] text-muted-foreground"><NavLink to="/" className="hover:text-foreground">Home</NavLink>{crumbs.map((crumb, index) => <React.Fragment key={`${crumb}-${index}`}><span>/</span><span className={index === crumbs.length - 1 ? "font-medium capitalize text-foreground" : "capitalize"}>{crumb.replace(/-/g, " ")}</span></React.Fragment>)}</div><main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6"><Outlet /></main></div>
  </div>;
}
