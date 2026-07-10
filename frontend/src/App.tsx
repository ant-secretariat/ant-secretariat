import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { DebatePage } from "./pages/DebatePage";
import { HistoryPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { TrendReportPage } from "./pages/TrendReportPage";
import { useAppStore } from "./store/appStore";

export default function App() {
  const userId = useAppStore((state) => state.userId);

  return (
    <Routes>
      <Route path="/login" element={userId ? <Navigate to="/insight" replace /> : <LoginPage />} />
      <Route
        path="/onboarding"
        element={userId ? <OnboardingPage /> : <Navigate to="/login" replace />}
      />
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to={userId ? "/insight" : "/login"} replace />} />
        <Route path="/insight" element={userId ? <DashboardPage /> : <Navigate to="/login" replace />} />
        <Route path="/trend-report" element={userId ? <TrendReportPage /> : <Navigate to="/login" replace />} />
        <Route path="/debate/:jobId?" element={userId ? <DebatePage /> : <Navigate to="/login" replace />} />
        <Route path="/history" element={userId ? <HistoryPage /> : <Navigate to="/login" replace />} />
      </Route>
    </Routes>
  );
}
