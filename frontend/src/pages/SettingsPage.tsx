import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Button, Disclaimer, ErrorText, ListRow, Sheet, Skeleton, TopBar } from "../components/ui";
import { profiles, readTickers, sectorLabel, tickersKey } from "../data/onboarding";
import { useAppStore } from "../store/appStore";

const alertKey = "ant-secretariat-debate-alert";

export function SettingsPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const userId = useAppStore((state) => state.userId) ?? "";
  const logout = useAppStore((state) => state.logout);
  const [confirming, setConfirming] = useState(false);
  // shortcut: 알림 설정 API가 없어 이 브라우저에만 저장한다. API가 생기면 서버로 옮긴다.
  const [alertOn, setAlertOn] = useState(() => localStorage.getItem(alertKey) !== "off");

  const context = useQuery({
    queryKey: ["user-context", userId],
    queryFn: () => api.userContext(userId),
    retry: false,
  });
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const jobs = useQuery({ queryKey: ["user-jobs", userId], queryFn: () => api.userJobs(userId) });
  const reset = useMutation({
    mutationFn: () => api.resetUser(userId),
    onSuccess: () => {
      client.clear();
      localStorage.removeItem("ant-secretariat-onboarding");
      localStorage.removeItem("ant-secretariat-last-report");
      localStorage.removeItem(tickersKey);
      logout();
      navigate("/login", { replace: true });
    },
  });

  const profile = profiles[context.data?.risk_profile ?? ""];
  const sectors = context.data?.interest_sectors ?? [];
  const jobCount = jobs.data?.length ?? 0;
  const tickers = readTickers();
  const tickerNames = (companies.data ?? []).filter((c) => tickers.includes(c.ticker)).map((c) => c.company);

  return (
    <div className="screen">
      <TopBar title="설정" back />
      {context.isLoading ? <Skeleton /> : null}
      {context.error ? <ErrorText>내 성향을 불러오지 못했어요.</ErrorText> : null}

      <h2 className="section-title">내 성향</h2>
      <div className="card list">
        <ListRow
          title={profile?.label ?? "아직 답변하지 않았어요"}
          sub={profile ? `${profile.focus}을 먼저 챙겨드려요.` : undefined}
          to="/onboarding"
        />
        <ListRow title="답변 수정" sub="8개 질문의 답을 고쳐요." to="/onboarding" />
      </div>

      <h2 className="section-title">관심 산업과 종목</h2>
      <div className="card list">
        <ListRow
          title={`관심 산업 ${sectors.length}개`}
          sub={sectors.map(sectorLabel).join(", ")}
          to="/onboarding"
        />
        {tickerNames.length ? (
          <ListRow title={`관심 종목 ${tickerNames.length}개`} sub={tickerNames.join(", ")} to="/onboarding" />
        ) : null}
      </div>

      <h2 className="section-title">알림</h2>
      <div className="card list">
        <ListRow
          title="토론 완료 알림"
          sub={alertOn ? "켜짐" : "꺼짐"}
          onClick={() => {
            const next = !alertOn;
            setAlertOn(next);
            localStorage.setItem(alertKey, next ? "on" : "off");
          }}
        />
      </div>

      <h2 className="section-title">내 데이터</h2>
      <Button variant="secondary" onClick={() => setConfirming(true)}>
        데이터 초기화
      </Button>
      <Disclaimer />

      {confirming ? (
        <Sheet title="데이터를 초기화할까요?" onClose={() => setConfirming(false)}>
          <p className="sheet-body">토론 작업 {jobCount}건과 성향 답변이 지워져요. 되돌릴 수 없어요.</p>
          {reset.error ? <ErrorText>초기화하지 못했어요. 다시 시도해 주세요.</ErrorText> : null}
          <Button variant="danger" disabled={reset.isPending} onClick={() => reset.mutate()}>
            {jobCount}건 지우고 초기화
          </Button>
          <Button variant="text" className="cancel" onClick={() => setConfirming(false)}>
            취소
          </Button>
        </Sheet>
      ) : null}
    </div>
  );
}
