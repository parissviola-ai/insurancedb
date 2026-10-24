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

### HealthSpring 2027 North Carolina pilot

The static dashboard includes HealthSpring (formerly Cigna Medicare) True Choice (PPO), H7849-113-001, for its 11 CMS-confirmed NC counties. ZIP 28262 requires choosing Mecklenburg or Cabarrus. Only this pilot plan is imported; this does not imply other plans or states are unavailable. The official Summary of Benefits, Evidence of Coverage, MAPD formulary 00027063, and NC PPO provider/pharmacy directory are linked. Extracted formulary candidates retain physical PDF page numbers and wrapped restrictions; the two-column parser keeps neighboring drugs separate. Some source names group strengths/forms, so exact prescriptions still require review. Drug costs use preferred network retail, 30-day initial coverage without Extra Help; standard retail Tier 1/Tier 2 are $10/$20 rather than $0/$8. Source conditions and deductible rules are preserved. OTC and routine transportation amounts remain unverified; hearing aids are shown as not covered, never scored as a $0 hearing-aid copay.

Refresh the verified pilot with normal TLS validation and `pdftotext` installed:

```bash
python import_healthspring.py --cache /tmp/healthspring-documents --landscape /tmp/cms-2027-landscape.zip
python -m unittest discover -s tests -v
node tests/healthspring.mjs
node tests/ranking.mjs
```

The official CMS archive is https://www.cms.gov/files/zip/cy2027-landscape-202609-1.zip. The importer checks document year, plan/segment identity, CMS/PDF service-area agreement, source schedules and representative formulary restrictions; it stops on mismatches. `docs/data/healthspring.json` is separate from Devoted and Wellcare data and is not overwritten by their exporters. PDF cache files stay outside Git.

Public HealthSpring FHIR is reachable at `https://data.healthspring.healthlx.com:8003/`. The catalog checked on October 14, 2026 contained 618 plan records with 2025/2026 coverage periods; no 2027 records were found. `docs/healthspring.js` prepares an anonymous read-only exact plan/year lookup and requires a full-year active InsurancePlan with matching CMS segment and network references. It never promotes historical records to 2027 or establishes provider coverage from a plan mapping alone. For this pilot, providers/facilities are added manually and remain unverified, with official directory links and review details in Excel. No provider names or candidate information are sent to the HealthSpring API; only the CMS plan identifier is queried. The supplied NC HMO directory names different plans and is listed in the setup tracker for later expansion.

The HealthSpring search also offers a county-filtered **Official 2027 NC coverage documents** library sourced from the official EOC page. It contains 13 Medicare Advantage plan/segment EOCs with CMS-matched county lists and the shared Assurance Rx Part D EOC. Library links are source documents, not additional ranked results. The zero-segment EOCs sometimes print only contract/PBP; the official filename, matching cover, and CMS segment/county list establish their document linkage. Assurance's regional CMS plan linkage remains pending. Refresh the library with:

```bash
python fetch_healthspring_documents.py --cache /tmp/healthspring-nc-eoc --landscape /tmp/cms-2027-landscape.zip
```

### HealthSpring source library across all 15 target states

The public `healthspring-documents.html` page filters official 2027 EOCs and formulary links by state, county, plan name/CMS ID, and product type. It is linked from the main dashboard. The current collection has 162 state/document entries (146 MA state/plan-segments plus 16 PDP entries), 143 unique EOC PDFs, and six shared formularies containing 15,304 extracted candidate rows. MA formularies are joined by explicit printed CMS applicability IDs and matching state/plan name: 139 MA state/segments match; seven have no included Part D. Shared PDP sources are shown separately without claiming regional CMS linkage. LA, MI, and NY have no HealthSpring MA entries in the reviewed catalog/CMS release, but have Assurance Rx documents. These source counts do not imply full benefit comparisons or provider checks are integrated.

Refresh dependencies in this order:

```bash
python fetch_healthspring_documents.py --cache /tmp/healthspring-eoc --landscape /tmp/cms-2027-landscape.zip
python fetch_healthspring_formularies.py --cache /tmp/healthspring-eoc --landscape /tmp/cms-2027-landscape.zip
```

