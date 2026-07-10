import { useQuery } from "@tanstack/react-query";
import { Clock, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingBlock } from "../components/LoadingBlock";
import { StatusBadge } from "../components/StatusBadge";
import { useAppStore } from "../store/appStore";

export function HistoryPage() {
  const userId = useAppStore((state) => state.userId);
  const activeUserId = userId ?? "";
  const jobsQuery = useQuery({
    queryKey: ["user-jobs", activeUserId],
    queryFn: () => api.userJobs(activeUserId),
    enabled: Boolean(activeUserId),
  });

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">History</p>
          <h1>분석 이력</h1>
          <p>사용자별 Debate/Simulation 작업 목록입니다.</p>
        </div>
        <button className="secondary-button" onClick={() => jobsQuery.refetch()}>
          <RefreshCw size={16} />
          새로고침
        </button>
      </header>

      <section className="panel">
        <div className="panel-title">
          <Clock size={18} />
          최근 작업
        </div>
        {jobsQuery.isLoading ? (
          <LoadingBlock />
        ) : jobsQuery.data?.length ? (
          <div className="history-list">
            {jobsQuery.data.map((job) => (
              <Link className="history-row" to={`/debate/${job.job_id}`} key={job.job_id}>
                <div>
                  <strong>{job.company}</strong>
                  <span>분석 번호 {job.job_id.replace(/^debate_/, "").slice(0, 8)}</span>
                </div>
                <StatusBadge status={job.status} />
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState title="분석 이력이 없습니다" />
        )}
      </section>
    </div>
  );
}
