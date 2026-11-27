create table app.capture_scenarios (
    capture_id uuid primary key references app.captures (id) on delete cascade,
    user_id uuid not null references app.profiles (user_id) on delete cascade,
    route text not null,
    status text not null,
    title text not null,
    amount integer,
    remind_text text,
    policy_version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    
    constraint ck_capture_scenarios__route
        check (route in ('shopping', 'reminder', 'expense')),
    constraint ck_capture_scenarios__status
        check (status in ('proposed', 'accepted')),
    constraint ck_capture_scenarios__title
        check (char_length(title) >=1 and char_length(title) <= 200),
    constraint ck_capture_scenarios__amount
        check (amount is null or amount >= 0),
    constraint ck_capture_scenarios__remind_text
        check (remind_text is null or (char_length(remind_text) >= 1 and char_length(remind_text) <= 200)),
    constraint ck_capture_scenarios__policy_version
        check (policy_version = 'capture-scenario-v1')
);

revoke all on app.capture_scenarios from public, anon, authenticated;
grant select, insert, update, delete on app.capture_scenarios to hibi_runtime;