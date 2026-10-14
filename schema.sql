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
