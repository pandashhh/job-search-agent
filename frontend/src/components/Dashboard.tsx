/*
 * Dashboard: Filterleiste + Job-Liste.
 *
 * Datenfluss:
 *  - min_score/status als lokaler State
 *  - useEffect lädt Jobs neu, wenn sich einer der beiden Werte ändert
 *  - Status-Änderung: optimistischer Update auf der Karte, dann API-
 *    Call. Bei Fehler den Status wieder zurückdrehen und Fehler oben
 *    anzeigen.
 *
 * refreshToken (Prop): erlaubt dem Elternteil (App), ein Neuladen zu
 * erzwingen — z.B. nachdem ein Suchlauf frisch fertig ist.
 */

import { useCallback, useEffect, useState } from "react";
import { getJobs, patchJobStatus, type Job } from "../api";
import { JobCard, STATUS_OPTIONS } from "./JobCard";

interface DashboardProps {
  refreshToken: number;
}

export function Dashboard({ refreshToken }: DashboardProps) {
  const [minScore, setMinScore] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Als useCallback, damit der Effect-Handler die Referenz stabil hat.
  // Setzt loading zuerst, damit die alte Liste beim Filter-Wechsel
  // nicht komplett verschwindet (weiche UX)
  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const daten = await getJobs({
        min_score: minScore,
        status: statusFilter || undefined,
        limit: 50,
      });
      setJobs(daten);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unbekannter Fehler");
    } finally {
      setLoading(false);
    }
  }, [minScore, statusFilter]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs, refreshToken]);

  // Optimistischer Update: sofort im UI ändern, dann API. Wenn API
  // fehlschlägt, alten Wert wiederherstellen — sonst wirkt das UI
  // unstimmig, weil das Backend eine andere Wahrheit hat als die UI.
  async function handleStatusChange(jobId: number, neuerStatus: string) {
    const vorherigerStatus = jobs.find((j) => j.id === jobId)?.status;
    setJobs((jetzige) =>
      jetzige.map((job) =>
        job.id === jobId ? { ...job, status: neuerStatus } : job,
      ),
    );
    try {
      await patchJobStatus(jobId, neuerStatus);
    } catch (err) {
      if (vorherigerStatus !== undefined) {
        setJobs((jetzige) =>
          jetzige.map((job) =>
            job.id === jobId ? { ...job, status: vorherigerStatus } : job,
          ),
        );
      }
      setError(`Status-Update fehlgeschlagen: ${err instanceof Error ? err.message : "unbekannter Fehler"}`);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="rounded-lg border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)] p-5">
        <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-[color:var(--color-text-muted)]">
          Filter
        </h2>
        <div className="flex flex-wrap items-end gap-6">
          <label className="flex flex-col gap-2 text-sm">
            <span className="text-[color:var(--color-text-secondary)]">
              Mindest-Score:{" "}
              <span className="font-mono text-[color:var(--color-text-primary)]">
                {minScore.toFixed(2)}
              </span>
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minScore}
              onChange={(event) =>
                setMinScore(Number.parseFloat(event.target.value))
              }
              className="w-64 accent-[color:var(--color-accent)]"
            />
          </label>
          <label className="flex flex-col gap-2 text-sm">
            <span className="text-[color:var(--color-text-secondary)]">
              Status
            </span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="rounded-md border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface)] px-3 py-2 text-sm text-[color:var(--color-text-primary)] focus:border-[color:var(--color-accent)] focus:outline-none"
            >
              <option value="">alle</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-[color:var(--color-text-muted)]">
          Lade Jobs …
        </p>
      ) : jobs.length === 0 ? (
        <p className="text-sm text-[color:var(--color-text-muted)]">
          Keine Jobs für die aktuellen Filter. Passe den Score-Slider an
          oder starte einen neuen Suchlauf.
        </p>
      ) : (
        <div className="grid gap-4">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onStatusChange={handleStatusChange}
            />
          ))}
        </div>
      )}
    </section>
  );
}
