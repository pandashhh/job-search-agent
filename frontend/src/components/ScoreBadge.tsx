/*
 * Farbcodiertes Badge für den Fit-Score.
 *
 * Farbstufen bewusst als Design-Tokens (siehe index.css @theme):
 *  - score-high  ab 0.7  — deutlich passende Stellen
 *  - score-mid   0.4-0.7 — Grenzfälle, näher anschauen
 *  - score-low   < 0.4   — schwacher Match, meist Filterrauschen
 *
 * Score wird immer als "0.72" (zwei Nachkommastellen) formatiert —
 * konsistenter Look, auch wenn das Backend mal 0.7 oder 0.7345 liefert.
 */

interface ScoreBadgeProps {
  score: number;
}

function scoreTone(score: number): "high" | "mid" | "low" {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "mid";
  return "low";
}

const toneStyles: Record<
  "high" | "mid" | "low",
  { bg: string; text: string; label: string }
> = {
  high: {
    bg: "bg-[color:var(--color-score-high)]/20",
    text: "text-[color:var(--color-score-high)]",
    label: "Starker Match",
  },
  mid: {
    bg: "bg-[color:var(--color-score-mid)]/20",
    text: "text-[color:var(--color-score-mid)]",
    label: "Grenzfall",
  },
  low: {
    bg: "bg-[color:var(--color-score-low)]/20",
    text: "text-[color:var(--color-score-low)]",
    label: "Schwach",
  },
};

export function ScoreBadge({ score }: ScoreBadgeProps) {
  const tone = scoreTone(score);
  const styles = toneStyles[tone];
  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${styles.bg} ${styles.text}`}
      title={styles.label}
    >
      <span className="font-mono tabular-nums">{score.toFixed(2)}</span>
      <span className="text-xs opacity-75">{styles.label}</span>
    </div>
  );
}
