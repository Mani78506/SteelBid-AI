import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { AuthProvider } from "@/lib/auth";
import { ToastProvider } from "@/components/Toast";
import { ApiError } from "@/lib/api";
import "@/index.css";

const qc = new QueryClient();
qc.setDefaultOptions({
  queries: {
    retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    refetchOnWindowFocus: false,
    staleTime: 15_000,
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
