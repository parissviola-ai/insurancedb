PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS plans (
 id TEXT PRIMARY KEY, carrier TEXT NOT NULL, name TEXT NOT NULL,
 year INTEGER NOT NULL, state TEXT NOT NULL, county TEXT NOT NULL,
 zip TEXT NOT NULL CHECK(length(zip)=5), business TEXT NOT NULL,
 premium TEXT NOT NULL DEFAULT '', benefits TEXT NOT NULL DEFAULT '',
 source_url TEXT NOT NULL, verified_on TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS plans_area ON plans(year, state, zip);
CREATE TABLE IF NOT EXISTS coverage (
 id INTEGER PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('medication','provider')),
 name TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL CHECK(status IN ('covered','restricted','not covered','unverified')),
 restrictions TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL,
 verified_on TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS coverage_plan ON coverage(plan_id, kind);
CREATE TABLE IF NOT EXISTS devoted_zip_counties (
 zip TEXT NOT NULL, county_code TEXT NOT NULL, county_name TEXT NOT NULL,
 PRIMARY KEY(zip,county_code)
);
CREATE TABLE IF NOT EXISTS devoted_service_areas (
 locator TEXT NOT NULL, county_code TEXT NOT NULL, name TEXT NOT NULL,
 PRIMARY KEY(locator,county_code)
);
CREATE TABLE IF NOT EXISTS devoted_documents (
 url TEXT PRIMARY KEY, text TEXT NOT NULL, sha256 TEXT NOT NULL,
 retrieved_at TEXT NOT NULL, year INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS devoted_document_links (
 locator TEXT NOT NULL, kind TEXT NOT NULL, url TEXT NOT NULL, page_url TEXT NOT NULL,
 PRIMARY KEY(locator,kind,url)
);
CREATE TABLE IF NOT EXISTS devoted_sync (
 id INTEGER PRIMARY KEY CHECK(id=1), retrieved_at TEXT NOT NULL, site_build TEXT NOT NULL, source_url TEXT NOT NULL
);
