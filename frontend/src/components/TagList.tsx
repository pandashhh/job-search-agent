/*
 * Wiederverwendbare Tag-Liste — genutzt für matched_skills auf den
 * Job-Karten und (mit editable=true) für die Blacklists im Filter-
 * Regeln-Bereich.
 *
 * onRemove/onAdd sind optional: ohne sie ist die Liste read-only,
 * mit ihnen kommt ein X-Knopf pro Tag und ein Eingabefeld darunter.
 */

import { useState, type KeyboardEvent } from "react";

interface TagListProps {
  tags: string[];
  onRemove?: (tag: string) => void;
  onAdd?: (tag: string) => void;
  emptyLabel?: string;
  addPlaceholder?: string;
}

export function TagList({
  tags,
  onRemove,
  onAdd,
  emptyLabel,
  addPlaceholder = "Neuer Eintrag …",
}: TagListProps) {
  const [entwurf, setEntwurf] = useState("");
  const editable = Boolean(onRemove || onAdd);

  // Enter im Input-Feld hinzufügen, damit man nicht extra auf einen
  // Button klicken muss — Standard-Erwartung bei Tag-Inputs
  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" && entwurf.trim() && onAdd) {
      event.preventDefault();
      onAdd(entwurf.trim());
      setEntwurf("");
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {tags.length === 0 && emptyLabel && (
        <span className="text-sm italic text-[color:var(--color-text-muted)]">
          {emptyLabel}
        </span>
      )}
      <div className="flex flex-wrap gap-2">
        {tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-2 rounded-md border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)] px-3 py-1 text-sm text-[color:var(--color-text-primary)]"
          >
            {tag}
            {onRemove && (
              <button
                type="button"
                onClick={() => onRemove(tag)}
                aria-label={`${tag} entfernen`}
                className="text-[color:var(--color-text-muted)] transition hover:text-[color:var(--color-accent)]"
              >
                ×
              </button>
            )}
          </span>
        ))}
      </div>
      {editable && onAdd && (
        <div className="flex gap-2">
          <input
            type="text"
            value={entwurf}
            onChange={(event) => setEntwurf(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={addPlaceholder}
            className="flex-1 rounded-md border border-[color:var(--color-surface-border)] bg-[color:var(--color-surface)] px-3 py-2 text-sm text-[color:var(--color-text-primary)] placeholder:text-[color:var(--color-text-muted)] focus:border-[color:var(--color-accent)] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => {
              if (entwurf.trim() && onAdd) {
                onAdd(entwurf.trim());
                setEntwurf("");
              }
            }}
            className="rounded-md bg-[color:var(--color-accent-muted)] px-4 py-2 text-sm font-medium text-[color:var(--color-accent)] transition hover:bg-[color:var(--color-accent)]/25"
          >
            +
          </button>
        </div>
      )}
    </div>
  );
}
