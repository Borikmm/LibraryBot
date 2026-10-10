CREATE TABLE IF NOT EXISTS schema_migrations (
    version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS groups (
    chat_id bigint PRIMARY KEY, title text NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT now(), invite_scanned boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id bigint PRIMARY KEY, group_id bigint REFERENCES groups(chat_id),
    data jsonb NOT NULL CHECK (jsonb_typeof(data) = 'object'),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS profiles_group ON profiles(group_id);
CREATE TABLE IF NOT EXISTS reading_days (
    user_id bigint NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    local_day date NOT NULL, read_at timestamptz NOT NULL,
    PRIMARY KEY (user_id, local_day)
);
CREATE TABLE IF NOT EXISTS actions (
    token text PRIMARY KEY, owner_id bigint NOT NULL REFERENCES profiles(user_id),
    kind text NOT NULL, payload jsonb NOT NULL,
    expires_at timestamptz NOT NULL, consumed boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS actions_owner ON actions(owner_id);
CREATE TABLE IF NOT EXISTS menus (
    token text PRIMARY KEY, owner_id bigint NOT NULL, chat_id bigint NOT NULL,
    message_id bigint, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS deliveries (
    id bigserial PRIMARY KEY, user_id bigint NOT NULL REFERENCES profiles(user_id),
    event_key text NOT NULL, payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(), sent_at timestamptz,
    UNIQUE(user_id, event_key)
);
CREATE INDEX IF NOT EXISTS deliveries_pending ON deliveries(status, created_at);
INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING;
