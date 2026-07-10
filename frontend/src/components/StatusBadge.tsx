import type { JobStatus } from "../types";

const labels: Record<JobStatus, string> = {
  queued: "대기",
  running: "토론 생성",
  debate_completed: "토론 완료",
  simulation_running: "시뮬레이션",
  completed: "완료",
  failed: "실패",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`status-badge ${status}`}>{labels[status] ?? status}</span>;
}
