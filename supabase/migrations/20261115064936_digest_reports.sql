create table app.digest_reports (
    id uuid primary key,
    user_id uuid not null references app.profiles(user_id) on delete cascade,
    kind text not null,
    period_start date not null,
    timezone text not null,
    status text not null,
    content jsonb,
    content_version text not null,
    summary_model text,
    error_code text,
    generated_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint ck_digest_reports__kind
        check (kind in ('daily', 'weekly')),
    constraint ck_digest_reports__status
        check (status in ('pending', 'ready', 'failed')),
    constraint ck_digest_reports__content_version
        check (content_version in ('daily-digest-v1', 'weekly-review-v1')),
    constraint ck_digest_reports__content_ready
        check ((status='ready')=(content is not null)),
    constraint uq_digest_reports__user_id_kind_period_start
        unique (user_id, kind, period_start)
);

revoke all on app.digest_reports from public, anon, authenticated;
grant select, insert, update, delete on app.digest_reports to hibi_runtime;


alter table app.outbox_events
    drop constraint outbox_events_aggregate_id_fkey;

alter table app.outbox_events
    drop constraint ck_outbox_events__aggregate_type,
    drop constraint ck_outbox_events__event_type;

alter table app.outbox_events
    add constraint ck_outbox_events__aggregate_type
        check (aggregate_type in ('capture', 'digest_report')),
    add constraint ck_outbox_events__event_type
        check (event_type in ('capture.processing_requested', 'digest_report.generation_requested')),
    add constraint ck_outbox_events__aggregate_event
        check (
            (aggregate_type = 'capture' and event_type = 'capture.processing_requested')
            or
            (aggregate_type = 'digest_report' and event_type = 'digest_report.generation_requested')
        );