The EOC collector defaults to all target states, deduplicates PDFs, verifies year/printed plan codes and CMS county lists, and records unresolved download/mapping issues instead of filling gaps. CMS/PDF service areas override website summary metadata only when the printed county list explicitly agrees with CMS; PA H3949-052-000 has this documented metadata discrepancy. Only exact plan/state identities are joined. The six-formulary collection and MA CSV are separate from the NC pilot's comparison dataset; refreshing them does not automatically expand ranked comparisons or drug coverage claims. Source PDFs/text caches remain outside Git. `healthspring-ma-segments.csv` opens in Excel and includes state, segment, county list, source URLs, checks, and conditions. Browser checks cover cross-state isolation, exact segment filters, PDP separation, source notes, downloads, and the existing pilot; Python and year-gating tests remain required.

### HealthSpring NC PPO PDF provider suggestions

Provider/facility suggestions for HealthSpring's NC True Choice pilot now search a local index extracted from the official 2027 NC PPO directory, dated September 23, 2026. Individuals can be searched by name tokens or available NPI; hospital listings include their specific office and phone number. The index is deliberately partial: ambiguous/continuation blocks without a dependable identity are skipped, and HMO/other-state directories and many ancillary facilities/clinics are not indexed. A missing suggestion never establishes exclusion. Selected PDF entries retain office, phone, physical PDF page, and directory date in plan details and Excel. They remain “2027 PDF listing — confirm current participation,” with live API coverage unverified. Only the verified 2027 NC True Choice segment is attached to these candidates; historical plans and other segments receive no inferred match. Provider searches in this mode remain local; the separate plan-network availability request sends only a plan ID.

Rebuild with `python import_healthspring_providers.py --pdf /path/to/provider-pharmacy-directory-north-carolina-ppo.pdf` (requires PyMuPDF). The importer requires the PDF SHA-256 to match the verified pilot's source metadata. Run `node tests/healthspring-providers.mjs` alongside the existing Python and HealthSpring tests. The official HealthSpring EyeMed locator is included in the vision cell, plan details, and Excel review export.

### Regional HMO and other-state PDF directory indexing

`index_healthspring_directories.py` supersedes the NC-only suggestion index. It collects every official 2027 directory listed for the 15 target states, retaining the source's regional boundaries: 38 unique PDFs across 12 MA target states, including HMO, PPO, and the separately named D-SNP directory. LA/MI/NY have no MA directory listed in the reviewed catalog. The official page misspells one Virginia entry as “Virgina”; that explicit catalog label is normalized to VA. All directory dates were extracted. Current indexes contain 561,409 directory/office candidates (providers recur across directories, so these are not unique-provider counts). Extraction remains partial and hospital-focused for facilities; ambiguous blocks and some clinics/ancillary facilities are omitted.

Refresh with `python index_healthspring_directories.py --cache /tmp/healthspring-all-directories` (PyMuPDF and pdftotext required). Each PDF has its own generated JSON index and SHA-256 manifest under `docs/data/healthspring-directories/`; cached indexes are reused only when PDF hashes match. Failed directories remain flagged for review, never silently represented as empty coverage. No failed directories remain in this snapshot. A selected state's directory options come from the official catalog. Representatives choose the regional HMO/PPO source; NC defaults to the already verified True Choice PPO source. Only the selected directory is loaded, with at most three indexes cached in browser memory. Source names/date/page stay attached to selections. Other PDF-to-plan attachments remain unset; matching a directory name/state is not enough to infer coverage for every plan in that state.

The carrier selector now says “HealthSpring (formerly Cigna Medicare)” without “pilot”; the comparison dataset still clearly discloses its current NC True Choice scope. True Choice OTC allowance and annual free routine rides remain unverified because no amount was confirmed in the checked plan sources. They are not stored as zero. Ambulance and transplant travel benefits do not establish an annual routine-ride count. Comparison cells and Excel notes preserve these distinctions.

### Excellus 2027 document integration

`python import_excellus.py --cache /tmp/excellus-cache` rebuilds the three individual
NY plans H3351-028/029/030 (segment 000), the shared formulary candidates and the
partial provider/facility index from official Excellus PDFs and the CMS landscape.
Remove a cached file to retrieve a fresh copy. Source hashes and PDF pages are
retained. Run `node tests/excellus.mjs` after refreshing.

