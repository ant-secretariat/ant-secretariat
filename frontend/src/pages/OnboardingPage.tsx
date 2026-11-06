import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Ant, Button, Chip, ErrorText, OptionCard, ProgressAnt, Tip } from "../components/ui";
import {
  type Answers,
  mismatchMessage,
  profiles,
  questions,
  sectorLabel,
  sectors,
  tickersKey,
  toPayload,
} from "../data/onboarding";
import { useAppStore } from "../store/appStore";

// 단계: 0 안내·동의, 1~6 객관식, 7 퀴즈, 8 관심 산업, 9 결과
const QUIZ = 7;
const INTEREST = 8;
const RESULT = 9;
const MAX_SECTORS = 3;
const MAX_TICKERS = 5;
const draftKey = "ant-secretariat-onboarding";

type Draft = { step: number; consent: boolean; answers: Answers; riskProfile?: string };

function loadDraft(): Draft {
  try {
    const raw = localStorage.getItem(draftKey);
    if (raw) return JSON.parse(raw) as Draft;
  } catch {
    // 저장 내용이 깨졌으면 처음부터 시작한다.
  }
  return { step: 0, consent: false, answers: {} };
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const userId = useAppStore((state) => state.userId) ?? "";
  const [draft, setDraft] = useState<Draft>(loadDraft);
  const [warned, setWarned] = useState<string | null>(null);
  const { step, consent, answers } = draft;

  useEffect(() => {
    try {
      localStorage.setItem(draftKey, JSON.stringify(draft));
    } catch {
      // 이어하기만 안 될 뿐 진행에는 지장 없다.
    }
  }, [draft]);

  const go = (next: number) => {
    setWarned(null);
    setDraft((d) => ({ ...d, step: next }));
    window.scrollTo(0, 0);
  };
  const answer = (patch: Answers) => {
    setWarned(null);
    setDraft((d) => ({ ...d, answers: { ...d.answers, ...patch } }));
  };

  const save = useMutation({
    mutationFn: () => api.saveOnboarding(toPayload(userId, answers)),
    onSuccess: (data) => {
      // 저장 전 조회 결과가 남아 있으면 홈이 다시 온보딩으로 돌려보낸다.
      client.removeQueries({ queryKey: ["user-context", userId] });
      setDraft((d) => ({ ...d, step: RESULT, riskProfile: String(data.risk_profile ?? "") }));
      window.scrollTo(0, 0);
    },
  });

  if (step === 0) {
    return (
      <Shell
        footer={
          <Button disabled={!consent} onClick={() => go(1)}>
            다음
          </Button>
        }
      >
        <div className="onb-intro">
          <Ant kind="chart" size={130} />
          <h1 className="display">
            안녕하세요, 오늘부터 곁에서
            <br />
            투자 공부를 도울 개미 비서예요.
          </h1>
          <p className="lead">제가 어떤 점을 먼저 챙기면 좋을지 알 수 있도록 몇 가지만 여쭤볼게요. 2분이면 끝나요.</p>
          <div className="card consent">
            <p>답변은 확인 포인트를 정리하는 데만 써요.</p>
            <p>종목 추천이나 매수·매도 조언에는 쓰지 않아요.</p>
            <p>답변은 설정에서 언제든 지울 수 있어요.</p>
            <label>
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setDraft((d) => ({ ...d, consent: e.target.checked }))}
              />
              투자 성향 답변 수집·이용에 동의해요 (필수)
            </label>
          </div>
        </div>
      </Shell>
    );
  }

  if (step === RESULT) {
    const profile = profiles[draft.riskProfile ?? ""];
    const horizon = questions[1].options.find((o) => o.id === answers.horizon)?.label;
    const reaction = questions[3].options.find((o) => o.id === answers.loss_reaction)?.label;
    return (
      <Shell
        footer={
          <>
            <div className="btn-row">
              <Button variant="secondary" onClick={() => go(1)}>
                답변 수정
              </Button>
              <Button
                variant="secondary"
                onClick={() => setDraft({ step: 1, consent: true, answers: {} })}
              >
                다시 하기
              </Button>
            </div>
            <Button
              onClick={() => {
                localStorage.setItem(tickersKey, JSON.stringify(answers.tickers ?? []));
                localStorage.removeItem(draftKey);
                navigate("/insight");
              }}
            >
              시작하기
            </Button>
          </>
        }
      >
        <div className="onb-result">
          <ProgressAnt done={8} />
          <h1 className="display">
            지금 답변을 보면
            <br />
            {profile?.label ?? "확인한 성향"}에 가까워요.
          </h1>
          <p className="lead">앞으로 토론 결과에서 {profile?.focus ?? "근거"}을 먼저 챙겨드릴게요.</p>
          <p className="caption">이 결과는 종목 추천이나 적합 여부 판단이 아니에요.</p>
          <div className="card summary">
            <h2>내 답변</h2>
            <p>투자 기간: {horizon}</p>
            <p>하락 시 행동: {reaction}</p>
            <p>관심 산업: {(answers.sectors ?? []).map(sectorLabel).join(", ")}</p>
          </div>
        </div>
      </Shell>
    );
  }

  const header = (
    <>
      <button type="button" className="icon-btn back" aria-label="이전 단계" onClick={() => go(step - 1)}>
        <ArrowLeft size={24} />
      </button>
      <ProgressAnt done={step - 1} />
    </>
  );

  if (step === QUIZ) {
    return (
      <Shell
        footer={
          <Button disabled={!answers.risk_return} onClick={() => go(INTEREST)}>
            다음
          </Button>
        }
      >
        {header}
        <p className="eyebrow">잠깐 퀴즈예요.</p>
        <h1 className="question">
          기대 수익이 높은 투자일수록
          <br />
          손실 위험도 커지는 편일까요?
        </h1>
        <div className="tiles" role="radiogroup">
          <Tile id="yes" label="네, 커지는 편이에요" tone="up" answers={answers} answer={answer} />
          <Tile id="no" label="아니요, 상관없어요" tone="flat" answers={answers} answer={answer} />
        </div>
        {answers.risk_return ? (
          <Tip>보통은 기대 수익이 높을수록 손실 위험도 커요. 다만 높은 위험이 높은 수익을 보장하지는 않아요.</Tip>
        ) : null}
      </Shell>
    );
  }

  if (step === INTEREST) {
    return (
      <Shell
        footer={
          <>
            {save.error ? <ErrorText>저장하지 못했어요. 답변은 그대로 있으니 다시 시도해 주세요.</ErrorText> : null}
            <Button disabled={!answers.sectors?.length || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "저장하고 있어요" : "결과 보기"}
            </Button>
          </>
        }
      >
        {header}
        <p className="eyebrow">마지막이에요.</p>
        <h1 className="question">
          제가 소식을 먼저 챙겨볼
          <br />
          산업을 골라주세요.
        </h1>
        <p className="caption gap">최대 {MAX_SECTORS}개까지 고를 수 있어요.</p>
        <SectorChips answers={answers} answer={answer} />
        <TickerPicker answers={answers} answer={answer} />
      </Shell>
    );
  }

  const q = questions[step - 1];
  const warning = q.id === "loss_limit" ? mismatchMessage(answers) : null;
  const needsWarning = warning && warned !== warning;

  return (
    <Shell
      footer={
        <Button
          disabled={!answers[q.id]}
          onClick={() => {
            if (needsWarning) return setWarned(warning);
            go(step + 1);
          }}
        >
          {warned ? "이대로 다음" : "다음"}
        </Button>
      }
    >
      {header}
      {q.eyebrow ? <p className="eyebrow">{q.eyebrow}</p> : null}
      <h1 className="question">{q.title}</h1>
      {q.sub ? <p className="caption gap">{q.sub}</p> : null}
      <div className="options" role="radiogroup" aria-label={q.title}>
        {q.options.map((o) => (
          <OptionCard key={o.id} selected={answers[q.id] === o.id} onClick={() => answer({ [q.id]: o.id })}>
            {o.label}
          </OptionCard>
        ))}
      </div>
      {q.tip && answers[q.id] ? <Tip>{q.tip}</Tip> : null}
      {warned ? (
        <div className="notice" role="alert">
          <p>{warned}</p>
          <Button variant="text" onClick={() => go(step - 1)}>
            앞 답변 다시 보기
          </Button>
        </div>
      ) : null}
    </Shell>
  );
}

