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

## Medication tier costs

Medication candidate matches include the plan-listed 30-day network-retail initial-coverage copay or coinsurance when the Summary of Benefits explicitly supports that table. The parser verifies the retail/mail-order header and extracts the first (retail) column, never the mail-order amount. Costs are linked to their plan's benefit PDF page and exported with assumptions and deductible conditions. Unsupported tables remain unverified; the MA-only plan has no included Part D schedule.

These are standard tier schedules without Extra Help, not personalized pharmacy quotes or coverage confirmations. They assume the exact matched drug is covered and any applicable deductible is met; pharmacy participation, actual drug price, and member coverage stage are not verified. Extra Help, covered insulin/vaccine exceptions, and catastrophic coverage can change costs. Coinsurance remains a percentage, never an invented dollar estimate. No price total is calculated and prescription cost is not part of benefit ranking.

## Medication picker

The static dashboard replaces multiline entry with a local autocomplete picker. Type at least two characters, choose a complete formulary entry (including form), select a strength from that entry when available, and Add medication. Selections remain in browser memory and can be removed individually; maximum 10, with duplicates blocked. Keyboard arrows and Enter select suggestions. Combination products remain distinct from standalone medications. Suggested entries use exact source-row matching per plan, rather than substring matching; grouped strengths remain in source descriptions and the chosen strength is recorded separately. Other plans with differently formatted rows can remain unverified rather than inferred equivalent.

Add manually supports missing catalog entries and retains unverified text matching. Suggestions use only imported Devoted formularies, not a complete medication catalog, and never imply coverage. Unadded text blocks search so a medication is not silently omitted. Selected entries/strengths and manual status appear in the Excel intake and coverage review. No browser storage or remote suggestion requests are used. Original drug restrictions and cost-sharing review requirements remain.

## Provider picker

The static dashboard queries Devoted's public Practitioner directory after at least three name characters or a complete ten-digit NPI, with a 600ms debounce and cancellation of superseded searches. Suggestions show provider names, NPIs, specialty display text (or source taxonomy codes when no readable specialty is supplied), and active 2027 North Carolina office locations. Suggestions are limited; narrow by full name or NPI. Facility and pharmacy organization selection is not supported yet.

Selecting an office adds a provider to a removable list, maximum three. Subsequent plan checks use that exact Practitioner ID and Location ID, with active year-specific PractitionerRole and matching plan network references. A different office or network cannot satisfy the check. Selections are not coverage confirmations. Manual name/NPI entry remains unverified and uses the previous directory search behavior. Unadded provider text blocks search to avoid silently omitting it. Selected identities and office addresses appear in Excel. Names/NPIs are sent to the public directory for lookup, never stored in the database or browser storage. Responses are cached in memory for five minutes. Browser end-to-end validation uses verified curl transport because test Chromium does not trust the environment proxy certificate; no TLS verification is disabled. Run `node tests/provider.mjs` for identity/location/network isolation.

## Facilities and transportation

The directory picker has Individual provider and Facility / hospital / clinic search modes. Facility suggestions search Organization and resolve active 2027 OrganizationAffiliation records to specific NC Location IDs. Plan checks require the selected organization, exact location, year, and explicit network match; they do not establish participation of all clinicians at that facility. Public directory phone numbers appear when provided, in selections and Excel. Manual facility entries remain unverified. Provider/facility selections share the three-item limit. Coverage review includes a blank follow-up call notes column for offline completion. Test the facility branch with `node tests/facility.mjs`.

Transportation priority favors more explicitly covered free one-way rides per year. Missing data stays unknown. An explicit “Transportation Not covered” becomes zero, with a source page citation. All 37 current Devoted NC Summary of Benefits documents explicitly list this benefit as not covered; separate transportation programs are not inferred. The parser accepts positive counts only when free copay and yearly one-way trip units are explicit. Rides, source conditions, and priority labels are included in Excel.

## Expansion to all 15 target states

