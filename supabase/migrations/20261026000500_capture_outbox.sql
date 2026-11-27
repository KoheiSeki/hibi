alter table app.captures
  add column processing_generation integer not null default 1;

alter table app.captures
  add constraint ck_captures__processing_generation
  check (processing_generation >= 1);

create table app.outbox_events (
  id uuid primary key,
  user_id uuid not null references app.profiles(user_id) on delete cascade,
  aggregate_type text not null,
  aggregate_id uuid not null references app.captures(id) on delete cascade,
  event_type text not null,
  processing_generation integer not null,
  status text not null default 'pending',
  available_at timestamptz not null default now(),
  published_at timestamptz,
  created_at timestamptz not null default now(),
  constraint ck_outbox_events__aggregate_type
    check (aggregate_type = 'capture'),
  constraint ck_outbox_events__event_type
    check (event_type = 'capture.processing_requested'),
  constraint ck_outbox_events__processing_generation
    check (processing_generation >= 1),
  constraint ck_outbox_events__status
    check (status in ('pending', 'published'))
);

create index ix_outbox_events__pending_available
  on app.outbox_events (available_at, id)
  where status = 'pending';

revoke all on app.outbox_events from public, anon, authenticated;
grant select, insert, update, delete on app.outbox_events to hibi_runtime;
