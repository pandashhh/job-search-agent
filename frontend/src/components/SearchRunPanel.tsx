/*
 * Suchlauf-Bereich: Formular für search_term/location + Ergebnis.
 *
 * Der Endpoint POST /search-runs blockiert bis der komplette
 * LangGraph-Lauf fertig ist (30 s+). Deshalb hier:
 *  - Button deaktiviert während des Laufs
 *  - Lade-Indikator mit Kontext-Text ("kann eine Minute dauern")
 *  - Nach Abschluss: Zusammenfassung mit den 4 Zählwerten, dann
 *    Callback an den Elternteil (App) — der bumpt refreshToken,
 *    damit das Dashboard neu lädt.
 */

import { useState, type FormEvent } from "react";
import { postSearchRun, type SearchRunResult } from "../api";

interface SearchRunPanelProps {
  onCompleted: () => void;
}

export function SearchRunPanel({ onCompleted }: SearchRunPanelProps) {
  const [searchTerm, setSearchTerm] = useState("Junior AI Engineer");
  const [location, setLocation] = useState("Hamburg");
  const [running, setRunning] = useState(false);
  const [ergebnis, setErgebnis] = useState<SearchRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRunning(true);
    setError(null);
    setErgebnis(null);
    try {
      const antwort = await postSearchRun({
        search_term: searchTerm,
        location,
      });
      setErgebnis(antwort);
      // Elternteil neu-laden-Signal — Dashboard zieht die neuen Jobs
      onCompleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Suchlauf fehlgeschlagen");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <form
        onSubmit={handleSubmit}
        className="rounded-lg border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)] p-6"
      >
        <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-[color:var(--color-text-muted)]">
          Neuer Suchlauf
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm">
            <span className="text-[color:var(--color-text-secondary)]">
              Suchbegriff
            </span>
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              required
              disabled={running}
              className="rounded-md border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface)] px-3 py-2 text-sm text-[color:var(--color-text-primary)] placeholder:text-[color:var(--color-text-muted)] focus:border-[color:var(--color-accent)] focus:outline-none disabled:opacity-60"
            />
          </label>
          <label className="flex flex-col gap-2 text-sm">
            <span className="text-[color:var(--color-text-secondary)]">
              Standort
            </span>
            <input
              type="text"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              required
              disabled={running}
              className="rounded-md border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface)] px-3 py-2 text-sm text-[color:var(--color-text-primary)] placeholder:text-[color:var(--color-text-muted)] focus:border-[color:var(--color-accent)] focus:outline-none disabled:opacity-60"
            />
          </label>
        </div>
        <div className="mt-5 flex items-center gap-4">
          <button
            type="submit"
            disabled={running}
            className="rounded-md bg-[color:var(--color-accent)] px-5 py-2 text-sm font-medium text-black transition hover:bg-[color:var(--color-accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {running ? "Suchlauf läuft …" : "Suchlauf starten"}
          </button>
          {running && (
            <span className="text-xs text-[color:var(--color-text-muted)]">
              Der Lauf kann 30&nbsp;s bis mehrere Minuten dauern — Fenster
              nicht schließen.
            </span>
          )}
        </div>
      </form>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {ergebnis && (
        <div className="rounded-lg border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)] p-6">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-[color:var(--color-text-muted)]">
            Letztes Ergebnis
          </h2>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <SummaryCell label="Gefunden" value={ergebnis.raw_jobs_count} />
            <SummaryCell
              label="Nach Filter"
              value={ergebnis.filtered_jobs_count}
            />
            <SummaryCell
              label="Verworfen"
              value={ergebnis.rejected_jobs_count}
            />
            <SummaryCell
              label="Bewertet"
              value={ergebnis.evaluated_jobs_count}
              tone="accent"
            />
          </dl>
          {ergebnis.errors.length > 0 && (
            <div className="mt-4 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <p className="mb-1 font-medium">Fehler während des Laufs:</p>
              <ul className="list-disc pl-5">
                {ergebnis.errors.map((message, idx) => (
                  <li key={idx}>{message}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

interface SummaryCellProps {
  label: string;
  value: number;
  tone?: "accent";
}

function SummaryCell({ label, value, tone }: SummaryCellProps) {
  const numberClass =
    tone === "accent"
      ? "text-[color:var(--color-accent)]"
      : "text-[color:var(--color-text-primary)]";
  return (
    <div className="rounded-md border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface)] p-4">
      <dt className="text-xs uppercase tracking-wide text-[color:var(--color-text-muted)]">
        {label}
      </dt>
      <dd className={`mt-2 text-2xl font-semibold ${numberClass}`}>
        {value}
      </dd>
    </div>
  );
}
