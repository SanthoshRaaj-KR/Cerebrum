"use client";

/**
 * What actually happens between you typing an answer and the next question
 * arriving.
 *
 * Every fact on this panel is read off /api/health and the live session
 * state - the model names, which coordinator is driving, the question
 * band, the search providers, where the competency map came from. Nothing
 * is hardcoded prose about the architecture, because a hardcoded diagram
 * is exactly the thing that goes quietly out of date the first time the
 * config changes.
 *
 * It deliberately shows the machinery and none of the judgements. Which
 * agents run, on which models, in what order - all fine. How any given
 * answer was read is not: that is the one thing the candidate must not see
 * before the report, and putting it on a diagram would leak it just as
 * effectively as saying it out loud.
 */

import styles from "./page.module.css";
import { ResearchBrief, SystemInfo } from "@/lib/api";

const RESUME_MODE = "resume_projects";

type Stage = {
  n: string;
  title: string;
  /** module name -> what runs it. Rendered as mono chips. */
  actors: { name: string; model?: string }[];
  body: string;
};

function stages(system: SystemInfo, modeKey: string): Stage[] {
  const resumeRound = modeKey === RESUME_MODE;
  const providers = system.researchProviders.join(" → ");

  const prep: Stage = resumeRound
    ? {
        n: "1",
        title: "Before the first question",
        actors: [{ name: "resume.py" }, { name: "gateway.py", model: system.model }],
        body:
          "This round has no external syllabus - the material is your own " +
          "work. Your résumé is digested once, then a gateway agent reads it " +
          "and decides what this particular interview should examine: the " +
          "competencies are named after your actual projects, and the red " +
          "flags are claims in your own document that would matter if you " +
          "can't back them up.",
      }
    : {
        n: "1",
        title: "Before the first question",
        actors: [
          { name: "resume.py" },
          ...(system.researchEnabled
            ? [{ name: "research.py", model: providers }]
            : []),
        ],
        body: system.researchEnabled
          ? `Your target role is searched (${providers}, whichever answers ` +
            "first) and distilled into a competency map - what freshers for " +
            "this role actually get asked, and what counts as knowing each " +
            "thing at entry level rather than at a senior one. Your résumé " +
            "is digested alongside it, once, so no later turn re-parses it."
          : "Role research is switched off, so the competency map comes from " +
            "the model's own knowledge of the role rather than a live " +
            "search. Your résumé is still digested once up front.",
      };

  const decide: Stage =
    system.coordinator === "agent"
      ? {
          n: "3",
          title: "…a main agent decides the move",
          actors: [{ name: "agent.py", model: system.model }],
          body:
            "An LLM holding the other two as tools. It is made to judge the " +
            "answer before anything else, then picks one move - challenge a " +
            "wrong claim, redirect a dodge, dig into something thin, ease " +
            "off an honest \"I don't know\", or advance to new ground - and " +
            "which competency to aim at. It never writes a word you see, " +
            "and it owns neither the question cap nor the ledger.",
        }
      : {
          n: "3",
          title: "…a deterministic ladder decides the move",
          actors: [{ name: "interviewer.py" }],
          body:
            "The read is turned into a private instruction and the move is " +
            "settled in code, in fixed priority: a wrong claim outranks a " +
            "dodge, which outranks a thin answer, which outranks moving on. " +
            "Cheaper and entirely predictable. The LLM main agent in " +
            "agent.py is the alternative, switched on in config.yaml.",
        };

  return [
    prep,
    {
      n: "2",
      title: "You answer, and it's read privately…",
      actors: [
        { name: "evaluator.py", model: system.model },
        ...(system.doubleCheckWrong
          ? [{ name: "double-check", model: system.scorerModel }]
          : []),
      ],
      body:
        "Not for a score - for the next question. Was that correct, thin, " +
        "wrong, dodged, or an honest \"I don't know\"; which competency it " +
        "bears on; and what a right answer would have contained that yours " +
        "didn't." +
        (system.doubleCheckWrong
          ? " A wrong read is the only one that gets challenged to your " +
            `face, so it gets a second, focused opinion on ${system.scorerModel} ` +
            "before it counts. Being told you're wrong when you were right " +
            "is the worst thing this can do."
          : ""),
    },
    decide,
    {
      n: "4",
      title: "…and one agent writes the question",
      actors: [
        { name: resumeRound ? "gateway.py" : "questionnaire.py", model: system.model },
      ],
      body:
        "The only thing here allowed to produce words you see. It gets the " +
        "move, the competency to aim at, the coverage ledger and the private " +
        "read - and writes one question, fresh, reacting to what you just " +
        "said. There is no question list being worked through.",
    },
    {
      n: "5",
      title: "Meanwhile, in the background",
      actors: [{ name: "scorecard.py", model: system.scorerModel }],
      body:
        "While you're reading the next question, that answer is judged " +
        "properly on a stronger model - off the critical path, never waited " +
        "on, never shown. At the end those per-answer judgements plus the " +
        "transcript become the scorecard.",
    },
  ];
}