function Shell({ children, footer }: { children: React.ReactNode; footer: React.ReactNode }) {
  return (
    <div className="app">
      <main className="screen onb">
        <div className="onb-body">{children}</div>
        <div className="onb-foot">{footer}</div>
      </main>
    </div>
  );
}

function Tile({
  id,
  label,
  tone,
  answers,
  answer,
}: {
  id: string;
  label: string;
  tone: "up" | "flat";
  answers: Answers;
  answer: (patch: Answers) => void;
}) {
  const selected = answers.risk_return === id;
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      className={`tile tile-${tone} ${selected ? "selected" : ""}`}
      onClick={() => answer({ risk_return: id })}
    >
      <span className="bars" aria-hidden>
        <i />
        <i />
        <i />
      </span>
      {label}
    </button>
  );
}

function SectorChips({ answers, answer }: { answers: Answers; answer: (patch: Answers) => void }) {
  const picked = answers.sectors ?? [];
  const full = picked.length >= MAX_SECTORS;
  return (
    <div className="chips">
      {sectors.map((s) => {
        const on = picked.includes(s.code);
        return (
          <Chip
            key={s.code}
            selected={on}
            muted={full && !on}
            disabled={full && !on}
            onClick={() => answer({ sectors: on ? picked.filter((c) => c !== s.code) : [...picked, s.code] })}
          >
            {s.label}
          </Chip>
        );
      })}
    </div>
  );
}

function TickerPicker({ answers, answer }: { answers: Answers; answer: (patch: Answers) => void }) {
  const [text, setText] = useState("");
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const picked = answers.tickers ?? [];
  const matches = text
    ? (companies.data ?? []).filter((c) => c.company.includes(text) && !picked.includes(c.ticker)).slice(0, 5)
    : [];
  return (
    <div className="field">
      <label htmlFor="ticker">이미 보고 있는 종목이 있다면 함께 알려주세요. (선택)</label>
      <input
        id="ticker"
        value={text}
        placeholder="종목명으로 찾기"
        onChange={(e) => setText(e.target.value)}
        disabled={picked.length >= MAX_TICKERS}
      />
      <p className="helper">최대 {MAX_TICKERS}개까지 추가할 수 있어요.</p>
      {matches.length || picked.length ? (
        <div className="chips">
          {picked.map((ticker) => (
            <Chip key={ticker} selected onClick={() => answer({ tickers: picked.filter((t) => t !== ticker) })}>
              {companies.data?.find((c) => c.ticker === ticker)?.company ?? ticker}
            </Chip>
          ))}
          {matches.map((c) => (
            <Chip
              key={c.ticker}
              onClick={() => {
                answer({ tickers: [...picked, c.ticker] });
                setText("");
              }}
            >
              {c.company}
            </Chip>
          ))}
        </div>
      ) : null}
    </div>
  );
}
