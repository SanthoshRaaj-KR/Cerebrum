"use client";

/**
 * The library: every interview you chose to keep.
 *
 * The reason this screen exists is not storage, it is the second look. One
 * report tells you how a round went. A shelf of them tells you whether the
 * thing you were told to work on last time actually moved - which is the
 * only question a practice tool is really for.
 *
 * So the header is not a count, it is three answers: is the line going up,
 * which rounds are you strong in, and what keeps coming back as a gap. The
 * grid underneath is the way back into any single one of them.
 *
 * Every number here comes from interviews that are already finished and
 * already scored. Nothing on this screen can influence an interview in
 * progress, which is what makes it safe for it to be openly evaluative in
 * a way no other screen outside the report is.
 */

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  ProgressStats,
  SavedSummary,
  Scorecard,
  deleteInterview,
  getProgress,
  listInterviews,
} from "@/lib/api";
import { CountUp, Sparkline } from "./charts";
import { IconArrowLeft, IconArrowRight, IconTrash, IconTrend, ModeIcon } from "./icons";
import { AmbientMesh } from "./mesh";
import { ease, inView, rise, stagger } from "./motion";
import {
  Badge,
  Button,
  ConfirmButton,
  GlassCard,
  Reveal,
  ThemeToggle,
  ui,
} from "./ui";
import { Dots } from "./waiting";
import s from "./library.module.css";

const VERDICT_LABEL: Record<Scorecard["verdict"], string> = {
  strong_yes: "Strong yes",
  yes: "Yes",
  borderline: "Borderline",
  not_yet: "Not yet",
};

const VERDICT_TONE: Record<Scorecard["verdict"], "ok" | "warn" | "bad"> = {
  strong_yes: "ok",
  yes: "ok",
  borderline: "warn",
  not_yet: "bad",
};

