import { BrowserRouter, Routes, Route, Navigate } from "react-router";
import { lazy, Suspense } from "react";
import { useAuth } from "@/lib/auth";
import AppLayout from "@/components/AppLayout";
import Login from "@/pages/Login";
import { Skeleton } from "@/components/ui";

const CommandCenter = lazy(() => import("@/pages/CommandCenter"));
const Materials = lazy(() => import("@/pages/Materials")); const Inventory = lazy(() => import("@/pages/Inventory"));
const Customers = lazy(() => import("@/pages/Customers")); const Inquiries = lazy(() => import("@/pages/Inquiries"));
const Quotations = lazy(() => import("@/pages/Quotations")); const SalesOrders = lazy(() => import("@/pages/SalesOrders"));
const Suppliers = lazy(() => import("@/pages/Suppliers")); const Procurement = lazy(() => import("@/pages/Procurement"));
const Market = lazy(() => import("@/pages/Market")); const Fabrication = lazy(() => import("@/pages/Fabrication"));
const Projects = lazy(() => import("@/pages/Projects")); const Tenders = lazy(() => import("@/pages/Tenders"));
const Logistics = lazy(() => import("@/pages/Logistics")); const Finance = lazy(() => import("@/pages/Finance"));
const Audit = lazy(() => import("@/pages/Audit")); const Briefing = lazy(() => import("@/pages/Briefing"));
const PageFallback = () => <div className="p-6"><Skeleton className="h-8 w-56" /><Skeleton className="mt-4 h-64 w-full" /></div>;

function Guard() {
  const { me, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="w-64 space-y-3"><Skeleton className="h-8 w-full" /><Skeleton className="h-40 w-full" /></div>
      </div>
    );
  }
  return me ? <AppLayout /> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter><Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Guard />}>
          <Route index element={<CommandCenter />} />
          <Route path="/briefing" element={<Briefing />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/inquiries" element={<Inquiries />} />
          <Route path="/quotations" element={<Quotations />} />
          <Route path="/sales-orders" element={<SalesOrders />} />
          <Route path="/materials" element={<Materials />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/suppliers" element={<Suppliers />} />
          <Route path="/procurement" element={<Procurement />} />
          <Route path="/market" element={<Market />} />
          <Route path="/fabrication" element={<Fabrication />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/tenders" element={<Tenders />} />
          <Route path="/logistics" element={<Logistics />} />
          <Route path="/finance" element={<Finance />} />
          <Route path="/audit" element={<Audit />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense></BrowserRouter>
  );
}
