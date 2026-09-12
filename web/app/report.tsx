"use client";

/**
 * The report.
 *
 * The only evaluative screen in the product, and the one people actually
 * read. It is deliberately long: a verdict tells you where you stand, and
 * only the question-by-question section tells you what to do about it.
 *
 * The order is chosen. Verdict first, because that is the question anyone
 * opens this to answer and burying it reads as evasion. Then the summary,
 * then the per-question breakdown, which is the substance. Competencies
 * and coach notes after, and the provenance last - it matters for trust
 * but nobody needs it before they know how they did.
 *
 * Every status is a word before it is a colour, so the report survives
 * being read by someone who cannot tell the colours apart.
 */

import {
  AnswerVerdict,
  Scorecard,
  SessionState,
  SystemInfo,
} from "@/lib/api";
import {
  IconArrowLeft,
  IconCheck,
  IconCross,
  IconMinus,
  ModeIcon,
} from "./icons";
import { Badge, Button, ThemeToggle, ui } from "./ui";
import s from "./report.module.css";

const VERDICT_LABEL: Record<Scorecard["verdict"], string> = {
  strong_yes: "Strong yes",
  yes: "Yes",
  borderline: "Borderline",
  not_yet: "Not yet",
};

const VERDICT_CLASS: Record<Scorecard["verdict"], string> = {
  strong_yes: s.stampStrong_yes,
  yes: s.stampYes,
  borderline: s.stampBorderline,
  not_yet: s.stampNot_yet,
};

const STATUS_LABEL: Record<string, string> = {
  solid: "Solid",
  developing: "Developing",
  not_shown: "Not shown",
  not_covered: "Not covered",
};

const STATUS_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  solid: "ok",
  developing: "warn",
  not_shown: "bad",
  not_covered: "neutral",
};

const DEPTH_LABEL: Record<AnswerVerdict["depth"], string> = {
  solid: "Solid",
  partial: "Partial",
  absent: "Missed",
};

const DEPTH_TONE: Record<AnswerVerdict["depth"], "ok" | "warn" | "bad"> = {
  solid: "ok",
  partial: "warn",
  absent: "bad",
};

function DepthIcon({ depth }: { depth: AnswerVerdict["depth"] }) {
  if (depth === "solid") return <IconCheck size={13} />;
  if (depth === "partial") return <IconMinus size={13} />;
  return <IconCross size={13} />;
}

/** One question, taken apart: what was asked, what you said, what was
 * missing, what good sounds like, what to do next time. */
function QuestionCard({ v }: { v: AnswerVerdict }) {
  const rule =
    v.depth === "solid"
      ? s.itemSolid
      : v.depth === "partial"
        ? s.itemPartial
        : s.itemAbsent;

  return (
    <article className={`${s.item} ${rule}`}>
      <header className={s.itemHead}>
        <div>
          <p className={s.qNum}>
            Question {v.index}
            {v.competency && ` · ${v.competency}`}
          </p>
          <h3 className={s.qText}>{v.question}</h3>
        </div>
        <Badge tone={DEPTH_TONE[v.depth]}>
          <DepthIcon depth={v.depth} />
          {DEPTH_LABEL[v.depth]}
        </Badge>
      </header>

      <div className={s.itemBody}>
        <section className={s.block}>
          <p className={s.blockLabel}>What you said</p>
          <p className={`${s.blockText} ${s.yourAnswer}`}>
            {v.skipped ? <em>You skipped this one.</em> : v.answer || <em>—</em>}
          </p>
        </section>

        {v.evidence && (
          <section className={s.block}>
            <p className={s.blockLabel}>What that showed</p>
            <p className={s.blockText}>{v.evidence}</p>
          </section>
        )}

        {v.gap && (
          <section className={s.block}>
            <p className={s.blockLabel}>
              {v.correct ? "What was still missing" : "What went wrong"}
            </p>
            <p className={s.blockText}>{v.gap}</p>
          </section>
        )}

        {v.better && (
          <section className={`${s.block} ${s.blockBetter}`}>
            <p className={s.blockLabel}>
              {v.correct
                ? "What would have taken it further"
                : "What a strong answer sounds like"}
            </p>
            <p className={s.blockText}>{v.better}</p>
          </section>
        )}

        {v.improve && (
          <section className={`${s.block} ${s.blockImprove}`}>
            <p className={s.blockLabel}>Next time</p>
            <p className={s.blockText}>{v.improve}</p>
          </section>
        )}
      </div>
    </article>
  );
}

