import { FileText, History, Home, Scale } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const tabs = [
  { to: "/insight", label: "홈", icon: Home },
  { to: "/trend-report", label: "트렌드 리포트", icon: FileText },
  { to: "/debate", label: "토론", icon: Scale },
  { to: "/history", label: "이력", icon: History },
];

export function AppLayout() {
  return (
    <div className="app">
      <main className="app-main">
        <Outlet />
      </main>
      <nav className="tabbar" aria-label="주요 메뉴">
        {tabs.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
            <Icon size={24} aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
