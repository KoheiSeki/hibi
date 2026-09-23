# Contributing

Use conventional commits. Before committing, run `just check` (or the equivalent commands in the root `justfile`). API behavior changes must update `contracts/openapi.json` and the generated TypeScript client. Database schema changes belong only in `supabase/migrations`; Alembic is not used.
