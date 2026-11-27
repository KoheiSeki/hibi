create extension if not exists vector with schema extensions;

create table app.capture_embeddings (
    capture_id uuid primary key references app.captures (id) on delete cascade,
    user_id uuid not null references app.profiles (user_id) on delete cascade,
    content_text text not null,
    content_hash text not null,
    embedding extensions.vector(8) not null,
    embedding_model text not null,
    embedding_dimensions integer not null,
    embedding_version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint ck_capture_embeddings__content_text
        check (char_length(content_text) >= 1 and char_length(content_text) <= 2000),
    constraint ck_capture_embeddings__hash
        check (content_hash ~ '^[0-9a-f]{64}$'),
    constraint ck_capture_embeddings__embedding_model
        check (char_length(embedding_model) >= 1),
    constraint ck_capture_embeddings__embedding_dimensions
        check (embedding_dimensions = 8),
    constraint ck_capture_embeddings__embedding_version
        check (embedding_version = 'capture-embed-v1')
);

create index ix_capture_embeddings__user_id
    on app.capture_embeddings (user_id);

revoke all on app.capture_embeddings from public, anon, authenticated;
grant select, insert, update, delete on app.capture_embeddings to hibi_runtime;