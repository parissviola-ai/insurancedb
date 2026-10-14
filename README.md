# Fern & Moss Plan Finder

A simple local insurance-plan lookup dashboard using Python 3.12+ and SQLite. No external packages, demo records, portal passwords, or patient identifiers are required.

## Run

From `/workspace/fernandmoss`:

```sh
python3 app.py
```

The server binds to loopback on port 8000. The database is initialized automatically and starts empty. A shared deployment requires a production web server, HTTPS, and access controls; this local development server is not a public hosting solution.

## Search

Filter by ZIP, state, year, county, line of business, and optional exact carrier name. Enter one medication or provider per line. Search finds candidate source records by text; it does not establish exact medication equivalence or provider identity. Missing records remain unverified. Coverage and costs require confirmation for the exact plan, drug strength/form, pharmacy, network, and provider location. Medigap does not provide standalone prescription coverage.

## Carrier portals

The dashboard opens the Spark Agent Hub supplied by the project owner in a separate tab. Sign in on the official site. The dashboard does not capture credentials, share sessions, or automatically read portal data. Direct carrier portal URLs require confirmation. Automated imports from authenticated portals require a supported API or other explicitly authorized integration. Downloaded official documents can support manual imports without integration.

## Import verified data

Run `python3 app.py --import-json /path/to/verified-plans.json`.

The JSON root must contain a `plans` array. Every plan requires `id`, `carrier`, `name`, `year` (integer), `state`, `county`, `zip` (five-digit string), `business`, `source_url` (public HTTPS URL), and `verified_on` (YYYY-MM-DD). Optional fields: `premium`, `benefits`, and `coverage` array.

Use one record per plan/service-area ZIP and county, with a stable unique `id` incorporating official plan ID, year, and service area. Supported business values: Medicare Advantage, Part D, Medigap, ACA. Supported states: NC, SC, GA, FL, AL, TN, VA, KY, LA, TX, OH, PA, DE, MI, NY.

Each coverage record requires `kind` (medication or provider), `name`, `status` (covered, restricted, not covered, unverified), `source_url`, and `verified_on`. Optional fields: `detail`, `restrictions`. Include medication strength/form or provider office/network in `detail`, and all known coverage conditions in `restrictions`.

Imports are transactional. Reimporting a plan replaces its coverage records. Source attribution is required; the importer cannot independently establish that a document supports a coverage claim. Review each source before importing. Do not use earlier-year records as confirmed 2027 data. Only import data you are permitted to use and redistribute. No official data is included yet.

SQLite files stay out of Git. Code, schema, and documentation can be published; private customer data and portal credentials must never be committed. Queries are not logged by this server.

## Validate

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

Tests use isolated temporary fixtures; those records never populate the application database.

## Live Devoted connection and official documents

Before starting the dashboard, run `python3 sync_devoted.py`. This needs `pdftotext` (Poppler utilities), Python 3.12+, and HTTPS access to `www.devoted.com`, `assets.devoted.com`, and `fhir.devoted.com`. The sync imports official 2027 NC plan service areas, ZIP/county mappings, document links, PDF text, retrieval timestamps, and PDF SHA-256 digests into the ignored SQLite database. It replaces the previous snapshot in one transaction only after all downloads and text extraction succeed. Rerun it to refresh; if refresh fails, the previous snapshot remains available with its retrieval date. No credentials or demo records are used.

Select “Live Devoted API · North Carolina” in the dashboard. ZIP resolves to county using the same public site data as Devoted's plan finder. If multiple NC counties match, select the member's county and search again. County codes come directly from Devoted (SSA county codes, not FIPS codes). The connector joins the selected county's 2027 plan record locators to official FHIR CMS plan identifiers. Unknown ZIPs, unserved counties, and mismatched years do not fall back to statewide results. Other states and 2026 are not yet supported in this connector.

This website mapping is public page data, not a documented stable API. The importer requires its expected structure and refuses incomplete imports. Site changes require checking and updating the importer. Eligibility, special-needs requirements, and enrollment rules still need confirmation even for a plan listed in a county.

Plan results include a premium and benefit excerpt when the Summary of Benefits contains the expected heading, direct official PDF links, and expandable imported text for the Summary of Benefits, Evidence of Coverage, and formulary where available. Text extraction can disrupt tables and omit nontext content; the original PDF governs. Use browser find to search expanded text. Benefit excerpts do not include all coverage conditions. A missing premium remains unverified rather than zero.

Medication searches return up to five literal text excerpts per formulary with PDF page citations. These are explicitly unverified candidate matches, not structured coverage decisions. Read strength/form, tier, PA/ST/QL restrictions, and document legends in the original. A missing match does not mean a drug is excluded. MA-only plans may have no formulary. General document matches can include indexes and disclaimers.

The public FHIR connector verifies TLS, follows bounded pagination restricted to the official host, and caches responses in memory for five minutes. API errors remain errors. Provider matching uses Practitioner → PractitionerRole → Location and explicit plan network references, active role status, and applicable year. Search by first/last name or NPI and check office locations. The member's home ZIP no longer restricts provider office locations; providers may be elsewhere in NC. An optional API `provider_zip` filter can narrow offices. Facility/pharmacy organization searches are not implemented. Partial searches are labeled.

Validation in the current environment: 37 2027 NC plans and 77 distinct documents imported. ZIP 28202 / Mecklenburg and 28697 / Wilkes each return 12 plans; 27601 / Wake returns none in the published mapping; 27344 requires county selection. The SQLite snapshot is local and ignored by Git; a new checkout needs sync, while a published environment snapshot may retain it. No public application hosting is configured.
