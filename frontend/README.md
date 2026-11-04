# ChangeGuard Frontend Foundation

Production-ready Next.js frontend for the ChangeGuard construction change-order governance and commercial audit platform.

## Architecture & Tech Stack

- **Framework**: [Next.js](https://nextjs.org/) App Router (React 19)
- **Language**: TypeScript with strict mode enabled (`strict`, `noUncheckedIndexedAccess`, `noImplicitReturns`)
- **Styling**: [Tailwind CSS v4](https://tailwindcss.com/) with design tokens defined in `src/app/globals.css`
- **Data Fetching & Caching**: [TanStack Query v5](https://tanstack.com/query) (`@tanstack/react-query`) with transient-fault retries and query invalidation
- **Schema & Form Validation**: [Zod](https://zod.dev/) for client-side forms and API response contracts
- **HTTP Client**: [Axios](https://axios-http.com/) client with JWT bearer header injection, token rotation, and in-memory + tab-scoped session sync
- **Access Control & RBAC**: Client-side mirror of backend RBAC (`lib/rbac.ts`) for role-aware navigation and guarded UI actions
- **No AI features**: Pure human review workflows for potential changes, risk decisions, and change order management

## Application Routes

- `/` &rarr; Redirects authenticated visitors to `/projects`, unauthenticated to `/login`
- `/login` &rarr; Sign in with workspace slug, email, and password (Zod validation, error banners, loading indicators)
- `/register` &rarr; Organization workspace registration (auto slug suggestion, password criteria, async confirmation)
- `/projects` &rarr; Paginated projects directory with status filtering (`active`, `on_hold`, `completed`, `cancelled`, `archived`), code/client search, and role-guarded project creation modal
- `/projects/[projectId]` &rarr; Comprehensive project hub with tabs for:
  - **Overview**: Commercial baseline, contract value, timeline, stakeholders
  - **Documents**: File upload modal, processing status badges, file size and download links
  - **Potential Changes**: Scope variances and variances requiring human review with "Convert to Change Order"
  - **Risks**: Severity badges, financial exposure, schedule impact, and audited decision modal (`accept`, `dismiss`, `override`)
  - **Change Orders**: Create change order, inspect claims, and view approval status
- `/review-queue` &rarr; Cross-project triage inbox for human reviewers:
  - Triage potential changes requiring human verification
  - Decide on commercial & programme risks
  - Audit flagged documents requiring classification review
- `/settings` &rarr; User session details, assigned role badge, complete 22-permission RBAC audit matrix, and live backend `/health` connectivity status

## Reusable Component Library

Importable directly from `@/components/ui`:

| Component | Path | Description |
|---|---|---|
| `Button` | `@/components/ui/button` | Primary, secondary, ghost, and danger variants with loading spinner and disabled states |
| `Input` | `@/components/ui/form` | Accessible text input with `aria-invalid` and error states |
| `Select` | `@/components/ui/form` | Styled select menu with focus ring and invalid states |
| `Field` | `@/components/ui/form` | Form field wrapper with label, required asterisk, hint, and `aria-describedby` errors |
| `DataTable` / `Table` | `@/components/ui/table` | Accessible sortable table with column definitions, alignments, and empty row handling |
| `Card` | `@/components/ui/card` | Structured container with `CardHeader`, `CardTitle`, `CardBody`, and `CardFooter` |
| `Badge` | `@/components/ui/badge` | Status badge with tones (`brand`, `success`, `warning`, `danger`, `info`, `neutral`) |
| `Modal` | `@/components/ui/modal` | Native `<dialog>` modal with focus trapping, backdrop, and cancel handlers |
| `Tabs` | `@/components/ui/tabs` | Accessible keyboard-navigable tabs (`ArrowLeft`, `ArrowRight`, `Home`, `End`) with badges |
| `EmptyState` | `@/components/ui/states` | Dotted container with icon, title, description, and optional action CTA |
| `ErrorState` | `@/components/ui/states` | Danger alert banner with title, message, details, and optional "Try again" retry button |
| `LoadingSkeleton` | `@/components/ui/states` | Shimmering placeholder for tables and card layouts during query resolution |

## Environment Variables

Copy `.env.example` to `.env.local`:

```bash
# FastAPI API root without trailing slash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

# TanStack Query stale time in milliseconds (default: 30000)
NEXT_PUBLIC_QUERY_STALE_TIME_MS=30000
```

## Available Scripts

```bash
# Start development server
npm run dev

# Run full TypeScript check without emitting
npm run typecheck

# Run ESLint
npm run lint

# Build production bundle
npm run build

# Start production server
npm run start
```

