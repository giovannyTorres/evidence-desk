# Evidence Desk web

Next.js 16.4.5 / React 19.3.1 / TypeScript, served on port 3101. Run from this directory:

```sh
npm ci
npm run dev
```

The API must be running on `http://localhost:8101`; `API_URL` selects a different **server-side** origin. The Next route at `src/app/api/[...path]/route.ts` forwards to that fixed origin at runtime, preserves HttpOnly session cookies, streams SSE, does not follow redirects, caps multipart requests, and returns safe transport errors. Set the backend `PUBLIC_ORIGIN=http://localhost:3101` for local browser use. Provider credentials never enter this app.

```sh
npm run lint
npm run typecheck
npm test
npm run build
npm start
# With the backend, database and worker running:
npx playwright install chromium
npm run test:e2e
# Or use an installed browser:
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
```

`npm start` prepares static files for the standalone production server. In containers, copy `.next/standalone` and `.next/static` and execute `node server.js` with `PORT=3101`.

## Verification

Six Vitest tests cover fragmented UTF-8 SSE, API error handling, the fixed gateway destination, manual redirects, request limits, and safe upstream errors. Three Playwright tests use the **real local FastAPI/PostgreSQL/worker**: sign-in → sample question → streamed answer → source → persisted reload; document upload and mobile layout; DEMO free-form guidance and keyboard focus. No provider API calls occur in these tests.

Real screenshots are saved to `../../docs/screenshots/`: `01-sign-in.png`, `02-workspace.png`, `03-answer-and-source.png`, `04-document-library.png`, and `05-mobile-workspace.png`. Desktop, source panel, and mobile captures were visually inspected. This is not a complete WCAG assessment.

## Dependency decisions

The official [Next.js installation guide](https://nextjs.org/docs/app/getting-started/installation) and [React versions](https://react.dev/versions) were consulted on 2026-11-05; package registry versions and peer compatibility were checked. Direct dependencies are exact and the npm lockfile captures transitive versions. ESLint 10 uses the Next plugin, TypeScript ESLint and React Hooks plugin directly: the `eslint-config-next` wrapper still included plugins whose peer range ended at ESLint 9. This avoids unsupported peer overrides while retaining the relevant Next and Hooks rules.

All fonts are system fonts. No assets, fonts, analytics, or credentials are fetched from a third-party runtime origin.

Audit on 2026-11-05: `npm audit` reported zero vulnerabilities after pinning the transitive development tool dependency `minimatch` to 11.0.4, which fixes GHSA-g3hv-75wg-m249. Lint, types, unit tests, and production build passed with this override. Re-run audit as advisories change.
