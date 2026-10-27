import "./styles.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Shell } from "./components/Shell";
import { Bar } from "./components/ui";
import { Companies } from "./pages/Companies";
import { JobPage } from "./pages/Job";
import { NotFound } from "./pages/NotFound";
import { Overview } from "./pages/Overview";
import { Reports } from "./pages/Reports";
import { Research } from "./pages/Research";
import { Settings } from "./pages/Settings";

const ReportPage = lazy(() => import("./pages/Report").then((m) => ({ default: m.ReportPage })));

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true, retry: 1, staleTime: 2000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Shell>
          <Suspense fallback={<Bar w="40%" h={28} />}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/research" element={<Research />} />
              <Route path="/research/:jobId" element={<JobPage />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/reports/:jobId" element={<ReportPage />} />
              <Route path="/companies" element={<Companies />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </Shell>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
