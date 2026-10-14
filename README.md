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

## Live Devoted connection

Select “Live Devoted API · North Carolina” in the dashboard. The server queries the official public FHIR API at `https://fhir.devoted.com/fhir/`, using TLS verification and a five-minute in-memory response cache. No authentication was needed for tested public resources. API errors display as errors rather than empty successful coverage results.

The connector follows pagination, restricts remote requests to the official FHIR host, and selects active plans explicitly spanning the requested year with NC in their official names. These are state candidates: ZIP/county plan service areas and benefits are not established by these resources. ZIP filters provider office locations only. County inputs do not filter live plan candidates.

Provider searches use Practitioner → PractitionerRole → Location and match the role's explicit network reference against the selected plan's network, with active status and applicable period required. Results are limited to NC locations and the entered office ZIP. Exact identity and current participation still need confirmation. Search up to three provider names at a time; office details should be checked in results rather than appended to the name query. Facility and pharmacy organization searches are not yet implemented. Truncated searches are labeled; missing records remain unverified.

Formulary List and MedicationKnowledge resources exist, but inspected NC lists lack an explicit coverage year and do not establish the connection to all current 2027 plan IDs. Medication coverage therefore remains unverified. Do not use lastUpdated as evidence of a formulary's plan year. No live records are committed to Git or inserted into the local SQLite database by the connector.
