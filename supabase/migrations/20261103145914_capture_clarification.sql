alter table app.captures
    add column clarification_text text,
    add constraint ck_captures__clarification_text
        check (
            clarification_text is null
            or (
                char_length(clarification_text) >= 1
                and char_length(clarification_text) <= 500
            )
        );