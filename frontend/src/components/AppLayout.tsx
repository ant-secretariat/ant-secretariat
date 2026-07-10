import { Activity, BarChart3, History, LayoutDashboard, Settings2 } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { API_BASE_URL } from "../api/client";
import { useAppStore } from "../store/appStore";

const navItems = [
  { to: "/dashboard", label: "대시보드", icon: LayoutDashboard },
  { to: "/onboarding", label: "온보딩", icon: Settings2 },
  { to: "/debate", label: "토론 분석", icon: BarChart3 },
  { to: "/history", label: "이력", icon: History },
];

export function AppLayout() {
  const userId = useAppStore((state) => state.userId);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Activity size={22} />
          </div>
          <div>
            <strong>Ant Secretariat</strong>
            <span>Financial Agent</span>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              >
                <Icon size={18} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <span>API</span>
          <strong>{API_BASE_URL.replace(/^https?:\/\//, "")}</strong>
          <span>User</span>
          <strong>{userId.slice(0, 12)}...</strong>
        </div>
      </aside>
      <main className="main-panel">
        <Outlet />
      </main>
    </div>
  );
}
