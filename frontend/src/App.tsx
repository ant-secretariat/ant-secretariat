import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { DebatePage } from "./pages/DebatePage";
import { HistoryPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TrendReportDetailPage, TrendReportPage } from "./pages/TrendReportPage";
import { useAppStore } from "./store/appStore";

function RequireUser() {
  const userId = useAppStore((state) => state.userId);
  return userId ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  const userId = useAppStore((state) => state.userId);

  return (
    <>
      {import.meta.env.VITE_USE_MOCK === "true" ? <p className="mock-banner">예시 데이터예요. 실제 수치가 아니에요.</p> : null}
      <Routes>
        <Route path="/login" element={userId ? <Navigate to="/insight" replace /> : <LoginPage />} />
        <Route element={<RequireUser />}>
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/settings" element={<div className="app"><main className="app-main"><SettingsPage /></main></div>} />
          <Route path="/trend-report/:ticker" element={<div className="app"><main className="app-main"><TrendReportDetailPage /></main></div>} />
          <Route element={<AppLayout />}>
            <Route path="/insight" element={<DashboardPage />} />
            <Route path="/trend-report" element={<TrendReportPage />} />
            <Route path="/debate/:jobId?" element={<DebatePage />} />
            <Route path="/history" element={<HistoryPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to={userId ? "/insight" : "/login"} replace />} />
      </Routes>
    </>
  );
}
