from typing import Optional

from fastmcp import FastMCP
from jobspy import scrape_jobs

# MCP-Server-Instanz
mcp = FastMCP("jobspy")


@mcp.tool()
def search_jobs(
    search_term: str,
    location: str,
    site_names: list[str] = ["indeed"],
    results_wanted: int = 15,
    job_type: Optional[str] = None,
    is_remote: bool = False,
    country_indeed: str = "Germany",
) -> str:
    """Durchsucht Jobportale (Indeed, LinkedIn, Glassdoor) nach Stellenanzeigen.

    Gibt die gefundenen Jobs als JSON-Array zurück. Jedes Element enthält
    Felder wie title, company, location, job_url, description, date_posted u.a.

    job_type akzeptiert: fulltime, parttime, internship, contract (oder None).

    country_indeed legt fest, welche Indeed-Länderdomain durchsucht wird
    (z.B. "Germany" → indeed.de, "USA" → indeed.com). Der location-Parameter
    grenzt nur innerhalb dieses Landes ein — er bestimmt nicht das Land selbst.
    """
    df = scrape_jobs(
        site_name=site_names,
        search_term=search_term,
        location=location,
        results_wanted=results_wanted,
        job_type=job_type,
        is_remote=is_remote,
        country_indeed=country_indeed,
    )

    # Leere Ergebnisse sauber abfangen
    if df is None or df.empty:
        return "[]"

    # date_posted enthält Python date-Objekte — ISO-Format für JSON-Kompatibilität
    return df.to_json(orient="records", date_format="iso", force_ascii=False)


if __name__ == "__main__":
    mcp.run()
