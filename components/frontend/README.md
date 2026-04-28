# SyftHub Frontend

The web app for SyftHub — built with React 19, TypeScript, Vite, and Tailwind.

For project-level docs, see the [repository README](../../README.md) and [`docs/`](../../docs/index.md).

## Running locally

From the repo root, `make dev` starts the frontend at <http://localhost:8080> alongside the rest of the stack.

To work on just the frontend:

```bash
cd components/frontend
npm install
npm run dev
```

The dev server runs on <http://localhost:3000> and proxies API calls to the backend.

## Common scripts

```bash
npm run dev        # dev server
npm run build      # production build
npm run lint       # eslint
npm run typecheck  # typescript
npm test           # playwright e2e
```

## Learn more

- [Frontend architecture](../../docs/architecture/components/frontend.md)
