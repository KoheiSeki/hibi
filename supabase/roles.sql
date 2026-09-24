do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'hibi_runtime') then
    create role hibi_runtime nologin noinherit;
  end if;

  if not exists (select 1 from pg_roles where rolname = 'hibi_runtime_user') then
    create role hibi_runtime_user login inherit;
  end if;
end
$$;

grant hibi_runtime to hibi_runtime_user;