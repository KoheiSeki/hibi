begin;
select plan(8);
select has_table('app', 'captures', 'captures table exists');
select has_column('app', 'captures', 'user_id', 'captures link to profile owner');
select has_column('app', 'captures', 'raw_text', 'captures store raw input');
select has_column('app', 'captures', 'idempotency_key', 'captures store create idempotency key');
select has_index(
  'app',
  'captures',
  'ix_captures__user_id_created_at',
  'owner list index exists'
);
select is(
  has_table_privilege('anon', 'app.captures', 'SELECT'),
  false,
  'anon cannot read captures'
);
select is(
  has_table_privilege('authenticated', 'app.captures', 'SELECT'),
  false,
  'authenticated cannot read captures'
);
select is(
  has_table_privilege('hibi_runtime_user', 'app.captures', 'SELECT'),
  true,
  'runtime deployment user receives capture read access'
);
select * from finish();
rollback;
