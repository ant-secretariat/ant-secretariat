import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PercentilePath } from "../types";

function toRows(paths?: PercentilePath) {
  const p50 = paths?.p50 ?? [];
  return p50.map((value, index) => ({
    day: index,
    p10: paths?.p10?.[index],
    p50: value,
    p90: paths?.p90?.[index],
  }));
}

export function SimulationChart({ paths }: { paths?: PercentilePath }) {
  const rows = toRows(paths);
  if (!rows.length) {
    return <div className="chart-placeholder">차트 데이터가 없습니다.</div>;
  }

  return (
    <div className="chart-box">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="day" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={72} />
          <Tooltip
            formatter={(value) =>
              typeof value === "number" ? value.toLocaleString("ko-KR") : value
            }
            labelFormatter={(label) => `${label}일 후`}
          />
          <Line type="monotone" dataKey="p90" stroke="#94a3b8" dot={false} strokeWidth={1.5} />
          <Line type="monotone" dataKey="p50" stroke="#0f766e" dot={false} strokeWidth={2.5} />
          <Line type="monotone" dataKey="p10" stroke="#94a3b8" dot={false} strokeWidth={1.5} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
