import { BrowserRouter, Routes, Route, Navigate } from "react-router";
import { useAuth } from "@/lib/auth";
import AppLayout from "@/components/AppLayout";
import Login from "@/pages/Login";
import CommandCenter from "@/pages/CommandCenter";
import Materials from "@/pages/Materials";
import Inventory from "@/pages/Inventory";
import Customers from "@/pages/Customers";
import Inquiries from "@/pages/Inquiries";
import Quotations from "@/pages/Quotations";
import SalesOrders from "@/pages/SalesOrders";
import Suppliers from "@/pages/Suppliers";
import Procurement from "@/pages/Procurement";
import Market from "@/pages/Market";
import Fabrication from "@/pages/Fabrication";
import Projects from "@/pages/Projects";
import Tenders from "@/pages/Tenders";
import Logistics from "@/pages/Logistics";
import Finance from "@/pages/Finance";
import Audit from "@/pages/Audit";
import Briefing from "@/pages/Briefing";
import { Skeleton } from "@/components/ui";

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
    <BrowserRouter>
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
    </BrowserRouter>
  );
}
