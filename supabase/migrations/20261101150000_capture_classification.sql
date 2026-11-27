alter table app.captures
    add column category text,
    add column route text,
    add column urgency text,
    add column confidence numeric,
    add column policy_version text,
    add question_version text,
    add processed_at timestamptz,
    add constraint ck_captures__category
        check (category in ('shopping', 'reminder', 'expense', 'note', 'chat')),
    add constraint ck_captures__route
        check (route in ('shopping', 'reminder', 'expense', 'note', 'chat', 'clarify')),
    add constraint ck_captures__urgency
        check (urgency in ('low', 'normal', 'high')),
    add constraint ck_captures__confidence
        check (confidence>=0 and confidence <=1),
    add constraint ck_captures__classification_presence
        check (
            num_nonnulls(
                category,
                route,
                urgency,
                confidence,
                policy_version,
                question_version,
                processed_at
            ) in (0, 7)
        );