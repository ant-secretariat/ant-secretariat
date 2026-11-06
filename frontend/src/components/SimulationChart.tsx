import type { PercentilePath } from "../types";

function bands(paths?: PercentilePath) {
  if (!paths?.p50?.length) return null;
  // 서버는 현재 p10/p90을 주고, 계약서(openapi)는 p5/p95를 예정한다. 있는 쪽을 그대로 쓴다.
  const outer = paths.p5 && paths.p95 ? { low: paths.p5, high: paths.p95, lowName: "p5", highName: "p95" } : null;
  const inner = paths.p10 && paths.p90 ? { low: paths.p10, high: paths.p90, lowName: "p10", highName: "p90" } : null;
  const widest = outer ?? inner;
  return widest ? { outer, inner, widest, mid: paths.p50 } : null;
}

const pct = (value: number, base: number) => {
  const p = ((value - base) / base) * 100;
  return `${p >= 0 ? "+" : ""}${p.toFixed(0)}%`;
};

export function simulationStats(paths?: PercentilePath, currentPrice?: number) {
  const b = bands(paths);
  if (!b) return null;
  const base = currentPrice || b.mid[0];
  const last = (a: number[]) => a[a.length - 1];
  return {
    days: b.mid.length - 1,
    lowName: b.widest.lowName,
    highName: b.widest.highName,
    low: pct(last(b.widest.low), base),
    high: pct(last(b.widest.high), base),
    mid: pct(last(b.mid), base),
  };
}

export function SimulationChart({ paths }: { paths?: PercentilePath }) {
  const b = bands(paths);
  if (!b) return <p className="caption">차트 데이터가 없습니다.</p>;

  const w = 312;
  const h = 150;
  const values = [...b.widest.low, ...b.widest.high];
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const x = (i: number) => (i / (b.mid.length - 1)) * w;
  const y = (v: number) => 8 + (1 - (v - min) / span) * (h - 16);
  const area = (low: number[], high: number[]) =>
    [...high.map((v, i) => `${x(i)},${y(v)}`), ...low.map((v, i) => `${x(i)},${y(v)}`).reverse()].join(" ");

  return (
    <svg className="sim-chart" viewBox={`0 0 ${w} ${h + 2}`} role="img" aria-label="시뮬레이션 가격 범위 차트">
      {b.outer ? <polygon className="band-outer" points={area(b.outer.low, b.outer.high)} /> : null}
      {b.inner ? <polygon className={b.outer ? "band-inner" : "band-outer"} points={area(b.inner.low, b.inner.high)} /> : null}
      <polyline className="mid" points={b.mid.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
      <line className="axis" x1="0" x2={w} y1={h + 1} y2={h + 1} />
    </svg>
  );
}
