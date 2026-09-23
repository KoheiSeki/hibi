do $verify$
declare
  runtime_user_id uuid := '11111111-1111-4111-8111-111111111111';
begin
  if not exists (
    select 1 from pg_roles
    where rolname = 'hibi_runtime' and not rolcanlogin
  ) then
    raise exception 'hibi_runtime must be a NOLOGIN privilege role';
  end if;

  if not exists (
    select 1 from pg_roles
    where rolname = 'hibi_runtime_user' and rolcanlogin and rolinherit
  ) then
    raise exception 'hibi_runtime_user must be an inheriting LOGIN role';
  end if;

  if not pg_has_role('hibi_runtime_user', 'hibi_runtime', 'member') then
    raise exception 'hibi_runtime_user must inherit hibi_runtime privileges';
  end if;

  if to_regclass('app.profiles') is null then
    raise exception 'app.profiles must exist';
  end if;

  insert into auth.users (id) values (runtime_user_id)
  on conflict (id) do nothing;

  if not exists (select 1 from app.profiles where user_id = runtime_user_id) then
    raise exception 'auth user trigger must create app profile';
  end if;
end
$verify$;
