import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, UserRound } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { defaultOnboarding, onboardingOptions } from "../data/onboarding";
import { useAppStore } from "../store/appStore";

export function OnboardingPage() {
  const navigate = useNavigate();
  const userId = useAppStore((state) => state.userId);
  const accountName = useAppStore((state) => state.accountName);
  const [form, setForm] = useState(defaultOnboarding);
  const activeUserId = userId ?? "";

  const createUser = useMutation({
    mutationFn: () => api.createUser(activeUserId),
  });
  const saveOnboarding = useMutation({
    mutationFn: () => api.saveOnboarding({ user_id: activeUserId, ...form }),
  });
  const contextQuery = useQuery({
    queryKey: ["user-context", activeUserId],
    queryFn: () => api.userContext(activeUserId),
    retry: false,
    enabled: Boolean(activeUserId),
  });

  const setValue = (key: keyof typeof defaultOnboarding, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const toggleSector = (sector: string) => {
    setForm((prev) => {
      const exists = prev.q6.includes(sector);
      const next = exists ? prev.q6.filter((item) => item !== sector) : [...prev.q6, sector];
      return { ...prev, q6: next.slice(0, 3) };
    });
  };

  const submit = async () => {
    await createUser.mutateAsync();
    await saveOnboarding.mutateAsync();
    await contextQuery.refetch();
    navigate("/insight");
  };

  return (
    <div className="page setup-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Initial Setup</p>
          <h1>투자 성향 설정</h1>
          <p>{accountName}으로 접속했습니다. 분석 결과 해석에 사용할 투자 성향을 설정합니다.</p>
        </div>
        <button className="secondary-button" onClick={() => contextQuery.refetch()}>
          <RefreshCw size={16} />
          새로고침
        </button>
      </header>

      <section className="split-grid">
        <div className="panel">
          <div className="panel-title">
            <UserRound size={18} />
            설문 응답
          </div>
          <Question title="투자 기간">
            <Segmented
              options={onboardingOptions.q1}
              value={form.q1}
              onChange={(value) => setValue("q1", value)}
            />
          </Question>
          <Question title="투자 목표">
            <Segmented
              options={onboardingOptions.q2}
              value={form.q2}
              onChange={(value) => setValue("q2", value)}
            />
          </Question>
          <Question title="투자 금액">
            <Segmented
              options={onboardingOptions.q3}
              value={form.q3}
              onChange={(value) => setValue("q3", value)}
            />
          </Question>
          <Question title="총 자산 대비 비중">
            <Segmented
              options={onboardingOptions.q3_1}
              value={form.q3_1}
              onChange={(value) => setValue("q3_1", value)}
            />
          </Question>
          <Question title="손실 시 행동">
            <Segmented
              options={onboardingOptions.q4}
              value={form.q4}
              onChange={(value) => setValue("q4", value)}
            />
          </Question>
          <Question title="투자 경험">
            <Segmented
              options={onboardingOptions.q5}
              value={form.q5}
              onChange={(value) => setValue("q5", value)}
            />
          </Question>
          <Question title="관심 산업">
            <div className="chip-grid">
              {onboardingOptions.q6.map((sector) => (
                <button
                  key={sector}
                  className={`chip ${form.q6.includes(sector) ? "selected" : ""}`}
                  onClick={() => toggleSector(sector)}
                  type="button"
                >
                  {sector}
                </button>
              ))}
            </div>
          </Question>
          <button className="primary-button wide" onClick={submit} disabled={saveOnboarding.isPending}>
            <CheckCircle2 size={17} />
            {saveOnboarding.isPending ? "저장 중" : "저장하고 시작하기"}
          </button>
          {saveOnboarding.error ? (
            <div className="error-box">{saveOnboarding.error.message}</div>
          ) : null}
        </div>

        <aside className="panel sticky-panel">
          <div className="panel-title">저장된 프로필</div>
          {contextQuery.data ? (
            <div className="profile-list">
              <Info label="위험 성향" value={profileLabel(contextQuery.data.risk_profile)} />
              <Info label="투자 목표" value={goalLabel(contextQuery.data.investment_goal)} />
              <Info label="투자 금액" value={amountLabel(contextQuery.data.investment_amount_range)} />
              <Info label="경험 수준" value={experienceLabel(contextQuery.data.investment_experience)} />
              <Info label="관심 산업" value={contextQuery.data.interest_sectors.join(", ")} />
            </div>
          ) : (
            <p className="muted-text">아직 저장된 온보딩 정보가 없습니다.</p>
          )}
        </aside>
      </section>
    </div>
  );
}

function profileLabel(value: string) {
  return (
    {
      conservative: "안정형",
      moderate_conservative: "안정추구형",
      moderate: "위험중립형",
      aggressive: "적극투자형",
      very_aggressive: "공격투자형",
    }[value] ?? value
  );
}

function goalLabel(value: string) {
  return { short_term: "단기", mid_term: "중기", long_term: "장기" }[value] ?? value;
}

function amountLabel(value: string) {
  return {
    under_500: "500만원 미만",
    "500_2000": "500만원 ~ 2,000만원",
    "2000_5000": "2,000만원 ~ 5,000만원",
    over_5000: "5,000만원 이상",
  }[value] ?? value;
}

function experienceLabel(value: string) {
  return { beginner: "초보", intermediate: "경험 있음", advanced: "고급" }[value] ?? value;
}

function Question({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="question-block">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

function Segmented({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="option-list">
      {options.map((option) => (
        <button
          key={option}
          className={`option-row ${value === option ? "selected" : ""}`}
          onClick={() => onChange(option)}
          type="button"
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <strong>{value || "-"}</strong>
    </div>
  );
}