export function ReportScreen({
  session,
  report,
  system,
  onRestart,
}: {
  session: SessionState;
  report: Scorecard;
  system: SystemInfo | null;
  onRestart: () => void;
}) {
  const answered = report.answers ?? [];
  const resumeRound = session.mode.key === "resume_projects";

  return (
    <main className={`${ui.page} ${ui.pageWide}`}>
      <header className={s.verdict}>
        <div className={ui.eyebrow}>
          <ModeIcon mode={session.mode.key} size={14} />
          {session.mode.name}
          {session.role && ` · ${session.role}`}
          <span className={ui.spacerFlex} />
        </div>

        <div className={s.verdictTop}>
          <span className={s.score}>
            <span className={s.scoreNum}>{report.score}</span>
            <span className={s.scoreOf}>/10</span>
          </span>
          <span className={`${s.stamp} ${VERDICT_CLASS[report.verdict]}`}>
            {VERDICT_LABEL[report.verdict]}
          </span>
          <span className={ui.spacerFlex} />
          <ThemeToggle />
        </div>

        <h1 className={s.headline}>{report.headline}</h1>
        <p className={s.meta}>
          {session.turns.length} question
          {session.turns.length === 1 ? "" : "s"} · judged against an
          entry-level bar
        </p>
      </header>

      {!report.grounded && (
        <p className={ui.notice}>
          {resumeRound
            ? "A competency map couldn't be built from the résumé this time, so this is based on the transcript alone."
            : "The role research didn't come back this time, so the competencies below come from the model's own knowledge rather than a live search."}
        </p>
      )}

      <div className={s.split}>
        {report.strengths.length > 0 && (
          <section>
            <p className={ui.eyebrow}>What held up</p>
            <ul className={s.list}>
              {report.strengths.map((x, i) => (
                <li key={i} className={s.listItem}>
                  <span className={`${s.bullet} ${s.bulletOk}`} />
                  {x}
                </li>
              ))}
            </ul>
          </section>
        )}

        {report.gaps.length > 0 && (
          <section>
            <p className={ui.eyebrow}>What didn&apos;t</p>
            <ul className={s.list}>
              {report.gaps.map((x, i) => (
                <li key={i} className={s.listItem}>
                  <span className={`${s.bullet} ${s.bulletBad}`} />
                  {x}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {answered.length > 0 && (
        <section>
          <p className={ui.eyebrow}>Question by question</p>
          <h2 className={ui.sectionTitle}>Every answer, taken apart</h2>
          <p className={ui.lede}>
            Each one was judged on its own while the interview was still
            running. This is where the verdict above came from.
          </p>
          <div className={s.qa} style={{ marginTop: "var(--space-5)" }}>
            {answered.map((v) => (
              <QuestionCard key={v.index} v={v} />
            ))}
          </div>
        </section>
      )}

      {report.competencies.length > 0 && (
        <section>
          <p className={ui.eyebrow}>By area</p>
          <h2 className={ui.sectionTitle}>
            {resumeRound
              ? "What your own work showed"
              : "What this role expects of a fresher"}
          </h2>
          <div className={s.table} style={{ marginTop: "var(--space-4)" }}>
            {report.competencies.map((c) => (
              <div key={c.name} className={s.row}>
                <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>
                  {STATUS_LABEL[c.status] ?? c.status}
                </Badge>
                <div>
                  <p className={s.rowName}>{c.name}</p>
                  {c.evidence && <p className={s.rowEvidence}>{c.evidence}</p>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {report.notes.length > 0 && (
        <section>
          <p className={ui.eyebrow}>Coach notes</p>
          <h2 className={ui.sectionTitle}>Patterns worth working on</h2>
          <ul className={s.list} style={{ marginTop: "var(--space-4)" }}>
            {report.notes.map((n, i) => (
              <li key={i} className={s.listItem}>
                <span className={s.bullet} />
                {n}
              </li>
            ))}
          </ul>
        </section>
      )}

      {system && (
        <section>
          <p className={ui.eyebrow}>How this was judged</p>
          <ul className={s.prov}>
            <li>
              <strong>Every answer was judged on its own, as you went.</strong>{" "}
              Each went to <code>{system.scorerModel}</code> in the background
              while you were already reading the next question, so it got real
              attention rather than a skim at the end.
            </li>
            <li>
              <strong>None of it was visible during the interview.</strong> The
              agent that judged and the agent that spoke to you were separate
              calls — an opinion could not leak into the wording of the next
              question.
            </li>
            {system.doubleCheckWrong && (
              <li>
                <strong>Wrong answers were double-checked.</strong> Anything the
                fast read called incorrect got a second opinion on{" "}
                <code>{system.scorerModel}</code> before it counted — a
                vague-but-right answer is not a wrong one.
              </li>
            )}
            <li>
              <strong>Graded against a fresher bar.</strong> Naming the concept,
              one worked example, and reasoning about a trade-off out loud is a
              solid answer at this level. An honest &quot;I don&apos;t
              know&quot; costs far less than a confident wrong claim.
            </li>
            <li>
              <strong>Nothing was scored on speed.</strong> There was no clock;
              how long you took is not an input to any of this.
            </li>
          </ul>
        </section>
      )}

      {report.sources.length > 0 && (
        <section>
          <p className={ui.eyebrow}>Researched from</p>
          <ul className={s.sources}>
            {report.sources.map((u) => (
              <li key={u}>
                <a href={u} target="_blank" rel="noreferrer">
                  {u}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className={s.footer}>
        <Button variant="primary" onClick={onRestart}>
          <IconArrowLeft size={16} />
          Take another round
        </Button>
      </div>
    </main>
  );
}
