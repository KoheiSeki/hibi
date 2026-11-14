alter table app.captures
    add column urgency_score numeric(3,2),
    add constraint ck_captures__urgency_score
        check (
            urgency_score is null
            or (
                urgency_score >= 0 and urgency_score <= 1
            )
        );

alter table app.capture_scenarios
    add column due_at timestamptz,
    add column done_at timestamptz;

alter table app.profiles
    alter column timezone set default 'Asia/Tokyo';

update app.profiles
    set timezone = 'Asia/Tokyo'
    where timezone = 'UTC';
