-- Dashboard views (Technical Proposal §4.1, §8.1 DB-4)

-- Single-row table the ETL upserts after every successful load, so v_kpis
-- has a real "last update" even before the centrality job has ever run.
CREATE TABLE IF NOT EXISTS etl_meta (
  id            SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  loaded_at     TIMESTAMPTZ,
  papers_loaded INT,
  data_scope    TEXT
);

-- DASH-7: precomputed by the ETL (jobs/etl.py:compute_topic_trends) from
-- titles it already holds in memory - a live per-request tokenize-and-count
-- over all titles measured ~800ms on the real v1 data, over the 500ms
-- endpoint budget, so this table lets the API just SELECT the top keywords.
CREATE TABLE IF NOT EXISTS topic_year_counts (
  word         TEXT NOT NULL,
  year         SMALLINT NOT NULL,
  paper_count  INT NOT NULL,
  PRIMARY KEY (word, year)
);

-- DASH-2: publications per year, journal vs conference
CREATE OR REPLACE VIEW v_papers_per_year AS
SELECT year,
       CASE
         WHEN type = 'article' THEN 'journal'
         WHEN type = 'inproceedings' THEN 'conference'
         ELSE 'other'
       END AS series,
       COUNT(*) AS paper_count
FROM paper
WHERE year IS NOT NULL
GROUP BY year, series;

-- DASH-3: top venues (API applies the year filter / LIMIT)
CREATE OR REPLACE VIEW v_top_venues AS
SELECT v.venue_id, v.key_prefix, v.name, v.type, p.year, COUNT(*) AS paper_count
FROM paper p
JOIN venue v ON v.venue_id = p.venue_id
GROUP BY v.venue_id, v.key_prefix, v.name, v.type, p.year;

-- DASH-5: median team size per year with an IQR band
CREATE OR REPLACE VIEW v_team_size_by_year AS
SELECT year,
       COUNT(*) AS paper_count,
       PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY author_count) AS median_team_size,
       PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY author_count) AS p25_team_size,
       PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY author_count) AS p75_team_size
FROM (
  SELECT p.paper_id, p.year, COUNT(a.author_id) AS author_count
  FROM paper p
  JOIN authorship a ON a.paper_id = p.paper_id
  WHERE p.year IS NOT NULL
  GROUP BY p.paper_id, p.year
) team_sizes
GROUP BY year;

-- DASH-6: papers per author (long tail)
CREATE OR REPLACE VIEW v_author_productivity AS
SELECT author_id, COUNT(*) AS paper_count
FROM authorship
GROUP BY author_id;

-- DASH-1: KPI tiles
CREATE OR REPLACE VIEW v_kpis AS
SELECT
  (SELECT COUNT(*) FROM paper) AS paper_count,
  (SELECT COUNT(*) FROM author) AS author_count,
  (SELECT COUNT(*) FROM venue) AS venue_count,
  (SELECT loaded_at FROM etl_meta WHERE id = 1) AS last_update;
