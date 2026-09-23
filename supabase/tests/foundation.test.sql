begin;
select plan(4);
select has_schema('app', 'private app schema exists');
select has_table('app', 'profiles', 'profiles table exists');
select has_column('app', 'profiles', 'user_id', 'profiles link to auth user');
select isnt_empty($$select 1 from pg_roles where rolname = 'hibi_runtime'$$, 'runtime role exists');
select * from finish();
rollback;