The integration uses dated directory listings, not live network confirmation.
The PDF index has no NPIs; name suggestions and manual entry are available.
Do not infer exclusions from missing extracted records. Where the prepared ZIP
lookup is missing, select NY and confirm the county manually. Optional dental
costs extra and is not scored as a base allowance; OTC remains unverified. Exact
CMS-to-internal-FHIR network mapping is awaiting Excellus support.

### Search all public carrier websites

Run `python3 app.py` and open `http://127.0.0.1:8000/dashboard/` for the current
dashboard with the local backend. The static GitHub Pages dashboard reports that
it is not connected to the private backend; this change does not deploy one.

Enter a ZIP once and click **Search all carrier websites**. A public ZIP lookup
resolves county/state within the existing `app.STATES` list: NC, SC, GA, FL, AL,
TN, VA, KY, LA, TX, OH, PA, DE, MI, NY. Ambiguous ZIPs require county selection;
an existing county selection is reused by exact name after public revalidation.
The public FIPS code is never substituted for Devoted's SSA code.

The backend concurrently queries Aetna, Devoted Health, HealthSpring,
UnitedHealthcare / AARP, Highmark, Highmark Wholecare, Molina and Excellus
BlueCross BlueShield. Highmark/Wholecare share one public shopping request and
are separated by source carrier/contract identity. Former Cigna Medicare is
included under HealthSpring without duplicate plans; separate Cigna commercial
shopping is not connected. Public CareFirst, Medico/Wellabe and Guarantee Trust
Life entries are also checked, but cannot yet supply verified ZIP/year plan lists:
CareFirst's Medicare entry returned a missing-page response during validation;
Medico/Wellabe accepts a ZIP but directs users to an agent; the reviewed GTL
supplement page is a product/agent entry rather than ZIP/year shopping results.
These limitations are explicit per-carrier results, never successful empty searches.

The combined table includes Medicare Advantage and Part D records with official
IDs, source links and actual retrieval timestamps. Premiums stay unverified when
not retrieved. Special-needs listings retain eligibility warnings. Medigap and
supplement quotes are not supplied by the current plan-list connectors, even when
carrier websites advertise those products. Broader product coverage is unfinished.
Selected medications and providers now feed the website result checks described below.
Imported comparisons remain available separately.

`/api/carrier-websites?zip=28202&year=2027` returns one status per requested carrier,
verified plans, location, and `complete: false` while any source cannot complete a
plan search. `checked_at` is set only for successful plan retrieval. Quote/site
checks can supply `source_checked_at`, with `checked_at: null`. Use returned FIPS
county codes on subsequent ambiguous-ZIP requests. `/api/carrier-locations` exposes
the same public ZIP resolution. No request text, secrets or raw upstream errors are
logged or returned. There are no portal logins or stored browser sessions.

Browser setup for Highmark/Wholecare, Molina and Excellus:

```sh
npm install
npx playwright install chromium
python3 app.py
```

A managed runtime can set `SHOPPING_CHROMIUM_PATH` to its installed Chromium.
Only container runtimes requiring it should set `SHOPPING_CHROMIUM_NO_SANDBOX=1`.
TLS verification stays enabled and inherited proxy settings are preserved.
Anonymous browser contexts are isolated and destroyed after each search.
The other plan connectors use Python's standard HTTPS libraries. Each search is
bounded; failures are isolated and successful carrier results are retained.

Live validation October 24, 2026: ZIP 28202 / Mecklenburg NC returned 9 Aetna,
12 Devoted, 7 HealthSpring and 16 UHC MA/Part D plans. ZIP 15222 / Allegheny PA
returned 14 Highmark and 2 Wholecare plans. ZIP 29201 / Richland SC returned one
Molina plan. ZIP 14604 / Monroe NY returned four Excellus MA plans. These are
test locations, not proof of complete inventory in every configured state.
Official public shopping formats can change; unexpected schemas, wrong years,
county mismatches and incomplete lists withhold affected results.

