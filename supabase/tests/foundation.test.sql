begin;
select plan(8);
select has_schema('app', 'private app schema exists');
select has_table('app', 'profiles', 'profiles table exists');
select has_column('app', 'profiles', 'user_id', 'profiles link to auth user');
select isnt_empty(
  $$select 1 from pg_roles where rolname = 'hibi_runtime' and not rolcanlogin$$,
  'runtime privilege role is NOLOGIN'
);
select isnt_empty(
  $$select 1 from pg_roles where rolname = 'hibi_runtime_user' and rolcanlogin$$,
  'runtime deployment user is LOGIN'
);
select isnt_empty(
  $$select 1 from pg_roles where rolname = 'hibi_runtime_user' and rolinherit$$,
  'runtime deployment user inherits grants'
);
select ok(
  pg_has_role('hibi_runtime_user', 'hibi_runtime', 'member'),
  'runtime deployment user is a member of privilege role'
);
select is(
  has_table_privilege('hibi_runtime_user', 'app.profiles', 'SELECT'),
  true,
  'runtime deployment user receives profile read access'
);
select * from finish();
rollback;
