/*
 * Filter-Regeln bearbeiten (GET/PUT /filter-rules).
 *
 * State-Strategie:
 *  - Der lokale State ("entwurf") ist der aktuelle Bearbeitungsstand.
 *  - Speichern schickt den Entwurf per PUT, das Backend antwortet mit
 *    dem gespeicherten Zustand — den setzen wir dann als neuen Entwurf,
 *    damit Server- und Client-Zustand danach garantiert übereinstimmen.
 */

import { useEffect, useState } from "react";
import { getFilterRules, putFilterRules, type FilterRules } from "../api";
import { TagList } from "./TagList";

export function FilterRulesPanel() {
  const [entwurf, setEntwurf] = useState<FilterRules | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const regeln = await getFilterRules();
        setEntwurf(regeln);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Fehler beim Laden");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <p className="text-sm text-[color:var(--color-text-muted)]">
        Lade Filter-Regeln …
      </p>
    );
  }
  if (!entwurf) {
    return (
      <p className="text-sm text-red-300">
        {error ?? "Filter-Regeln konnten nicht geladen werden."}
      </p>
    );
  }

  function updateTitleBlacklist(next: string[]) {
    setEntwurf((vorher) =>
      vorher ? { ...vorher, title_blacklist: next } : vorher,
    );
  }
  function updateDescriptionBlacklist(next: string[]) {
    setEntwurf((vorher) =>
      vorher ? { ...vorher, description_blacklist: next } : vorher,
    );
  }
  function updateMaxExperience(value: number) {
    setEntwurf((vorher) =>
      vorher ? { ...vorher, max_experience_years: value } : vorher,
    );
  }

  async function handleSave() {
    if (!entwurf) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const gespeichert = await putFilterRules(entwurf);
      setEntwurf(gespeichert);
      setMessage("Gespeichert.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Fehler beim Speichern",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="rounded-lg border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)] p-6">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[color:var(--color-text-muted)]">
          Titel-Blacklist
        </h2>
        <p className="mt-1 mb-4 text-xs text-[color:var(--color-text-muted)]">
          Jobs, deren Titel einen dieser Begriffe enthält, werden vor der
          Bewertung verworfen (case-insensitive Substring-Match).
        </p>
        <TagList
          tags={entwurf.title_blacklist}
          onAdd={(neu) =>
            !entwurf.title_blacklist.includes(neu) &&
            updateTitleBlacklist([...entwurf.title_blacklist, neu])
          }
          onRemove={(tag) =>
            updateTitleBlacklist(
              entwurf.title_blacklist.filter((t) => t !== tag),
            )
          }
          emptyLabel="Keine Blacklist-Einträge — jeder Titel geht durch."
          addPlaceholder="z.B. Senior, Lead …"
        />
      </div>

      <div className="rounded-lg border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)] p-6">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[color:var(--color-text-muted)]">
          Maximale geforderte Berufserfahrung (Jahre)
        </h2>
        <p className="mt-1 mb-4 text-xs text-[color:var(--color-text-muted)]">
          Jobs, in deren Beschreibung eine höhere Zahl Jahre verlangt
          wird, werden verworfen.
        </p>
        <input
          type="number"
          min={0}
          value={entwurf.max_experience_years}
          onChange={(event) =>
            updateMaxExperience(
              Number.parseInt(event.target.value || "0", 10),
            )
          }
          className="w-32 rounded-md border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface)] px-3 py-2 text-sm text-[color:var(--color-text-primary)] focus:border-[color:var(--color-accent)] focus:outline-none"
        />
      </div>

      <div className="rounded-lg border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)] p-6">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[color:var(--color-text-muted)]">
          Beschreibungs-Blacklist
        </h2>
        <p className="mt-1 mb-4 text-xs text-[color:var(--color-text-muted)]">
          Jobs, deren Beschreibung einen dieser Begriffe enthält, werden
          verworfen (case-insensitive).
        </p>
        <TagList
          tags={entwurf.description_blacklist}
          onAdd={(neu) =>
            !entwurf.description_blacklist.includes(neu) &&
            updateDescriptionBlacklist([
              ...entwurf.description_blacklist,
              neu,
            ])
          }
          onRemove={(tag) =>
            updateDescriptionBlacklist(
              entwurf.description_blacklist.filter((t) => t !== tag),
            )
          }
          emptyLabel="Keine Blacklist-Einträge — jede Beschreibung geht durch."
          addPlaceholder="z.B. Beratungsprojekte, Kundenprojekte vor Ort …"
        />
      </div>

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="rounded-md bg-[color:var(--color-accent)] px-5 py-2 text-sm font-medium text-black transition hover:bg-[color:var(--color-accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "Speichere …" : "Speichern"}
        </button>
        {message && (
          <span className="text-sm text-[color:var(--color-accent)]">
            {message}
          </span>
        )}
        {error && <span className="text-sm text-red-300">{error}</span>}
      </div>
    </section>
  );
}
