/*
 * App-Shell: einfache Tab-Navigation zwischen den drei Bereichen.
 *
 * refreshToken: einfache "Neu-laden-Signal"-Nummer. Der SearchRunPanel
 * ruft nach Abschluss onCompleted() → App inkrementiert die Zahl →
 * Dashboard hat die neue Zahl als Prop → sein useEffect löst neues
 * getJobs() aus. Bewusst kein globaler Store, für drei State-Stücke
 * unnötiger Overhead.
 */

import { useState } from "react";
import { Dashboard } from "./components/Dashboard";
import { FilterRulesPanel } from "./components/FilterRulesPanel";
import { SearchRunPanel } from "./components/SearchRunPanel";

type Tab = "dashboard" | "filter-rules" | "search-run";

const TABS: { id: Tab; label: string }[] = [
  { id: "dashboard", label: "Jobs" },
  { id: "search-run", label: "Neuer Suchlauf" },
  { id: "filter-rules", label: "Filter-Regeln" },
];

function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [refreshToken, setRefreshToken] = useState(0);

  function bumpRefresh() {
    setRefreshToken((n) => n + 1);
    // Nach dem Suchlauf direkt zurück auf die Job-Liste — der Nutzer
    // will die neuen Ergebnisse sehen
    setTab("dashboard");
  }

  return (
    <div className="min-h-screen bg-[color:var(--color-surface)] text-[color:var(--color-text-primary)]">
      <header className="border-b border-[color:var(--color-surface-border)] bg-[color:var(--color-surface-raised)]/60 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              Job Search Agent
            </h1>
            <p className="text-xs text-[color:var(--color-text-muted)]">
              Suchen · Filtern · Bewerten
            </p>
          </div>
          <nav className="flex gap-1">
            {TABS.map((entry) => {
              const active = tab === entry.id;
              return (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => setTab(entry.id)}
                  className={
                    "rounded-md px-3 py-2 text-sm transition " +
                    (active
                      ? "bg-[color:var(--color-accent-muted)] text-[color:var(--color-accent)]"
                      : "text-[color:var(--color-text-secondary)] hover:text-[color:var(--color-text-primary)]")
                  }
                >
                  {entry.label}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        {tab === "dashboard" && <Dashboard refreshToken={refreshToken} />}
        {tab === "filter-rules" && <FilterRulesPanel />}
        {tab === "search-run" && (
          <SearchRunPanel onCompleted={bumpRefresh} />
        )}
      </main>
    </div>
  );
}

export default App;