function when(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** The three answers the header exists to give. */
function Progress({ stats }: { stats: ProgressStats }) {
  if (stats.count === 0) return null;

  const trend = stats.trend.map((t) => ({
    score: t.score,
    label: `${t.mode} · ${when(t.at)}`,
  }));

  // Enough of a run for "improving" to mean anything. Two interviews is a
  // pair of numbers, not a direction.
  const movement =
    stats.trend.length >= 4
      ? (() => {
          const half = Math.floor(stats.trend.length / 2);
          const early =
            stats.trend.slice(0, half).reduce((a, t) => a + t.score, 0) / half;
          const late =
            stats.trend.slice(half).reduce((a, t) => a + t.score, 0) /
            (stats.trend.length - half);
          return late - early;
        })()
      : null;

  return (
    <motion.div
      className={s.progress}
      initial="hidden"
      animate="shown"
      variants={stagger(0.06)}
    >
      <motion.div className={s.statRow} variants={rise}>
        <div className={s.stat}>
          <span className={s.statValue}>{stats.count}</span>
          <span className={s.statLabel}>kept</span>
        </div>
        {stats.average !== undefined && (
          <div className={s.stat}>
            <span className={s.statValue}>
              <CountUp value={stats.average} />
            </span>
            <span className={s.statLabel}>average</span>
          </div>
        )}
        {stats.best !== undefined && (
          <div className={s.stat}>
            <span className={s.statValue}>
              <CountUp value={stats.best} />
            </span>
            <span className={s.statLabel}>best</span>
          </div>
        )}
        {movement !== null && (
          <div className={s.stat}>
            <span
              className={`${s.statValue} ${
                movement >= 0 ? s.statUp : s.statDown
              }`}
            >
              {movement >= 0 ? "+" : ""}
              {movement.toFixed(1)}
            </span>
            <span className={s.statLabel}>
              {movement >= 0 ? "better lately" : "down lately"}
            </span>
          </div>
        )}
      </motion.div>

      {trend.length > 1 && (
        <motion.div className={s.chart} variants={rise}>
          <div className={s.chartHead}>
            <IconTrend size={15} />
            <span>Score, oldest first</span>
          </div>
          <Sparkline values={trend} />
        </motion.div>
      )}

      <motion.div className={s.breakdown} variants={rise}>
        {stats.byMode.length > 0 && (
          <section className={s.panel}>
            <p className={ui.eyebrow}>By round</p>
            <ul className={s.modeList}>
              {stats.byMode.map((m) => (
                <li key={m.key} className={s.modeRow}>
                  <span className={s.modeName}>
                    <ModeIcon mode={m.key} size={15} />
                    {m.name}
                  </span>
                  <span className={s.modeMeta}>
                    <span className={s.modeAvg}>{m.average}</span>
                    <span className={s.modeCount}>
                      ×{m.count}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {stats.recurringGaps.length > 0 && (
          <section className={s.panel}>
            <p className={ui.eyebrow}>Keeps coming back</p>
            <p className={s.panelHint}>
              Areas that came back as developing or not shown. This is the
              list worth practising against.
            </p>
            <ul className={s.gapList}>
              {stats.recurringGaps.map((g) => (
                <li key={g.name} className={s.gapRow}>
                  <span className={s.gapName}>{g.name}</span>
                  <span className={s.gapTimes}>
                    {g.times}×
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </motion.div>
    </motion.div>
  );
}

export function LibraryScreen({
  storageEnabled,
  onBack,
  onOpen,
}: {
  storageEnabled: boolean;
  onBack: () => void;
  onOpen: (id: string) => void;
}) {
  const [fetched, setFetched] = useState<SavedSummary[] | null>(null);
  const [stats, setStats] = useState<ProgressStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  // With no database there is nothing to fetch and nothing to wait for, so
  // "empty" is derived rather than written into state - which keeps the
  // effect below free of a synchronous setState and its cascading render.
  const items = storageEnabled ? fetched : [];

  useEffect(() => {
    if (!storageEnabled) return;
    let live = true;
    Promise.all([listInterviews(), getProgress()])
      .then(([list, progress]) => {
        if (!live) return;
        setFetched(list.interviews);
        setStats(progress);
      })
      .catch((err) => {
        if (!live) return;
        setFetched([]);
        setError(err instanceof Error ? err.message : "Couldn't load your library.");
      });
    return () => {
      live = false;
    };
  }, [storageEnabled]);

  async function remove(id: string) {
    // Optimistic: the row goes immediately and the stats are refetched, so
    // a delete never leaves you looking at something you just deleted.
    setFetched((prev) => prev?.filter((i) => i.id !== id) ?? prev);
    try {
      await deleteInterview(id);
      setStats(await getProgress());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't delete that.");
      const list = await listInterviews().catch(() => null);
      if (list) setFetched(list.interviews);
    }
  }

  return (
    <>
      <AmbientMesh variant="hero" />
      <main className={`${ui.page} ${ui.pageWide}`}>
        <header className={s.top}>
          <Button variant="ghost" onClick={onBack}>
            <IconArrowLeft size={16} />
            All rounds
          </Button>
          <span className={ui.spacerFlex} />
          <ThemeToggle />
        </header>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={ease}
        >
          <p className={ui.eyebrow}>Your library</p>
          <h1 className={s.title}>Every interview you kept</h1>
          <p className={ui.lede}>
            One report says how a round went. A shelf of them says whether the
            thing you were told to work on actually moved.
          </p>
        </motion.div>

        {error && <p className={`${ui.notice} ${ui.noticeBad}`}>{error}</p>}

        {!storageEnabled && (
          <GlassCard className={s.setup} solid>
            <h2 className={s.setupTitle}>Saving isn&apos;t switched on yet</h2>
            <p className={s.setupBody}>
              Add a <code>MONGODB_URI</code> to <code>.env</code> and restart
              the backend. A free Atlas cluster or a local <code>mongod</code>
              both work — it is only a connection string. Until then everything
              else runs exactly as it does now; you just lose each interview
              when you close the tab.
            </p>
            <pre className={s.setupCode}>
              MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
            </pre>
          </GlassCard>
        )}

        {storageEnabled && items === null && (
          <p className={s.loading}>
            <Dots label="Fetching what you have kept" />
          </p>
        )}

        {stats && <Progress stats={stats} />}

        {items && items.length === 0 && storageEnabled && !error && (
          <GlassCard className={s.setup} solid>
            <h2 className={s.setupTitle}>Nothing kept yet</h2>
            <p className={s.setupBody}>
              Finish a round and press <strong>Store this interview</strong> at
              the bottom of the report. It will show up here, and after a few of
              them this page starts telling you which way you are going.
            </p>
            <Button variant="primary" onClick={onBack}>
              Take a round
              <IconArrowRight size={16} />
            </Button>
          </GlassCard>
        )}

        {items && items.length > 0 && (
          <section>
            <Reveal>
              <p className={ui.eyebrow}>
                {items.length} saved
              </p>
              <h2 className={ui.sectionTitle}>Open any of them again</h2>
            </Reveal>

            <motion.div className={s.grid} variants={stagger(0.04)} {...inView}>
              {items.map((it) => (
                <motion.article key={it.id} className={s.card} variants={rise}>
                  {/* The whole card opens it; the delete sits above that
                      layer so it is not swallowed by the click target. */}
                  <button
                    type="button"
                    className={s.cardOpen}
                    onClick={() => onOpen(it.id)}
                    aria-label={`Open the ${it.mode.name} interview from ${when(
                      it.savedAt
                    )}, scored ${it.score} out of 10`}
                  />
                  <div className={s.cardHead}>
                    <span className={s.cardGlyph}>
                      <ModeIcon mode={it.mode.key} size={18} />
                    </span>
                    <div className={s.cardTitles}>
                      <span className={s.cardName}>{it.mode.name}</span>
                      <span className={s.cardDate}>{when(it.savedAt)}</span>
                    </div>
                    <span className={s.cardScore}>{it.score}</span>
                  </div>

                  <p className={s.cardHeadline}>{it.headline}</p>

                  <div className={s.cardFoot}>
                    <Badge tone={VERDICT_TONE[it.verdict]}>
                      {VERDICT_LABEL[it.verdict]}
                    </Badge>
                    <span className={s.cardQs}>
                      {it.questionCount} question
                      {it.questionCount === 1 ? "" : "s"}
                    </span>
                    <span className={ui.spacerFlex} />
                    <span className={s.cardActions}>
                      <ConfirmButton
                        label={<IconTrash size={15} />}
                        confirmLabel="Delete?"
                        onConfirm={() => remove(it.id)}
                      />
                    </span>
                  </div>
                </motion.article>
              ))}
            </motion.div>
          </section>
        )}
      </main>
    </>
  );
}
