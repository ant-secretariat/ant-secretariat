import { Activity, BarChart3, History, LogOut, Search } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAppStore } from "../store/appStore";

const navItems = [
  { to: "/insight", label: "빠른 인사이트", icon: Search },
  { to: "/debate", label: "토론·시뮬레이션", icon: BarChart3 },
  { to: "/history", label: "분석 이력", icon: History },
];

export function AppLayout() {
  const userId = useAppStore((state) => state.userId);
  const accountName = useAppStore((state) => state.accountName);
  const logout = useAppStore((state) => state.logout);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

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
          <span>시연 계정</span>
          <strong>{accountName}</strong>
          <span>{userId}</span>
          <button className="sidebar-link" onClick={() => navigate("/onboarding")} type="button">
            투자 성향 수정
          </button>
          <button className="sidebar-link danger" onClick={handleLogout} type="button">
            <LogOut size={14} />
            로그아웃
          </button>
        </div>
      </aside>
      <main className="main-panel">
        <Outlet />
      </main>
    </div>
  );
}
