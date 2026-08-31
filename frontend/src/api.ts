/*
 * Zentrale API-Anbindung an das FastAPI-Backend.
 *
 * Alle HTTP-Calls laufen ausschließlich über die Wrapper-Funktionen
 * hier — keine fetch()-Aufrufe direkt in Komponenten. Das hat zwei
 * Gründe:
 *  1. Ein zentraler Ort für Base-URL, Header und Fehlerbehandlung.
 *  2. Die TypeScript-Interfaces bilden die Backend-Pydantic-Schemas
 *     1:1 ab — spätere Änderungen im Backend fallen hier zuerst auf,
 *     nicht verstreut über zehn Komponenten.
 */

// Hardcoded im Dev — später via VITE_API_BASE_URL, wenn produktiv
// deployed wird (Cloud Run-URL, hinter Custom Domain etc.)
const API_BASE_URL = "http://localhost:8000";

/* ------------------------------------------------------------------ */
/* Typen — spiegeln src/api/schemas.py                                */
/* ------------------------------------------------------------------ */

// GET /jobs Response-Element (flach, siehe schemas.py::JobResponse)
export interface Job {
  id: number;
  external_id: string;
  title: string;
  company: string;
  location: string;
  job_url: string;
  job_type: string | null;
  is_remote: boolean;
  date_posted: string | null;
  min_amount: number | null;
  max_amount: number | null;
  site: string;
  found_at: string;
  fit_score: number;
  reasoning: string;
  matched_skills: string[];
  missing_skills: string[];
  status: string;
}

// GET /jobs Query-Parameter
export interface JobsQuery {
  min_score?: number;
  status?: string;
  limit?: number;
  offset?: number;
}

// GET/PUT /filter-rules Body
export interface FilterRules {
  title_blacklist: string[];
  max_experience_years: number;
  description_blacklist: string[];
}

// POST /search-runs Request-Body
export interface SearchRunRequest {
  search_term: string;
  location: string;
}

// POST /search-runs Response
export interface SearchRunResult {
  raw_jobs_count: number;
  filtered_jobs_count: number;
  rejected_jobs_count: number;
  evaluated_jobs_count: number;
  errors: string[];
}

/* ------------------------------------------------------------------ */
/* Interner fetch-Wrapper                                             */
/* ------------------------------------------------------------------ */

// Kleiner Wrapper um fetch: setzt JSON-Header, prüft ok, wirft mit
// aussagekräftiger Message. Generic <T> = erwarteter Response-Typ.
async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    // FastAPI-Fehlerdetails aus dem Body ziehen, wenn vorhanden —
    // sonst reicht der HTTP-Status für die Anzeige im UI.
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      /* Body war kein JSON — ignorieren, statusText nutzen */
    }
    throw new Error(`${response.status}: ${detail}`);
  }

  return response.json() as Promise<T>;
}

/* ------------------------------------------------------------------ */
/* Öffentliche Wrapper-Funktionen                                     */
/* ------------------------------------------------------------------ */

// GET /jobs mit optionalen Filtern — baut den Query-String selbst,
// damit undefined-Werte gar nicht erst als "min_score=undefined"
// im URL landen
export async function getJobs(query: JobsQuery = {}): Promise<Job[]> {
  const params = new URLSearchParams();
  if (query.min_score !== undefined) {
    params.set("min_score", String(query.min_score));
  }
  if (query.status !== undefined && query.status !== "") {
    params.set("status", query.status);
  }
  if (query.limit !== undefined) {
    params.set("limit", String(query.limit));
  }
  if (query.offset !== undefined) {
    params.set("offset", String(query.offset));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<Job[]>(`/jobs${suffix}`);
}

// PATCH /jobs/{id}/status — gibt {job_id, status} zurück
export async function patchJobStatus(
  jobId: number,
  status: string,
): Promise<{ job_id: number; status: string }> {
  return request(`/jobs/${jobId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

// GET /filter-rules
export async function getFilterRules(): Promise<FilterRules> {
  return request<FilterRules>("/filter-rules");
}

// PUT /filter-rules — Response ist wieder das Regelwerk
export async function putFilterRules(
  rules: FilterRules,
): Promise<FilterRules> {
  return request<FilterRules>("/filter-rules", {
    method: "PUT",
    body: JSON.stringify(rules),
  });
}

// POST /search-runs — blockiert bis der LangGraph-Lauf fertig ist
// (kann laut Backend-Kommentar 30 s+ dauern)
export async function postSearchRun(
  payload: SearchRunRequest,
): Promise<SearchRunResult> {
  return request<SearchRunResult>("/search-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
