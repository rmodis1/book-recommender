# Contributing to Shelf

## Branch Strategy

- `main` — production-ready code; protected, requires passing CI
- `dev` — integration branch for in-progress work
- Feature branches: `feat/<short-description>` (e.g., `feat/nyt-tool`)
- Bug fixes: `fix/<short-description>`

## Running Locally

See the [README](README.md) Quick Start section.

## CI Checks

All PRs must pass three GitHub Actions workflows before merging:

| Workflow | Triggers on | Checks |
|---|---|---|
| `backend-ci` | Changes to `backend/**` | ruff, mypy, bandit, pytest |
| `frontend-ci` | Changes to `frontend/**` | eslint, tsc, next build |
| `codeql` | Every PR + weekly | Security scanning (Python + JS/TS) |

Run checks locally before opening a PR:

```bash
# Backend
cd backend
ruff check .
mypy app/
bandit -r app/
pytest tests/

# Frontend
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

## Environment Variables

Never commit `.env` files. Use `.env.example` as the template and add real values to `.env` (gitignored).
