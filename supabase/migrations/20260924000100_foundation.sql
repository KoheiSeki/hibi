create schema if not exists app;
revoke all on schema app from public, anon, authenticated;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'hibi_runtime') then
    create role hibi_runtime nologin noinherit;
  end if;
end
$$;

grant usage on schema app to hibi_runtime;

create table app.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text check (char_length(display_name) <= 100),
  timezone text not null default 'UTC',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_profiles__timezone_not_empty check (char_length(timezone) > 0)
);

revoke all on app.profiles from public, anon, authenticated;
grant select, insert, update, delete on app.profiles to hibi_runtime;

create or replace function app.create_auth_profile()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into app.profiles (user_id) values (new.id);
  return new;
end;
$$;

revoke all on function app.create_auth_profile() from public;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function app.create_auth_profile();
