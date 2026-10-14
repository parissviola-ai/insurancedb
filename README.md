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

## Static dashboard / GitHub Pages

The nontechnical dashboard is in `docs/index.html`. Its relative links load committed JSON files from `docs/data/`; there is no Python server in production. Official PDFs remain linked at Devoted rather than copied into GitHub. Exported data contains plan identifiers, premiums, service areas, source links, and factual candidate drug-table rows, not complete PDF prose. No customer data or credentials are included.

Refresh with `python3 sync_devoted.py` followed by `python3 export_static.py`, review the data changes, run tests, and commit/push the resulting files. Refresh is separate from user searches. Users can search medications locally; provider name/NPI searches are sent to Devoted's public FHIR service. Live provider failures show official directory links and never imply exclusion. The local static files must be served over HTTP(S), not opened with file://, because browsers restrict loading JSON that way.

In GitHub repository Settings → Pages, choose “Deploy from a branch”, branch `plan-finder`, folder `/docs`, and save. For a private repository, Pages availability depends on the account plan; making it public enables free Pages hosting and exposes all committed repository contents. Do not change visibility without the owner's decision. The integration in this session returned HTTP 403 for the Pages settings API, so publication must be enabled by the owner in GitHub. Do not claim the site is live until deployment completes and its URL is verified.

Validation: static browser flows tested under the GitHub Pages origin with routed local assets: 12 plans for 28202, county selection for 27344, no plans in Chatham County, drug candidates, network-matched providers, and blocked-provider fallback. Devoted returned Access-Control-Allow-Origin for `https://parissviola-ai.github.io`. Test Chromium did not trust the environment's proxy certificate; API requests in the successful browser test were forwarded through curl with normal TLS verification and actual CORS headers preserved. Native browser connectivity still needs verification on the published site; no TLS verification was disabled.

## Benefit comparison and ranking

The static dashboard displays plans side by side in a comparison table. Dental, OTC, and lower-premium priorities range from 0 (ignore) to 5. Scores update locally without repeating provider searches. Monthly plan premium, annual dental amount, and quarterly OTC allowance are extracted conservatively from explicit Summary of Benefits text, with PDF page citations and dental reimbursement/network conditions. Missing amounts remain unverified; missing OTC text is never interpreted as a zero allowance. Conditional food/home benefits are not substituted for OTC.

Only plans with numeric values for every selected priority are scored. Each selected amount is normalized within that comparable group; higher dental/OTC and lower premium are favored, equal values tie, and weighted results are scaled to 100. Annual OTC equivalents assume four quarters, not rollover. Scores are relative benefit matches, not cost estimates or overall coverage recommendations. Drug/provider results and enrollment eligibility are separate review requirements and never inferred from dollar allowances. The premium metric excludes Part B and other costs. A larger dental allowance can still reimburse less for a procedure; the table displays these conditions and links to the original.

Special-needs plans are hidden by default; the optional checkbox includes them for manual comparison, but never automatic ranking. MA-only plans are not scored if medications are entered because they lack included Part D coverage. Zero selected priorities produces no score. Unranked plans remain available for review. Detailed plan cards expand from the comparison table. Refreshing via `python3 export_static.py` regenerates metrics from the local official document snapshot. Run `node tests/ranking.mjs` in addition to the Python suite.

## Excel review export

“Export comparison to Excel” downloads an XLSX workbook generated entirely in the browser. Sheets include the search intake and priorities, all displayed plan comparisons and source URLs, and medication/provider candidate evidence available at export time. Names, additional notes, reviewer identity, and reviewer decisions are blank fields filled in offline. No candidate name or notes are collected by the dashboard; no export is uploaded or saved in the application database. Live provider requests still go to Devoted as described above. If exported before lookup completion, provider checks remain marked pending/unavailable. Exported ranking is a snapshot of the current priorities; review requirements stay explicit. Values are written as inline strings, preventing user-entered values from becoming Excel formulas. The workbook stays with the person downloading it; share through their chosen channel.

Additional priorities under “More priorities” are medical in-network out-of-pocket maximum (lower), specialist office copay (lower), modeled hospital cost for one 7-day in-network admission (lower), yearly eyewear allowance (higher), and Advanced hearing-aid copay per aid (lower). These start at zero. Hospital scoring is available only when an explicit per-stay copay or initial daily copay followed by $0 days supports the model; unsupported schedules stay unknown. Hearing notes include the separate Premium option copay and vendor requirements. Medical maximum excludes Part D and other noncounting services. Amounts have source-page links and conditions in both dashboard and Excel. Prescription costs remain unscored pending exact drug/pharmacy verification. The checkbox reads “Show special-needs plans — eligibility required.” Eligibility is still a separate requirement.

Priority controls now use High, Medium, Low, and Not a priority instead of sliders. Internal weights are 5, 3, 1, and 0 respectively; the workbook exports the readable labels. Dental/OTC default to Medium, lower premium to Low, and additional priorities to Not a priority. Changing a choice immediately re-ranks the current comparison.
