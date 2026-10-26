# ModelRail Dashboard

Next.js (App Router) + TypeScript administration UI for the ModelRail gateway.

## Run

```bash
cp .env.example .env   # NEXT_PUBLIC_MODELRAIL_API_URL, default http://localhost:8000
npm install
npm run dev            # http://localhost:3000
```

Or with Docker: `docker build -t modelrail-dashboard . && docker run -p 3000:3000 modelrail-dashboard`

Enter your admin token in the header (sent as `X-Admin-Token`, stored only in
localStorage). Pages: Overview, Models & Routes, Projects & Keys (one-time key
display), Requests (attempt timeline), Usage & Budgets, Evaluations
(regression gate report).

UI components in `components/ui/` are hand-written shadcn-style components
(Button, Card, Input, Table) using Tailwind CSS 4 — no shadcn CLI generation.
