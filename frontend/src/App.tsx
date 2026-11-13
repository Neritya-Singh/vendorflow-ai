import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { VendorShell } from "./components/AppShell";
import { ApplyPage } from "./pages/ApplyPage";
import { TrackPage } from "./pages/TrackPage";
import { VendorHome } from "./pages/VendorHome";
import { AdminCase } from "./pages/admin/AdminCase";
import { AdminLayout } from "./pages/admin/AdminLayout";
import { AdminActivity, AdminOverview, AdminQueue } from "./pages/admin/AdminQueue";
import { AppStateProvider } from "./state";

function NotFound() {
  return (
    <div className="mx-auto max-w-md px-4 py-20 text-center">
      <p className="text-sm font-semibold text-navy-600">404</p>
      <h1 className="mt-1 text-2xl font-semibold text-slate-900">Page not found</h1>
      <Link to="/" className="mt-4 inline-block text-sm font-medium text-navy-700 hover:underline">Go to the vendor workspace</Link>
    </div>
  );
}

export function App() {
  return (
    <AppStateProvider>
      <BrowserRouter>
        <a href="#main" className="sr-only z-50 rounded bg-white px-3 py-2 focus:not-sr-only focus:fixed focus:left-3 focus:top-3">Skip to content</a>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminQueue />} />
            <Route path="overview" element={<AdminOverview />} />
            <Route path="activity" element={<AdminActivity />} />
            <Route path="cases/:id" element={<AdminCase />} />
          </Route>
          <Route path="/" element={<VendorShell><VendorHome /></VendorShell>} />
          <Route path="/apply" element={<VendorShell><ApplyPage /></VendorShell>} />
          <Route path="/track" element={<VendorShell><TrackPage /></VendorShell>} />
          <Route path="*" element={<VendorShell><NotFound /></VendorShell>} />
        </Routes>
      </BrowserRouter>
    </AppStateProvider>
  );
}
