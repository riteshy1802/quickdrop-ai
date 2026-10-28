# QuickDrop AI frontend

A dark, responsive landing page, Rider Support prototype, and Operations Console for the Rider Payout Dispute Desk. Built with Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui primitives, Motion, Lucide icons, and TanStack React Query. Geist Sans and Geist Mono are loaded through `next/font`.

## Run locally

Requires Node.js 20.9+ and npm. Use the committed `package-lock.json` for reproducible installations.

```bash
cd frontend
npm ci
npm run dev
```

Open the URL printed by Next.js (normally http://localhost:3000).

```bash
npm run lint
npm run typecheck
npm run build
npm start
```

## Routes

- `/`: navigation and hero with an animated workflow preview; three resolution stages; five capability cards and final CTA; footer.
- `/rider`: interactive Rider Support prototype with demo identity selection, isolated histories, mock messaging, and dispute/payment details.
- `/ops/login`: demo operator sign-in.
- `/ops`: record-derived overview and analytics.
- `/ops/conversations` and `/ops/conversations/[id]`: a shared support inbox with direct conversation links.
- `/ops/approvals` and `/ops/approvals/[id]`: approval/escalation queues and evidence-based case review.
- `/ops/payouts` and `/ops/payouts/[id]`: payout monitoring, provider attempts, and demo reconciliation.
- `/ops/audit`: searchable sanitized trace explorer and grouped timelines.

Production authentication, backend calls, and payment execution are deferred. All conversations, calculations, statuses, and traces are demonstration data. TanStack Query manages the Rider mock adapter; it makes no real backend requests.

## Organization

- `src/components/landing/`: Navbar, Hero, HeroWorkflowPreview, HowItWorks, Capabilities, FinalCTA, Footer.
- `src/components/shared/`: brand, CTA links, reveal animation, providers, and demo placeholder.
- `src/components/rider/`: responsive workspace, React Query hooks, sidebar/selector, chat/composer, scenario picker, and dispute/payment panels.
- `src/types/rider.ts`: domain models, assignment message contract, and proposed internal UI contracts.
- `src/lib/api/rider.ts` and `src/lib/mock/rider-data.ts`: isolated, typed mock transport and fixtures.
- `src/app/rider/rider.css`: Rider-only styles using the shared dark indigo tokens.
- `src/components/ui/`: generated shadcn/ui primitives.
- `src/app/globals.css`: shared semantic dark-theme tokens, layouts, responsive rules, and reduced-motion overrides.

The page uses lightweight HTML/CSS illustrations and Motion reveals. Aceternity effects were not needed. No image assets, API keys, or environment variables are required. The first production build needs network access to retrieve Google fonts; Next.js serves the resulting font files locally.

shadcn is configured in `components.json`. Add components with `npx shadcn@latest add <component>`. Its CLI is not an application dependency; unused shared CLI CSS was removed to keep the dependency tree small.

Installation note: the current Next.js scaffold selects ESLint 9, which emits a deprecation warning. It is retained because the React lint plugin does not yet declare ESLint 10 compatibility. A fresh `npm ci`, lint, typecheck, and production build all pass; `npm audit` reports zero vulnerabilities.

Stop the development server before running `npm ci`, then restart it afterward. Replacing `node_modules` while Turbopack is running can leave its workers with stale module-resolution state. Local development supports both `localhost` and `127.0.0.1`; the latter is explicitly listed in `allowedDevOrigins` so HMR and browser hydration can connect through that address.


## Rider prototype

Select Imran Khan (R003), Ravi Kumar (R001), or Ramesh Babu (R017), using names/cities from the seeded rider file. Each identity has two sample histories. Start a new conversation to try the composer or explore all six sample scenarios. The sidebar and dispute panel become sheets on mobile. Enter sends, Shift+Enter inserts a newline, and **Test send error** deterministically fails the next submission once so Retry can be exercised.

Messages support AI, Rider, and Human Support senders. Sample payout states distinguish successful confirmations, pending reconciliation, approval requirements, and no adjustment owed. Fixtures are illustrative UI states, not assignment evaluation results or authoritative financial calculations. Demo histories live in browser memory and reset on a full reload; there is no authentication or persistence.

The adapter preserves the exact `POST /messages` request/response shape. Conversation context and simulated failures are separate mock transport options. Replace `getRiders`, `getConversations`, `getConversation`, `getMessages`, and `getDisputes` with the proposed `/ui/...` HTTP endpoints defined in `src/types/rider.ts`. The proposed conversation-event SSE type can replace the current presentation-only processing steps. Conversation creation is also mock-only. No Python endpoints or SSE connection are implemented in this phase.

Run the focused adapter checks without adding a test framework dependency:

```bash
npx --yes tsx --test src/lib/api/rider.test.ts src/lib/api/ops.test.ts
```


## Operations Console

Open `/ops/login`, use any valid demo email and the displayed password `demo-only`. This is public demo access, not a real credential. The operator marker is stored in sessionStorage for navigation continuity. It grants no production authorization; the intended real adapter will use server-managed HttpOnly cookies. Logout removes this marker and the Ops query cache.

The console deliberately keeps evidence, source records, and sanitized payloads behind detail routes, tabs, sheets, and expandable sections. Tables support search, sort, and pagination. New dependencies are TanStack Table 8, Recharts, React Hook Form, Zod, and the Hook Form Zod resolver. Ops uses the existing shadcn primitives and Radix primitives for accessible menus, tooltips, and confirmation dialogs.

`src/lib/api/ops.ts` extends the same `riderApi` instance used by Rider Support. Human replies, handling changes, and dispute/payment state changes update shared records. Internal notes remain private: Rider getters filter them and conversation previews do not expose them. A root adapter subscription invalidates both areas' React Query caches. Current records live in memory: navigate with the app links to retain state; a full reload resets demo data. This is not cross-tab or multi-user real-time synchronization.

`src/types/ops.ts` defines the proposed `/auth/*` and `/ui/ops/*` contracts, alongside shared models for cases, payment intents, provider attempts, traces, operators, and notifications. Replace the auth adapter and Ops snapshot/action transport with real HTTP adapters later. SSE is typed only, not connected. The assignment's `/messages`, `/trace/{rider_id}`, `/ops/pending`, and `/health` backend interfaces are not implemented or modified here.

Financial workflow: approval of the sample ₹425 case creates a pending human-authorized intent, never a successful payment. Rejection requires a reason. Escalation resolution never issues money. An unknown payment stays unresolved until the explicit mock provider ledger supplies an observed outcome. Reconciliation is a sample lookup and there is no unrestricted retry-payout action. Timelines contain observed fixture events, not private model reasoning.

All records, charts, provider health, and notifications are illustrative. No network payment calls occur. Browser UI automation was not run, per the request not to open Chrome; validation uses adapter tests, lint, TypeScript, production build, and direct HTTP route checks.
