# JobSpy — Parameter & Verhalten (Rechercheergebnisse)

Notizen aus der praktischen Arbeit mit python-jobspy, relevant für den
Filter-Node (M2) und die Bewertung.

## Pflichtparameter

| Parameter        | Typ   | Bedeutung                                                                                                                   |
|------------------|-------|-----------------------------------------------------------------------------------------------------------------------------|
| `country_indeed` | `str` | Exakter englischer Ländername (z.B. `"Germany"`). Bestimmt die regionale Indeed-Domain (z.B. indeed.de). **Pflicht für Indeed & Glassdoor.** |
| `location`       | `str` | Stadt oder Bundesland. Grenzt *innerhalb* des per `country_indeed` gewählten Landes ein — legt das Land **nicht** selbst fest. |

**Wichtig:** Ohne `country_indeed` liefert JobSpy US-Ergebnisse, auch wenn `location="Hamburg"` gesetzt ist.

## Plattform-Zuverlässigkeit

| Plattform  | Zuverlässigkeit | Anmerkung                                                                                   |
|------------|-----------------|----------------------------------------------------------------------------------------------|
| Indeed     | Hoch            | Kein Rate-Limiting beobachtet. Standardwahl in unserem Server (`site_names=["indeed"]`).    |
| LinkedIn   | Mittel          | Rate-Limiting ab ca. der 10. Ergebnisseite pro IP. Proxies praktisch Pflicht für größere Abfragen — aktuell nicht genutzt. |

Ergebnisse pro Suche pro Plattform: gedeckelt bei ca. 1.000.

## Indeed: Filter-Gruppen-Einschränkung

Pro Suche ist nur **eine** der folgenden Gruppen nutzbar — Gruppen sind nicht kombinierbar:

| Gruppe | Parameter              |
|--------|------------------------|
| 1      | `hours_old`            |
| 2      | `job_type`, `is_remote` |
| 3      | `easy_apply`           |

Werden Filter aus mehreren Gruppen gleichzeitig übergeben, wendet JobSpy nur eine Gruppe an (welche, ist nicht dokumentiert). **Relevant für den Filter-Node:** nicht stillschweigend Filter verlieren.

## Feldqualität — wichtig für den Filter-Node

| Feld        | Problem                                                                 | Konsequenz                                                                                     |
|-------------|-------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| `job_type`  | Häufig `null`, auch wenn der Typ im Freitext steht (beobachtet bei BCG, Thoughtworks, Fuse AI in Hamburg-Suchen). | Filter-Node darf sich **nicht** allein auf dieses Feld verlassen — Text-Matching in `title`/`description` als Fallback nötig. |
| `is_remote` | Nicht immer korrekt. Gegenbeispiel: Anzeige nennt explizit "Hybrid (2-3 days/week onsite)", Feld steht trotzdem auf `true`. | Nicht blind für einen "nur Remote"-Filter vertrauen.                                          |
| `salary` / `min_amount` / `max_amount` | Oft `null`, auch bei ansonsten vollständigen Anzeigen. `salary_source` unterscheidet `"direct_data"` (strukturiert von der Plattform) vs. `"description"` (aus Freitext geparst). | Gehaltsfilter nur als weicher Hinweis, nicht als hartes Ausschlusskriterium.                  |

## Rückgabeformat

`scrape_jobs()` gibt ein **Pandas DataFrame** zurück, kein JSON oder Liste.

### Felder (plattformübergreifend)

`title`, `company`, `company_url`, `job_url`, `job_url_direct`, `location` (country/city/state),
`is_remote`, `description`, `job_type`, `date_posted`, `emails`, `job_function`,
`interval`, `min_amount`, `max_amount`, `currency`, `salary_source`

### Felder (Indeed-spezifisch)

`job_level`, `company_industry`, `company_country`, `company_addresses`,
`company_employees_label`, `company_revenue_label`, `company_description`, `company_logo`

### JSON-Export

`date_posted` enthält Python `date`-Objekte — diese sind nicht nativ JSON-serialisierbar.
Für den Export immer:

```python
df.to_json(orient="records", date_format="iso", force_ascii=False)
```

Liefert `date_posted` als ISO-Datetime-String (z.B. `"2024-01-15T00:00:00.000"`).
Siehe `mcp_servers/jobspy_server/server.py`.

## Quelle

python-jobspy (speedyapply/JobSpy), aktiv gepflegt:
https://github.com/speedyapply/JobSpy
