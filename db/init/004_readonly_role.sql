-- CHAT-2 safety: sql_query runs against a real read-only role, not the
-- app's own superuser connection, so a bug in a SQL template (or a future
-- one added carelessly) can't write to the database no matter what.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dblp_readonly') THEN
    CREATE ROLE dblp_readonly LOGIN PASSWORD 'dblp_readonly_pw';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE dblp TO dblp_readonly;
GRANT USAGE ON SCHEMA public TO dblp_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dblp_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dblp_readonly;
