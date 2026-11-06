import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { Ant, Button, Disclaimer, ErrorText } from "../components/ui";
import { useAppStore } from "../store/appStore";

export function LoginPage() {
  const login = useAppStore((state) => state.login);
  const start = useMutation({
    mutationFn: async () => {
      const userId = `user-${crypto.randomUUID()}`;
      await api.createUser(userId);
      return userId;
    },
    onSuccess: (userId) => login({ userId, accountName: "" }),
  });

  return (
    <div className="app">
      <main className="screen login">
        <div className="login-hero">
          <Ant kind="chart" size={150} />
          <h1 className="display">
            리포트와 뉴스를
            <br />
            쉬운 말로 정리해 드려요
          </h1>
          <p className="lead">찬성과 반대 근거를 나란히 보고, 어디를 더 확인할지 직접 정할 수 있어요.</p>
        </div>
        <div className="login-foot">
          {start.error ? <ErrorText>시작하지 못했어요. 잠시 후 다시 시도해 주세요.</ErrorText> : null}
          <Button disabled={start.isPending} onClick={() => start.mutate()}>
            {start.isPending ? "준비하고 있어요" : "시작하기"}
          </Button>
          <p className="caption">가입 절차 없이 바로 시작해요.</p>
          <Disclaimer />
        </div>
      </main>
    </div>
  );
}
