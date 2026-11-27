# 公式リファレンス

設計判断は2026年9月時点の以下の公式資料を基準にしています。
実装時は各プロジェクトのrelease noteとversion別documentを再確認します。

## React / Next.js

- [Creating a React App](https://react.dev/learn/creating-a-react-app)
- [React Versions](https://react.dev/versions)
- [Next.js App Router](https://nextjs.org/docs/app)
- [Next.js Project Structure](https://nextjs.org/docs/app/getting-started/project-structure)
- [Next.js Error Handling](https://nextjs.org/docs/app/getting-started/error-handling)
- [Next.js 16 Upgrade Guide](https://nextjs.org/docs/app/guides/upgrading/version-16)

## Python / FastAPI

- [Python Downloads](https://www.python.org/downloads/)
- [Python 3.14 Documentation](https://docs.python.org/3.14/)
- [FastAPI Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [FastAPI Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)

## Supabase / PostgreSQL

- [Supabase Auth with Next.js](https://supabase.com/docs/guides/auth/server-side/nextjs)
- [Supabase JWT](https://supabase.com/docs/guides/auth/jwts)
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase Securing the Data API](https://supabase.com/docs/guides/api/securing-your-api)
- [Supabase Database Migrations](https://supabase.com/docs/guides/deployment/database-migrations)
- [PostgreSQL Current Documentation](https://www.postgresql.org/docs/current/)
- [pgvector](https://github.com/pgvector/pgvector)

## API / Git / Security

- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP API Security Top 10](https://owasp.org/API-Security/)

## Hosting

- [Vercel Monorepos](https://vercel.com/docs/monorepos)
- [Vercel Deployments](https://vercel.com/docs/deployments)
- [Render FastAPI](https://render.com/docs/deploy-fastapi)
- [Render Background Workers](https://render.com/docs/background-workers)

## 運用ルール

- major/minor versionを記憶だけで更新しない
- frameworkのdocumentは実際の`package.json`/`pyproject.toml`と同じversionを読む
- Supabaseは変更が速いため、実装前にchangelogを確認する
- deprecated APIを新規コードへ導入しない
- 「latest」を設定値へ書かず、検証済みversionとlockfileをcommitする
