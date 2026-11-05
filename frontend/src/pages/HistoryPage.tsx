import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Badge, Button, EmptyView, ErrorText, Skeleton, TopBar } from "../components/ui";
import { debateStep, formatJobTime } from "../lib/debate";
import { useAppStore } from "../store/appStore";
import type { DebateJob } from "../types";

function statusBadge(job: DebateJob) {
  if (job.status === "completed") return <Badge tone="success">완료</Badge>;
  if (job.status === "failed") return <Badge>실패</Badge>;
  if (job.status === "debate_completed" || job.status === "simulation_running") return <Badge>시뮬레이션 전</Badge>;
  return <Badge>진행 중 {Math.min(debateStep(job) + 1, 5)}/5</Badge>;
}

export function HistoryPage() {
  const userId = useAppStore((state) => state.userId) ?? "";
  const navigate = useNavigate();
  const client = useQueryClient();
  const jobs = useQuery({ queryKey: ["user-jobs", userId], queryFn: () => api.userJobs(userId) });
  const retry = useMutation({
    mutationFn: (job: DebateJob) =>
      api.startDebate({ user_id: userId, company: job.company, query: String(job.request?.query ?? "") }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["user-jobs", userId] });
      navigate(`/debate/${data.job_id}`);
    },
  });

  return (
    <div className="screen fill">
      <TopBar title="분석 이력" settings />
      {jobs.isLoading ? <Skeleton /> : null}
      {jobs.error ? <ErrorText>이력을 불러오지 못했어요.</ErrorText> : null}
      {jobs.data && !jobs.data.length ? (
        <EmptyView
          title="아직 분석한 이력이 없어요"
          body="첫 토론을 시작하면 여기에 저장돼요."
          action={<Button onClick={() => navigate("/debate")}>토론 시작</Button>}
        />
      ) : null}
      {(jobs.data ?? []).map((job) => (
        <article className="card history" key={job.job_id}>
          <button type="button" onClick={() => navigate(`/debate/${job.job_id}`)}>
            <span className="history-head">
              <strong>{job.company} 토론</strong>
              {statusBadge(job)}
            </span>
            <span className="history-time">{formatJobTime(job.created_at)}</span>
          </button>
          {job.status === "failed" ? (
            <>
              <ErrorText>분석을 마치지 못했어요. 다시 시도해 주세요.</ErrorText>
              <Button variant="text" disabled={retry.isPending} onClick={() => retry.mutate(job)}>
                다시 시도
              </Button>
            </>
          ) : null}
        </article>
      ))}
    </div>
  );
}