Validation: `python3 -m unittest discover -s tests -v`,
`node --check docs/carrier-websites.js`, `node --check public-shopping.cjs`.
The loopback development server is not a deployed private service; hosted use
still requires HTTPS and access controls. Credentials and private-support files
must stay outside the repository.


### Medication/provider checks in the combined ZIP search

The website result table reuses the existing medication and provider selections.
Its public plan-list backend request still sends location only. Medication matching
runs locally; existing Devoted provider queries use its public directory. No member
identifiers are sent with these requests. Changing selections invalidates previous
website checks.

Prepared data attaches only when carrier, full CMS contract/PBP/segment, state and
year match. There is no plan-name, contract-only, or earlier-year fallback. Medication
results reuse dated Devoted, HealthSpring and Excellus formularies where an exact
mapping exists. The all-state HealthSpring formulary library is also reused through
its explicit CMS segment applicability IDs. Shared PDP documents without confirmed
regional CMS linkage remain unconnected. Matches retain PDF pages, tiers, restrictions
and retrieval dates; they remain candidates requiring exact strength/form, pharmacy
and current coverage review. No new drug cost estimates are calculated.

Devoted provider checks reuse the live directory and exact imported plan-network
mapping. PDF selections from other carriers are not treated as Devoted resource IDs.
HealthSpring/Excellus dated PDF candidates attach only to their explicitly mapped
2027 plans and states; ambiguous identity/office or missing listings remain unverified.
A plan's home ZIP selects its service area; it does not restrict a provider to that
home ZIP. Standalone Part D plans are not treated as medical provider networks.

Automated medication/provider checks for Aetna, Highmark, Wholecare, Molina and UHC,
and for unmatched HealthSpring/Excellus segments, are still not connected. Their
rows say so explicitly and link back to the carrier source for review. A successful
plan-list search is never treated as successful drug coverage or provider participation.

Run `node tests/website-coverage.mjs` plus the existing Python and Node checks.
Browser validation uses fixture directory responses and the prior 44-plan shopping
response to verify selection reuse, per-plan results, stale-result invalidation,
location-only shopping requests and explicit unconnected-source messages.

### Optional Medicare member coverage review

The dashboard links to the member's official Medicare account and the supplied
account-recovery page. These links do not read coverage into the dashboard and do
not collect Medicare/MBI numbers, last names, birthdates or passwords. The recovery
page is not a public enrollment/plan lookup API.

A future Medicare data connection requires an approved CMS Blue Button application,
a private confidential OAuth backend, and the enrollee's Medicare.gov sign-in and
authorization. No CMS application credentials or production approval are configured
here. Do not implement a name/DOB/MBI form as if it can retrieve enrollment through
account recovery. Coverage returned by an approved connection must be evaluated for
what it actually establishes, including applicable dates and exact carrier/plan
identifiers, before attaching any current plan or network claim.

Official references: https://bluebutton.cms.gov/api-documentation/authorization/
and https://bluebutton.cms.gov/production-access/ .


### Free local Mac launcher

See `START-HERE-MAC.txt`. With Python 3.12+ and Node.js 20+ installed, double-click
`Start Plan Finder.command`. `run_local.py` installs the pinned npm dependency and
Chromium on first use, then opens `http://127.0.0.1:8765/dashboard/`. Downloads stay
in ignored `node_modules/` and `.local-cache/` folders inside the application.
The server binds only to loopback; keep Terminal open and press Control+C to stop.
No hosted account, portal credentials or subscription are needed. The local copy
and the GitHub Pages copy are separate; use the local URL for website searches.
`python3 run_local.py --check` validates prerequisite tools without downloading or
starting a server. `--no-browser` suppresses browser opening. The local Content
Security Policy explicitly allows only the existing external provider API origins
needed by the dashboard's connected checks.


### Full comparison features for Search all

The combined website search now shows the same benefit columns and uses the same
priority scoring and XLSX writer as the regular search. It includes local carrier
and product filters, the shared special-needs toggle, expandable plan details,
source-linked benefit amounts and a five-sheet Excel export (intake/priorities,
comparison, coverage review, benefit sources and all carrier statuses). Changing
priorities or display filters does not repeat upstream searches. Coverage results
update in place and exports include the state available at download time; unfinished
checks remain explicitly pending.

