import { ArrowLeft, Check, ChevronRight, Info, Settings } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import antAlert from "../assets/ant-alert.svg";
import antAnalysis from "../assets/ant-analysis.svg";
import antChart from "../assets/ant-chart.svg";

const ants = { chart: antChart, alert: antAlert, analysis: antAnalysis };

export function Ant({ kind, size }: { kind: keyof typeof ants; size: number }) {
  return <img className="ant" src={ants[kind]} width={size} height={size} alt="" />;
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "text" | "danger" }) {
  return <button type="button" className={`btn btn-${variant} ${className}`} {...props} />;
}

export function TopBar({ title, back, settings }: { title: string; back?: boolean | string | (() => void); settings?: boolean }) {
  const navigate = useNavigate();
  return (
    <header className="topbar">
      {back ? (
        <button
          type="button"
          className="icon-btn"
          aria-label="뒤로 가기"
          onClick={() => (typeof back === "function" ? back() : typeof back === "string" ? navigate(back) : navigate(-1))}
        >
          <ArrowLeft size={24} />
        </button>
      ) : null}
      <h1>{title}</h1>
      {settings ? (
        <Link className="icon-btn settings" to="/settings" aria-label="설정">
          <Settings size={24} />
        </Link>
      ) : null}
    </header>
  );
}

export function Disclaimer() {
  return (
    <p className="disclaimer">
      개미비서단이 제공하는 정보는 투자 판단을 돕기 위한 참고자료일 뿐, 투자 권유나 종목 추천이 아닙니다.
      개미비서단은 금융투자업자가 아니며 개별 투자 상담이나 자금 운용을 제공하지 않습니다. 투자 결정은 이용자 본인의
      판단과 책임으로 이루어져야 하며, 원금 손실이 발생할 수 있고 그 손실은 투자자에게 귀속됩니다.
    </p>
  );
}

export function AiNote() {
  return (
    <p className="ai-note">
      이 내용은 생성형 AI가 작성한 요약·의견입니다.
      <br />
      사실과 다를 수 있으니 원문과 공시를 함께 확인해 주세요.
    </p>
  );
}

export function Tip({ children }: { children: ReactNode }) {
  return (
    <div className="tip">
      <Info size={24} aria-hidden />
      <p>{children}</p>
    </div>
  );
}

export function ListRow({ title, sub, to, onClick }: { title: string; sub?: string; to?: string; onClick?: () => void }) {
  const body = (
    <>
      <span className="row-text">
        <strong>{title}</strong>
        {sub ? <span>{sub}</span> : null}
      </span>
      <ChevronRight size={24} aria-hidden />
    </>
  );
  return to ? (
    <Link className="row" to={to}>
      {body}
    </Link>
  ) : (
    <button type="button" className="row" onClick={onClick}>
      {body}
    </button>
  );
}

export function Chip({
  selected,
  muted,
  onClick,
  disabled,
  children,
}: {
  selected?: boolean;
  muted?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`chip ${selected ? "selected" : ""} ${muted ? "muted" : ""}`}
      aria-pressed={Boolean(selected)}
      disabled={disabled}
      onClick={onClick}
    >
      {selected ? <Check size={20} aria-hidden /> : null}
      {children}
    </button>
  );
}

export function OptionCard({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" role="radio" aria-checked={selected} className={`option ${selected ? "selected" : ""}`} onClick={onClick}>
      <span>{children}</span>
      <i className="radio">{selected ? <Check size={18} aria-hidden /> : null}</i>
    </button>
  );
}

export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

const STEPS = 8;
export function ProgressAnt({ done }: { done: number }) {
  const pct = (Math.min(done, STEPS) / STEPS) * 100;
  return (
    <div className="progress-ant" role="progressbar" aria-label="진행 상태" aria-valuemin={0} aria-valuemax={STEPS} aria-valuenow={done}>
      <div className="progress-ant-rider" style={{ left: `clamp(32px, ${pct}%, calc(100% - 32px))` }}>
        <Ant kind="chart" size={64} />
      </div>
      <div className="progress-ant-track">
        <div style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

const stepNames = ["자료", "찬성", "반대", "판정", "완료"];
/** current: 진행 중인 단계(0~4). 5면 모두 완료. */
export function DebateStepper({ current }: { current: number }) {
  return (
    <ol className="stepper" aria-label={`토론 진행 ${Math.min(current + 1, 5)}/5`}>
      {stepNames.map((name, i) => {
        const state = i < current ? "done" : i === current ? "current" : "todo";
        return (
          <li key={name} className={state} aria-current={state === "current" ? "step" : undefined}>
            <span className="stepper-dot">
              {state === "done" ? <Check size={14} aria-hidden /> : state === "current" ? <i /> : i + 1}
            </span>
            <span className="stepper-name">{name}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "success" | "up" | "down"; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

/** value: 0~1. 값이 없으면 표시하지 않는다. */
export function Confidence({ value }: { value?: number }) {
  if (typeof value !== "number") return null;
  const level = value >= 0.7 ? 3 : value >= 0.4 ? 2 : 1;
  return (
    <span className="confidence">
      확신도 {["낮음", "보통", "높음"][level - 1]}
      <span aria-hidden>
        {[1, 2, 3].map((n) => (
          <i key={n} className={n <= level ? "on" : ""} />
        ))}
      </span>
    </span>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p className="error-text" role="alert">
      {children}
    </p>
  );
}

export function Skeleton() {
  return (
    <div className="skeleton" aria-label="불러오는 중" role="status">
      <i />
      <i />
      <i />
    </div>
  );
}

export function EmptyView({
  title,
  body,
  action,
}: {
  title: ReactNode;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-ant">
        <Ant kind="alert" size={130} />
      </div>
      <h2>{title}</h2>
      <p>{body}</p>
      {action}
    </div>
  );
}
