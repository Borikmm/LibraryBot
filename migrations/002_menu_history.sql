ALTER TABLE menus ADD COLUMN IF NOT EXISTS history jsonb NOT NULL DEFAULT '[]'::jsonb;
INSERT INTO schema_migrations(version) VALUES (2) ON CONFLICT DO NOTHING;
