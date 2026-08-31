/*
 * Job-Karte für den Dashboard.
 *
 * Aufbau:
 *  - Kopf: Titel + Firma/Ort links, Fit-Score-Badge rechts
 *  - Meta-Zeile: Site, Remote-Flag, Datum, Gehaltsband (falls vorhanden)
 *  - Reasoning-Vorschau: 3 Zeilen gekürzt, "mehr anzeigen" klappt aus
 *  - Matched-Skills als Tags
 *  - Fuß: Link zur Original-Ausschreibung + Status-Dropdown
 *
 * Der Status-Dropdown ruft onStatusChange() sofort — der Elternteil
 * (Dashboard) aktualisiert den lokalen State optimistisch und ruft die
 * API im Hintergrund. Wenn der API-Call fehlschlägt, macht der Eltern-
 * teil den optimistischen Update rückgängig.
 */

import { useState } from "react";
import type { Job } from "../api";
import { ScoreBadge } from "./ScoreBadge";
import { TagList } from "./TagList";

// Fest im Frontend, weil das Backend bewusst freie Strings akzeptiert —
// eine feste Auswahl zwingt zu konsistenten Werten fürs UI. Neue Status
// hier ergänzen, DB-Migration nicht nötig.
const STATUS_OPTIONS = [
  "neu",
  "interessant",
  "beworben",
  "abgelehnt",
  "kein-interesse",
] as const;

interface JobCardProps {
  job: Job;
  onStatusChange: (jobId: number, status: string) => void;
}

// Grenze für die Reasoning-Vorschau — bewusst nach Zeichen, damit auch
// Reasonings ohne Absätze sauber gekürzt werden
const REASONING_PREVIEW_LEN = 220;

// Datum aus dem Backend (ISO-String) für die deutsche Locale formatieren.
// Fällt auf den Rohwert zurück, wenn `Date` den String nicht parsen kann —
// so sehen wir im UI nie "Invalid Date".
function formatDatum(iso: string): string {
  const datum = new Date(iso);
  if (Number.isNaN(datum.getTime())) {
    return iso;
  }
  return datum.toLocaleDateString("de-DE");
}

export function JobCard({ job, onStatusChange }: JobCardProps) {
  const [erweitert, setErweitert] = useState(false);
  const needsToggle = job.reasoning.length > REASONING_PREVIEW_LEN;
  const angezeigtesReasoning =
    erweitert || !needsToggle
      ? job.reasoning
      : `${job.reasoning.slice(0, REASONING_PREVIEW_LEN)}…`;

  return (
    <article className="rounded-lg border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)] p-5 shadow-sm transition hover:border-[color:var(--color-accent)]/40">
      <header className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-[color:var(--color-text-primary)]">
            <a
              href={job.job_url}
              target="_blank"
              rel="noreferrer"
              className="hover:text-[color:var(--color-accent)]"
            >
              {job.title}
            </a>
          </h3>
          <p className="mt-1 text-sm text-[color:var(--color-text-secondary)]">
            <span className="font-medium">{job.company}</span> ·{" "}
            {job.location}
            {job.is_remote && (
              <span className="ml-2 rounded-sm bg-[color:var(--color-accent-muted)] px-2 py-0.5 text-xs text-[color:var(--color-accent)]">
                remote
              </span>
            )}
          </p>
        </div>
        <ScoreBadge score={job.fit_score} />
      </header>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[color:var(--color-text-muted)]">
        <span>Quelle: {job.site}</span>
        {job.date_posted && (
          <span>Erschienen: {formatDatum(job.date_posted)}</span>
        )}
        {job.job_type && <span>Typ: {job.job_type}</span>}
        {job.min_amount != null && job.max_amount != null && (
          <span>
            {job.min_amount.toLocaleString("de-DE")} –{" "}
            {job.max_amount.toLocaleString("de-DE")} €
          </span>
        )}
      </div>

      <p className="mt-4 text-sm leading-relaxed text-[color:var(--color-text-secondary)]">
        {angezeigtesReasoning}
      </p>
      {needsToggle && (
        <button
          type="button"
          onClick={() => setErweitert((prev) => !prev)}
          className="mt-1 text-xs text-[color:var(--color-accent)] hover:underline"
        >
          {erweitert ? "weniger anzeigen" : "mehr anzeigen"}
        </button>
      )}

      {job.matched_skills.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[color:var(--color-text-muted)]">
            Passende Skills
          </p>
          <TagList tags={job.matched_skills} />
        </div>
      )}

      <footer className="mt-4 flex items-center justify-between border-t border-[color:var(--color-surface-border)] pt-3">
        <a
          href={job.job_url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-[color:var(--color-text-muted)] transition hover:text-[color:var(--color-accent)]"
        >
          Zur Original-Anzeige ↗
        </a>
        <label className="flex items-center gap-2 text-xs text-[color:var(--color-text-muted)]">
          Status
          <select
            value={job.status}
            onChange={(event) =>
              onStatusChange(job.id, event.target.value)
            }
            className="rounded-md border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface)] px-2 py-1 text-sm text-[color:var(--color-text-primary)] focus:border-[color:var(--color-accent)] focus:outline-none"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
            {!STATUS_OPTIONS.includes(
              job.status as (typeof STATUS_OPTIONS)[number],
            ) && <option value={job.status}>{job.status}</option>}
          </select>
        </label>
      </footer>
    </article>
  );
}

export { STATUS_OPTIONS };
