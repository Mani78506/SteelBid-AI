import { BrowserRouter, Routes, Route, Navigate } from "react-router";
import { lazy, Suspense, type ReactNode } from "react";
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
  // Keep the application shell mounted while a route chunk is loading. A
  // root-level Suspense boundary replaces the whole screen during navigation.
  const page = (content: ReactNode) => <Suspense fallback={<PageFallback />}>{content}</Suspense>;

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Guard />}>
          <Route index element={page(<CommandCenter />)} />
          <Route path="/briefing" element={page(<Briefing />)} />
          <Route path="/customers" element={page(<Customers />)} />
          <Route path="/inquiries" element={page(<Inquiries />)} />
          <Route path="/quotations" element={page(<Quotations />)} />
          <Route path="/sales-orders" element={page(<SalesOrders />)} />
          <Route path="/materials" element={page(<Materials />)} />
          <Route path="/inventory" element={page(<Inventory />)} />
          <Route path="/suppliers" element={page(<Suppliers />)} />
          <Route path="/procurement" element={page(<Procurement />)} />
          <Route path="/market" element={page(<Market />)} />
          <Route path="/fabrication" element={page(<Fabrication />)} />
          <Route path="/projects" element={page(<Projects />)} />
          <Route path="/tenders" element={page(<Tenders />)} />
          <Route path="/logistics" element={page(<Logistics />)} />
          <Route path="/finance" element={page(<Finance />)} />
          <Route path="/audit" element={page(<Audit />)} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
