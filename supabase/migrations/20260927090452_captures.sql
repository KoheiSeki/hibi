create table if not exists app.captures (
  id uuid primary key,
  user_id uuid not null references app.profiles(user_id) on delete cascade,
  raw_text text not null,
  status text not null default 'pending',
  idempotency_key text not null,
  request_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_captures__raw_text_length
    check (char_length(raw_text) >= 1 and char_length(raw_text) <= 2000),
  constraint ck_captures__status
    check (status in ('pending', 'processing', 'completed', 'failed')),
  constraint ck_captures__idempotency_key_length
    check (char_length(idempotency_key) >= 8 and char_length(idempotency_key) <= 128),
  constraint ck_captures__request_hash_sha256
    check (request_hash ~ '^[0-9a-f]{64}$'),
  constraint uq_captures__user_id_idempotency_key
    unique (user_id, idempotency_key)
);

create index if not exists ix_captures__user_id_created_at
  on app.captures (user_id, created_at desc, id desc);

revoke all on app.captures from public, anon, authenticated;
grant select, insert, update, delete on app.captures to hibi_runtime;
