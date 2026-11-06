import { ChevronDown, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { DebateArgument } from "../types";
import { Ant, Confidence } from "./ui";

type Speaker = "bull" | "bear" | "judge";
type Side = { summary?: string; arguments?: DebateArgument[] };

export type ChatAgenda = { id?: number; title?: string; bull?: Side; bear?: Side; reasoning?: string };

type Message =
  | { kind: "agenda"; key: string; title: string }
  | { kind: "talk"; key: string; speaker: Speaker; argument?: DebateArgument; text?: string };

const speakers = {
  bull: { name: "찬성", ant: "chart" },
  bear: { name: "반대", ant: "alert" },
  judge: { name: "판정", ant: "analysis" },
} as const;

/** 에이전트 프롬프트의 영어 호칭이 본문에 그대로 나와도 화면 이름과 맞춘다. */
export const plainNames = (text = "") => text.replace(/\bBull\b/g, "찬성 측").replace(/\bBear\b/g, "반대 측");

function toMessages(agendas: ChatAgenda[]) {
  const messages: Message[] = [];
  agendas.forEach((a, i) => {
    const id = a.id ?? i;
    if (a.title) messages.push({ kind: "agenda", key: `${id}-title`, title: a.title });
    for (const speaker of ["bull", "bear"] as const) {
      const side = a[speaker];
      if (side?.arguments?.length) {
        side.arguments.forEach((argument, n) => messages.push({ kind: "talk", key: `${id}-${speaker}-${n}`, speaker, argument }));
      } else if (side?.summary) {
        messages.push({ kind: "talk", key: `${id}-${speaker}`, speaker, text: side.summary });
      }
    }
    if (a.reasoning) messages.push({ kind: "talk", key: `${id}-judge`, speaker: "judge", text: a.reasoning });
  });
  return messages;
}

function Talk({ speaker, grouped, children }: { speaker: Speaker; grouped: boolean; children: React.ReactNode }) {
  const { name, ant } = speakers[speaker];
  return (
    <li className={`talk ${speaker}${grouped ? " grouped" : ""}`} aria-label={name}>
      {grouped ? null : (
        <div className="talk-who" aria-hidden>
          <span className="talk-avatar">
            <Ant kind={ant} size={30} />
          </span>
          {name}
        </div>
      )}
      <div className="bubble">{children}</div>
    </li>
  );
}

function ArgumentBody({ argument }: { argument: DebateArgument }) {
  const [open, setOpen] = useState(-1);
  return (
    <>
      {argument.rebuttal_target ? <p className="bubble-quote">{plainNames(argument.rebuttal_target)}</p> : null}
      {argument.title ? <h3>{plainNames(argument.title)}</h3> : null}
      {argument.content ? <p>{plainNames(argument.content)}</p> : null}
      {argument.source_title ? (
        <span className="source">
          {argument.source_title}
          {argument.source_date ? `, ${argument.source_date}` : ""}
        </span>
      ) : null}
      <Confidence value={argument.confidence} />
      {argument.relation_evidence?.map((r, i) => (
        <div className="relation" key={r.title}>
          <button type="button" aria-expanded={open === i} onClick={() => setOpen(open === i ? -1 : i)}>
            관계 근거: {r.title}
            {open === i ? <X size={20} aria-hidden /> : <ChevronDown size={20} aria-hidden />}
          </button>
          {open === i ? <p>{r.body}</p> : null}
        </div>
      ))}
    </>
  );
}

/** live면 서버가 단계별로 몰아서 준 결과를 한 개씩 보여 준다. 처음 열 때 이미 있던 메시지는 다시 재생하지 않는다. */
export function DebateChat({ agendas, typing, live = false }: { agendas: ChatAgenda[]; typing?: Speaker; live?: boolean }) {
  const messages = toMessages(agendas);
  const [shown, setShown] = useState(messages.length);
  const end = useRef<HTMLDivElement>(null);
  const visible = live ? messages.slice(0, shown) : messages;
  const next = live ? messages.slice(shown).find((m) => m.kind === "talk") : undefined;
  const writer = next?.kind === "talk" ? next.speaker : typing;

  useEffect(() => {
    if (!live || shown >= messages.length) return;
    const t = setTimeout(() => setShown((n) => n + 1), messages[shown].kind === "agenda" ? 300 : 1400);
    return () => clearTimeout(t);
    // messages는 매 렌더 새 배열이고 부모가 1초마다 렌더하므로, 길이로만 타이머를 다시 건다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, shown, messages.length]);

  useEffect(() => {
    // 위 내용을 읽는 중이면 끌어내리지 않는다.
    const fromBottom = document.documentElement.scrollHeight - window.scrollY - window.innerHeight;
    if (live && fromBottom < 500) end.current?.scrollIntoView({ block: "nearest" });
  }, [live, visible.length, writer]);

  return (
    <>
      <ol className={`chat${live ? " live" : ""}`} role={live ? "log" : undefined}>
        {visible.map((m, i) => {
          if (m.kind === "agenda") {
            return (
              <li className="chat-agenda" key={m.key}>
                {m.title}
              </li>
            );
          }
          const prev = visible[i - 1];
          return (
            <Talk key={m.key} speaker={m.speaker} grouped={prev?.kind === "talk" && prev.speaker === m.speaker}>
              {m.argument ? <ArgumentBody argument={m.argument} /> : <p>{plainNames(m.text)}</p>}
            </Talk>
          );
        })}
        {writer ? (
          <li className={`talk ${writer} writing`} aria-label={writer === "judge" ? "판정을 쓰고 있어요" : `${speakers[writer].name} 측이 쓰고 있어요`}>
            <div className="talk-who" aria-hidden>
              <span className="talk-avatar">
                <Ant kind={speakers[writer].ant} size={30} />
              </span>
              {speakers[writer].name}
            </div>
            <div className="bubble typing" aria-hidden>
              <i />
              <i />
              <i />
            </div>
          </li>
        ) : null}
      </ol>
      <div className="chat-end" ref={end} />
    </>
  );
}
