do $verify$
declare
  owner_id uuid := '22222222-2222-4222-8222-222222222222';
  capture_id uuid := '0198f0c2-7c1a-7000-8000-000000000001';
  request_hash text := repeat('a', 64);
begin
  if to_regclass('app.captures') is null then
    raise exception 'app.captures must exist';
  end if;

  if has_table_privilege('anon', 'app.captures', 'SELECT') then
    raise exception 'anon must not read app.captures';
  end if;

  if has_table_privilege('authenticated', 'app.captures', 'SELECT') then
    raise exception 'authenticated must not read app.captures';
  end if;

  if not has_table_privilege('hibi_runtime', 'app.captures', 'SELECT')
    or not has_table_privilege('hibi_runtime', 'app.captures', 'INSERT')
    or not has_table_privilege('hibi_runtime', 'app.captures', 'UPDATE')
    or not has_table_privilege('hibi_runtime', 'app.captures', 'DELETE')
  then
    raise exception 'hibi_runtime must have captures CRUD privileges';
  end if;

  if not exists (
    select 1
    from pg_indexes
    where schemaname = 'app'
      and tablename = 'captures'
      and indexname = 'ix_captures__user_id_created_at'
  ) then
    raise exception 'ix_captures__user_id_created_at must exist';
  end if;

  insert into auth.users (id) values (owner_id)
  on conflict (id) do nothing;

  if not exists (select 1 from app.profiles where user_id = owner_id) then
    raise exception 'auth user trigger must create app profile before capture insert';
  end if;

  insert into app.captures (
    id,
    user_id,
    raw_text,
    status,
    idempotency_key,
    request_hash
  ) values (
    capture_id,
    owner_id,
    '牛乳を買う',
    'pending',
    '11111111-1111-4111-8111-111111111111',
    request_hash
  );

  begin
    insert into app.captures (
      id,
      user_id,
      raw_text,
      status,
      idempotency_key,
      request_hash
    ) values (
      '0198f0c2-7c1a-7000-8000-000000000002',
      owner_id,
      '別の本文',
      'pending',
      '11111111-1111-4111-8111-111111111111',
      repeat('b', 64)
    );
    raise exception 'duplicate (user_id, idempotency_key) must fail';
  exception
    when unique_violation then
      null;
  end;

  begin
    insert into app.captures (
      id,
      user_id,
      raw_text,
      status,
      idempotency_key,
      request_hash
    ) values (
      '0198f0c2-7c1a-7000-8000-000000000003',
      owner_id,
      '',
      'pending',
      '22222222-2222-4222-8222-222222222222',
      request_hash
    );
    raise exception 'empty raw_text must fail';
  exception
    when check_violation then
      null;
  end;
end
$verify$;