export function Pipeline({
  system,
  modeKey,
  brief,
}: {
  system: SystemInfo;
  modeKey: string;
  brief?: ResearchBrief | null;
}) {
  return (
    <div className={styles.pipeline}>
      {stages(system, modeKey).map((s) => (
        <div key={s.n} className={styles.stage}>
          <span className={styles.stageNum}>{s.n}</span>
          <div className={styles.stageBody}>
            <h3 className={styles.stageTitle}>{s.title}</h3>
            <div className={styles.actors}>
              {s.actors.map((a) => (
                <span key={a.name} className={styles.actor}>
                  {a.name}
                  {a.model && <em className={styles.actorModel}>{a.model}</em>}
                </span>
              ))}
            </div>
            <p className={styles.stageText}>{s.body}</p>
          </div>
        </div>
      ))}

      <ul className={styles.guardrails}>
        <li>
          <strong>Nothing evaluative reaches you until the end.</strong> No
          score, no &quot;good answer&quot;, no rubric - the agent that judges
          and the agent that speaks are separate calls, so an opinion can&apos;t
          leak into the wording.
        </li>
        <li>
          <strong>No clock.</strong> {system.minQuestions}&ndash;
          {system.maxQuestions} questions, sized for about thirty minutes, and
          it ends when every competency has a read - not when time is up.
          Nothing is ever scored on how long you took.
        </li>
        <li>
          <strong>The cap, the coverage ledger and the background scorer live
          in code</strong>, not in a prompt - so they hold whichever
          coordinator is driving.
        </li>
        {brief && (
          <li>
            <strong>This session:</strong>{" "}
            {brief.source === "resume"
              ? `${brief.competencies.length} competencies drawn from your own résumé`
              : brief.grounded
                ? `${brief.competencies.length} competencies from a live search of ${brief.sources.length} source${brief.sources.length === 1 ? "" : "s"}`
                : `${brief.competencies.length} competencies from the model's own knowledge - the search didn't come back`}
            .
          </li>
        )}
      </ul>
    </div>
  );
}

/** The sidebar version: what's running, in one glanceable block. */
export function PipelineCompact({
  system,
  modeKey,
  brief,
}: {
  system: SystemInfo;
  modeKey: string;
  brief?: ResearchBrief | null;
}) {
  const asks = modeKey === RESUME_MODE ? "gateway" : "questionnaire";
  const drives = system.coordinator === "agent" ? "agent.py" : "code ladder";

  return (
    <div className={styles.runningBlock}>
      <span className={styles.hint}>Running</span>
      <dl className={styles.runList}>
        <div>
          <dt>asks</dt>
          <dd>
            {asks} <em>{system.model}</em>
          </dd>
        </div>
        <div>
          <dt>reads</dt>
          <dd>
            evaluator <em>{system.model}</em>
          </dd>
        </div>
        <div>
          <dt>decides</dt>
          <dd>{drives}</dd>
        </div>
        <div>
          <dt>judges</dt>
          <dd>
            scorecard <em>{system.scorerModel}</em>
          </dd>
        </div>
      </dl>
      {brief && (
        <p className={styles.provenance}>
          {brief.source === "resume"
            ? "Competencies built from your résumé"
            : brief.grounded
              ? `Competencies researched from ${brief.sources.length} source${brief.sources.length === 1 ? "" : "s"}`
              : "Competencies from the model's own knowledge"}
        </p>
      )}
    </div>
  );
}
