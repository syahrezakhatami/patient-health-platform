# Healthcare Web

Staff SPA shell. Architecture: `docs/architecture/healthcare-web-shell.md`.

Requires Node.js 20+.

```bash
nvm use
npm install
npm run dev
```

Public env only: copy `.env.example` to `.env.local`. Never put OIDC client secrets, JWTs, or database credentials in frontend env.
