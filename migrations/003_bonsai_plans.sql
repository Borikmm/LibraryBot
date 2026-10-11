-- Existing drawings retain the ASCII algorithm; no coordinates or progress are changed.
UPDATE profiles
SET data = data || jsonb_build_object(
    'tree_plan', NULL,
    'books', COALESCE((
        SELECT jsonb_agg(book || jsonb_build_object('tree_plan', NULL) ORDER BY ordinal)
        FROM jsonb_array_elements(data->'books') WITH ORDINALITY AS items(book, ordinal)
    ), '[]'::jsonb)
)
WHERE NOT (data ? 'tree_plan');
INSERT INTO schema_migrations(version) VALUES (3) ON CONFLICT DO NOTHING;
