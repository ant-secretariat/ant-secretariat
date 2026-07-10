import { useMutation } from "@tanstack/react-query";
import { ArrowRight, LockKeyhole, RotateCcw, UserRoundCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAppStore } from "../store/appStore";

const demoAccounts = [
  {
    userId: "demo-balanced-investor",
    accountName: "균형형 데모 계정",
    description: "중립적인 투자 성향으로 전체 기능을 시연합니다.",
  },
  {
    userId: "demo-active-investor",
    accountName: "적극형 데모 계정",
    description: "공격적인 투자 성향으로 토론과 시뮬레이션을 확인합니다.",
  },
];

export function LoginPage() {
  const navigate = useNavigate();
  const login = useAppStore((state) => state.login);
  const logout = useAppStore((state) => state.logout);
  const [resetMessage, setResetMessage] = useState("");
  const mutation = useMutation({
    mutationFn: (account: (typeof demoAccounts)[number]) => api.createUser(account.userId),
    onSuccess: (_, account) => {
      login({ userId: account.userId, accountName: account.accountName });
      navigate("/onboarding");
    },
  });
  const resetMutation = useMutation({
    mutationFn: (account: (typeof demoAccounts)[number]) => api.resetUser(account.userId),
    onSuccess: (data, account) => {
      logout();
      setResetMessage(`${account.accountName} 초기화 완료 · 분석 이력 ${data.deleted_jobs}건 삭제`);
    },
  });

  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="login-copy">
          <div className="brand-mark">
            <LockKeyhole size={22} />
          </div>
          <p className="eyebrow">Demo Access</p>
          <h1>투자 분석 에이전트 데모</h1>
          <p>
            준비된 시연 계정으로 접속한 뒤 투자 성향을 설정하고, 기업별 인사이트와
            토론형 분석을 확인합니다.
          </p>
        </div>
        <div className="login-card-list">
          {demoAccounts.map((account) => (
            <div
              className="login-card"
              key={account.userId}
              onClick={() => {
                if (!mutation.isPending && !resetMutation.isPending) {
                  mutation.mutate(account);
                }
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if ((event.key === "Enter" || event.key === " ") && !mutation.isPending && !resetMutation.isPending) {
                  mutation.mutate(account);
                }
              }}
            >
              <div>
                <UserRoundCheck size={20} />
                <strong>{account.accountName}</strong>
                <span>{account.description}</span>
              </div>
              <div className="login-card-actions">
                <button
                  className="reset-account-button"
                  disabled={resetMutation.isPending}
                  onClick={(event) => {
                    event.stopPropagation();
                    resetMutation.mutate(account);
                  }}
                  type="button"
                >
                  <RotateCcw size={14} />
                  초기화
                </button>
                <ArrowRight size={18} />
              </div>
            </div>
          ))}
        </div>
        {mutation.error ? <div className="error-box">{mutation.error.message}</div> : null}
        {resetMutation.error ? <div className="error-box">{resetMutation.error.message}</div> : null}
        {resetMessage ? <div className="success-box">{resetMessage}</div> : null}
      </section>
    </main>
  );
}