Saved benefits attach only to exact carrier/CMS segment/state/year matches. A live
premium takes precedence over an imported premium, while other imported document
amounts retain their own retrieval dates. Public HealthSpring and Connecture responses
can additionally supply explicit in-network annual medical maximums; negative,
missing, nonnumeric and nonfinite values are not amounts. Missing dental, OTC or
other benefits are not filled by inference. Rankings use only comparable medical
plans with every selected amount: special-needs plans are excluded from scoring,
medical-only plans are unranked when medications were requested, and Part D plans
are not ranked against Medicare Advantage plans.

Aetna links now use `step=PlanList`, with ZIP/FIPS/year from the search. Its public
pricing action adds premiums before Extra Help adjustments and explicit in-network
medical maximums only when product identity and contract/PBP/year match the returned
plan. Ambiguous or failed pricing preserves the plan list with an explicit benefit
notice. October 24 validation for ZIP 28262 / Mecklenburg / 2027 returned nine plans
with verified premiums; Eagle H5521-241 returned $0/month and a $7,150 medical maximum.
No county or year is hardcoded to that test case.

Coverage summaries distinguish "Listed in plan network" (selected exact live office),
"Network matches — choose office" (broad search), dated PDF listings/candidates,
formulary matches, "No prescription coverage" (medical-only source) and
"Not checked — connection needed". Evidence and longer restrictions remain under
"Sources and conditions"; they are also retained in Excel. Missing connections do
not imply that a medication or provider is excluded.

HealthSpring details link to its location-specific `/prescriptions` and `/pharmacy`
steps. Both public pages were opened for ZIP 28613 / FIPS 37035. Selections made on
those external pages are not imported into this dashboard; exact pharmacy quotes
are not claimed here. Prices still require the exact product, dose, quantity,
days' supply, pharmacy and coverage-stage assumptions.

Validation: 45 Python tests; all Node checks including
`tests/website-comparison.mjs`; browser checks for ranking/filter changes without
another website request, plan details, special-needs visibility, and the five-sheet
Excel download. The Mac copy must be updated from GitHub and restarted to pick up
these features; an already extracted ZIP does not update itself.


### Aetna and UHC official plan document pulls

`/api/plan-documents` accepts carrier, exact public plan ID, ZIP, county FIPS and
year. It resolves ZIP/county within the existing target states, verifies that the
carrier actually returned that plan for the location/year, and reads its public
plan document catalog. Aetna uses the observed anonymous `getPlanDocuments` action;
UHC uses the observed plan-detail document catalog. No portal credentials, patient
identifiers, or submitted medication lists are involved in document retrieval.

Search all automatically reads Aetna and UHC plan PDFs as soon as plans are retrieved, alongside initial coverage checks. Benefits, rankings, medication candidates and export data update as each plan finishes, with two concurrent document checks and visible progress. Failures stay visible in plan details and do not stop other plans. A per-plan **Pull official PDFs** action and a bulk action remain available for
displayed Aetna/UHC plans. It downloads Summary of Benefits, Evidence of Coverage
and formulary PDFs when available. Other documents (provider directory, vendor
information, enrollment, highlights, ANOC, star ratings, prior authorization, step
therapy and deletions) remain linked with their source dates. Large provider
PDFs are not automatically indexed or treated as current network confirmations.
Online provider/pharmacy tools remain available for manual carrier-site review.

Downloaded PDFs, extracted text, timestamps, page counts and SHA-256 digests stay
in ignored `.local-cache/plan-documents/`. Shared URLs reuse the local cache for
24 hours; per-plan **Refresh official PDFs** forces another download. Only official
HTTPS document paths and bounded PDFs are accepted. PDFs require a matching year;
benefit PDFs require matching CMS identity and cover name. Ambiguous multi-plan
covers, mismatches and conflicting amounts are flagged rather than scored. A shared
formulary's applicability comes from the verified plan's own carrier catalog.