The primary static dashboard now covers Devoted's published 2027 plans in NC, SC, GA, FL, AL, TN, VA, KY, LA, TX, OH, PA, DE, MI, and NY: 442 plans, 14,582 ZIP mappings, and 447 distinct imported benefit/formulary documents. County codes determine plan states and service areas; website plan identifiers are matched to active 2027 FHIR CMS plan IDs. Provider/facility suggestions and plan checks use the selected state, and state changes clear selected providers/facilities and cancel pending checks. Excel records the selected state. The initial NC-only implementation notes above describe the pilot; this expansion supersedes those static-dashboard limits. The legacy Python app.py lookup remains an NC development prototype.

Evidence of Coverage links are preserved at their official source; new EOC PDFs are not bulk-downloaded or copied to GitHub. Summary of Benefits and formulary PDF text are downloaded for extraction. Existing downloaded documents are reused with original retrieval dates. Use `python3 sync_devoted.py --refresh` to redownload documents at unchanged URLs before `python3 export_static.py`, then review, test, and commit/push updated JSON. The site mapping is refreshed on each sync. Source amount extraction is conservative: unsupported/conditional schedules (including Medicaid-dependent unlimited rides) remain unverified and unranked where required. Standard retail drug schedules are available for 434 plans; missing ones are not given assumed costs.

Browser smoke tests exercised county lookup and comparison in all 15 states, state isolation, and Excel state export. Test data includes no customer records. No appointment status filters are used. Published data is a dated snapshot, not a promise of eligibility or coverage.

Provider/facility typeahead now starts with the first name letter and refreshes after a 300ms debounce. NPIs require all ten digits. Broad searches remain limited and prompt users to keep typing. Public FHIR reverse-reference location/state filters are applied to initial candidate queries, with explicit location-state checks retained. Superseded requests are canceled; only the current query can populate suggestions. Live state-filter queries were verified against the official API, and first/subsequent-letter UI behavior was verified in browser tests.

Provider/facility suggestions now wait for a completed first word: type a name word followed by a space. After that, suggestions refresh as typing continues with a 300ms delay. A complete ten-digit NPI bypasses the word requirement. Manual entry still works without a trailing space. This supersedes the earlier first-letter trigger.

Directory reliability: exact NPI suggestion queries skip the expensive reverse-reference state join because NPIs identify unique records; retrieved offices still require the selected state. Name suggestions retain state filters. Each verified HTTPS directory request (including body read) has a 20-second timeout, preserves user cancellation, and failed suggestions expose a Retry lookup button without discarding input. No retry invents a coverage result. A missing ZIP/state prompts the user to enter ZIP first, rather than making an invalid state query. Run `node tests/directory-timeout.mjs` for timeout classification; UI retry/recovery has been browser tested. The root cause of the reported intermittent client failure was not established.

Name matching preserves compound surnames: “Roberto Rivera Cordero” searches given Roberto and family Rivera Cordero rather than assuming Cordero is the complete surname. If a multiword compound-family search has no matches, it tries first given name plus final surname to accommodate an entered middle name. Suggestions remain candidates with NPI/office disambiguation; neither a full name nor an NPI is mandatory. Both Roberto Rivera and Roberto Rivera Cordero were verified to return NPI 1457924003 from the official API.

When first-name plus surname-prefix searches find no candidates, a surname-fragment fallback searches the first given name plus a family-name contains filter. This permits “Roberto Cordero” to find “Roberto Rivera Cordero” without knowing the omitted surname word. Complete names, NPIs and office addresses remain visible for disambiguation. This exact case was verified against Devoted's official API and the name-matching tests.

Provider surname fragments now use the FHIR family-name contains filter from the initial multiword suggestion query. “Roberto Cor” can therefore include both Corvo-Bequer and Rivera Cordero; completing “Roberto Cordero” retains the intended match. Suggestions are candidates, not identity or coverage decisions. Both searches were verified in a browser against actual directory data using verified TLS transport. The index, app, provider-picker, and provider module release URLs must be updated together so an old cached picker cannot retain outdated matching logic. Static tests enforce consistent directory module versions.