Only explicit compatible amounts/periods enter ranking. The UHC NC-15 example
H5253-117-000 in ZIP 28613 / Catawba returned an annual $1,500 dental maximum from
its EOC, $25 quarterly OTC credit, $35 specialist copay, and a modeled $2,750 7-day
hospital stay from its SB. Its $150 eyewear allowance is every two years; it is
not scored as $150/year. Its hearing allowance is not an Advanced hearing-aid copay.
Aetna H5521-348 in ZIP 28262 also returned matching SB/EOC/formulary documents and
source-cited dental, vision and specialist amounts. These are sample validations,
not evidence that every plan/state's PDF layout has been supported.

Formulary extraction is partial and retains source page, tier and flags. Ingredient
text can find candidates across differing carrier descriptions, but does not establish
exact product/strength/form equivalence, exclusion, or pharmacy cost. New PDF values
and candidate checks update plan details and the five-sheet Excel export. Document
and shopping dates stay separate. Dated directories never become live network claims.

The Mac launcher installs pinned `pypdf` from `requirements-local.txt` into an
app-local Python environment when necessary. It leaves system Python unchanged
and requires no paid service. The source PDF test runs used pypdf 6.21.2. Validation
includes unit tests for plan/year/location binding, PDF URL restrictions, benefit
periods, conflict rejection, wrapped formulary rows, and isolated launcher setup,
plus a browser test of document pulls and comparison/medication updates.

Dental and OTC document parsing recognizes Aetna covered-services annual dental
allowances, CVS quarterly OTC Wallet wording, and UHC EOC quarterly credit rows.
Evidence of Coverage can fill or cross-check OTC as well as dental and medical
maximums; conflicting amounts are withheld. Preventive-only dental coverage and
optional paid dental riders are labeled separately from included annual allowances.
Shared or conditional OTC wallet amounts are disclosed without ranking them as
unrestricted OTC-only credits. Missing OTC amounts are never inferred as zero.
Validation used the 20 nonspecial-needs Aetna/UHC Medicare Advantage plans returned
for 2027 in ZIPs 28262 (Mecklenburg) and 10701 (Westchester), with plan-bound
Summary of Benefits and Evidence of Coverage documents cached privately.

HealthSpring public plan shopping now supplies exact-plan quarterly OTC credits,
single specialist copays, modeled seven-day hospital copays and annual one-way
transportation trips when the response specifies comparable amounts. Daily hospital
ranges must cover every modeled day exactly once, with dollar copays (not percentages).
HealthSpring MA benefit PDFs load automatically alongside Aetna/UHC PDFs. The source
catalog must bind the complete CMS segment and year; where a cover prints only the
contract/PBP, its exact full-segment official catalog filename is also required.
Dental yearly allowance and OTC quarterly allowance table layouts are supported.
D-SNP/C-SNP records use explicit SNPType or name flags as well as category lists;
users must enable the special-needs filter to display those plans. Drug-only
HealthSpring results are not sent to the medical benefit PDF queue. Prescription
and pharmacy links open the carrier tools; exact pharmacy quotes remain unconnected.
Live validation: H9725-009-003 in ZIP 28697/Wilkes returned dental $1,450 and OTC
$45/quarter; H9725-003-000 in ZIP 28262/Mecklenburg returned dental $2,000 and OTC
$140/quarter. These are different plan segments and are never interchanged.

Plan details use the selected ZIP/county/year across the 15 configured states;
there is no separate statewide bulk crawler or new hosting requirement. Public
Connecture responses for Highmark/Wholecare, Molina and Excellus now retain only
whitelisted benefit descriptions and drug-deductible fields. Supported comparable
specialist, hospital and quarterly OTC facts update the same comparison. Unknown,
monthly, conditional or ambiguous amounts are not coerced into quarterly amounts.

Standalone Part D plans have their own compact drug-plan table, source-linked drug
benefit sections in plan details, and drug details in Excel. UHC tier labels retain
public pharmacy qualifiers. HealthSpring deductible/tier schedules preserve supply,
preferred/standard and retail/mail conditions; these are not prescription quotes.
HealthSpring regional PDPs can use the existing dated formulary book only when its
identifier exactly matches the live plan's FormularyExternalID and year. This
avoids guessing a regional CMS-to-formulary mapping. SilverScript Choice's shared
contract-family booklet supplies only uniform deductible wording, not state-varying
premiums or tier amounts; its exact plan-bound catalog separately supplies formulary
candidates. A drug-plan summary failure no longer blocks independent catalog-bound
formulary reading. Medical-plan identity failures still stop companion processing.

If reviewed plan-bound PDFs yield no OTC amount, the cell says "No separate OTC
amount found in reviewed documents"; missing imported OTC facts say "No verified
OTC amount in saved documents". Neither means OTC is excluded or worth $0. Standalone
Part D plans retain "Not applicable" for medical/OTC columns. Live validation of
2027 ZIP 28697 verified S5601-016 ($700 deductible), S5921-390-000 ($0 for tiers 1/2,
$300 for tiers 3/4/5), S5921-353-000 ($700), and S5715-029-000 ($700 public deductible
with pharmacy-specific tier schedules and exact formulary ID 27061). The UHC and
SilverScript PDF checks also extracted independent formulary candidate rows.
Carrier availability, product scope and quote-only/unconnected sources still show
explicit statuses; these changes do not imply every carrier has a full parser.

Plan names in both the carrier comparison and the Part D table open and scroll to
the corresponding lower details section. Mouse and keyboard activation focus the
summary, and the open state is retained when automatic document updates rerender.

Full chart audit improvements (ZIP-based plan details v5): Aetna hospital schedules
are read from the in-network column only, including wrapped day ranges. HealthSpring
combined-network annual dental limits and yearly routine eyewear allowance wording
are supported. Alternate benefit disclosures preserve actual two-year eyewear,
hearing allowances, per-device copay ranges and optional paid dental rider premiums
with PDF page links and dates. They display in the chart and Excel but never replace
annual/Advanced-device ranking metrics. The dental, eyewear and hearing columns
show their periods/types explicitly. Explicitly uncovered hearing aids display
"Not covered", never a fabricated $0 copay. Routine ride counts are not inferred
from ambulance or worldwide emergency transportation. If reviewed sources do not
yield a routine ride count or eyewear allowance, the chart explains that specific
source gap instead of asserting coverage or showing a guessed amount.

UHC exact INN shopping rows now also populate medical maximum and specialist values
before PDF reading; combined or out-of-network limits are not substituted. The
21-medical-plan Wilkes audit closed all five hospital extraction gaps, the remaining
HealthSpring annual dental gap, and the missing annual eyewear/device disclosures.
The remaining unconfirmed categories in that audit are 11 separate OTC amounts,
13 routine ride counts and one routine eyewear allowance. These remain clearly
identified source gaps, not zero-valued benefits. No provider selections were
entered in that pasted search; no provider participation is inferred.

Plan-document reliability (ZIP-based plan details v6): a successful public search
seeds a five-minute in-memory validation snapshot per carrier/ZIP/county/year.
PDF requests reuse the exact plan and validated county relationship instead of
repeating the entire ZIP and carrier list lookup for every plan. Entries are
copied, bounded to 48 carrier/location groups and invalidated by each newer search,
including empty results. Standalone PDF requests still perform full verification
when no current exact-match snapshot exists. No personal search selections or
sessions are stored in these snapshots.

ZIP lookup, availability, catalogs and document reads retry transient connection
failures and HTTP 408/429/5xx up to three times. Short numeric Retry-After delays
are respected; longer requested pauses stop automatic retries. Access denial,
certificate and changed-response errors are reported without repeated requests.
Errors identify the stage and HTTP status or exception class without exposing raw
session URLs or unexpected exception values. Browser requests also retry a busy local PDF
queue up to five times with bounded delays. Aetna official source links include
the exact PlanID-year parameter supplied by the shopping result.
The exact Aetna H5521-348 request succeeded during investigation; the Mac's original
generic failure was not reproduced, so these changes do not assert a proven root
cause for it. Validation covers snapshot scope/expiry/immutability/invalidation,
bounded transient retries, phase diagnostics, real selected-plan retrieval and
browser busy recovery with per-plan access-error display.

Automatic document loading now starts with the plans shown by the current filters.
Hidden special-needs plan documents wait until those plans are enabled; new visible
plans load automatically after the current queue completes. Failed checks are not
retried indefinitely by filter changes. PDF buttons wait during bulk work so manual
clicks cannot create duplicate requests for queued plans. This reduces the default
workload without changing carrier availability or special-needs eligibility rules.