Directory diagnostics distinguish HTTP status errors, browser connection failures, unreadable replies, and timeouts without logging search terms. Provider suggestions preserve successful offices when another role/location request fails, mark results incomplete, and offer retry. No missing or failed record establishes exclusion. The exact strings Roberto Cor, Roberto Cord, and Roberto Cordero were browser-tested using live API responses through verified TLS transport. The user's intermittent native-browser failure has not been reproduced; updated diagnostic messages are intended to identify its cause if it recurs.

### Wellcare initial import

The carrier selector includes one source-reviewed 2027 Wellcare plan: H1914-007, Wellcare Simple Open (PPO), verified for ZIP 28202 in Mecklenburg County, NC. `docs/data/wellcare.json` is loaded separately and survives Devoted export refreshes. This is not a statewide catalog. Other ZIPs show the limited scope rather than inferred availability. Only standalone atorvastatin and amlodipine/atorvastatin formulary rows are imported; other drugs remain unverified. The $17 monthly Spendables allowance is shared across OTC, dental, vision and hearing and is represented as $51 quarterly for the existing comparison model. Advanced hearing copays are unverified, rather than inferred from an allowance. Wellcare provider suggestions and checks do not query Devoted: manual entries remain unverified and link to Wellcare's official shopping/directory flow. Source URLs, document hashes, retrieval dates and limitations are retained in the data.

### Wellcare CMS inventory and network candidates

`sync_wellcare_catalog.py` joins the CMS CY2027 Landscape CSV archive to a captured, dated Wellcare state/product-options JSON snapshot. Run `python3 sync_wellcare_catalog.py --landscape /path/cms.zip --network-options /path/network-options.json --out /path/output`. Downloads should use the official CMS source linked by the script; the directory capture must use supported access. This utility never stores credentials. It exports a county availability CSV and a JSON catalog with contract, PBP, segment, state, category, sanctions and exact directory-name/contract candidates. Candidates remain unverified until confirmed by plan selection. No fuzzy match or network participation is assumed. County names are provided by this Landscape release, not county FIPS; PDP “All Counties” is state-wide. These research exports are separate from the current dashboard's reviewed benefits import. The September 2026 CMS release is subject to change and excludes some plan categories described in its README.

### Wellcare North Carolina expansion (supersedes the single-ZIP pilot)

The public dashboard imports all seven Wellcare 2027 NC Medicare Advantage plans in the CMS September 2026 Landscape release, including three D-SNP plans hidden by default and one MA-only plan. County names are matched to the existing ZIP lookup's county codes; the union of plan service areas contains 74 counties. ZIPs missing from the existing lookup require explicit NC/county confirmation, remain labeled unverified for the ZIP relationship, and preserve that limitation in Excel. Four distinct formularies provide extracted candidate rows with PDF pages and captured restrictions. Preferred retail 30-day initial-stage cost schedules and supplemental conditions remain source-linked. Shared Spendables amounts are converted to quarterly/annual equivalents for comparison, with their shared uses preserved in both dashboard and Excel. Hearing allowances are not treated as Advanced hearing copays. Each plan links to its selected 2027 official Wellcare directory product network. This does not configure automated provider checks or infer FHIR Organization IDs; provider entries remain unverified in this dashboard. No website API key is included.

For refreshes, first obtain a current catalog using `sync_wellcare_catalog.py`. Run `python3 fetch_wellcare_nc.py --cache /tmp/wellcare-nc-source` to retrieve the official shopping documents, then `python3 import_wellcare_nc.py --source-manifest /tmp/wellcare-nc-source/manifest.json --catalog /path/wellcare-2027-catalog.json`. PDFs/text stay in the cache. The factual static output stays separate from Devoted exports. Changes to source layout or the expected seven plans require review before publication.

### Carrier setup tracker

`docs/status.html` provides a searchable, nontechnical setup tracker linked from the dashboard footer. Its single source is `docs/data/carrier-status.json`. Update this file after verified integration changes, separating researched inventory from published dashboard data, source candidates from confirmed connections, and outstanding access from successful tests. Do not include appointment notes, credentials, candidate information, or individual provider records. Track product scope, availability, benefits, medication data, provider searches, connection status, next steps and official source links. Dates reflect the status review, not freshness of every carrier document.
