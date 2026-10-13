# The Analyst Collective

A daily Industrials briefing covering EV, Automobiles, General Industrials and Aerospace & Defence.
The site itself is static: fast, free to host and secure. Claude drafts the brief every morning,
and you approve it before it goes live.

## How the daily update works (no API cost)

```
06:45 IST  A Claude scheduled task (Cowork) runs in the cloud
           → researches the last 48 hours of public news
           → writes src/data/briefs/YYYY-MM-DD.json, validates it, checks the site builds
           → pushes a branch named brief/YYYY-MM-DD
GitHub     "Open review PR" workflow opens a Pull Request: "📰 Daily brief: YYYY-MM-DD"
You        review it in the GitHub app → tap Merge (or close it to skip the day)
Cloudflare rebuilds the site → live about a minute later
```

The editorial rules Claude follows live in `prompts/daily_brief.md`. Edit that file to change tone, sources or coverage.

## Market charts (sector vs Nifty 50)

Each sector page opens with a chart of that sector against the Nifty 50 (1D, 1M, 6M, 1Y).
Every weekday at **4:00 PM IST** (after NSE closes at 3:30 PM) the GitHub Action
`Market data (4:00 PM IST)` runs `scripts/update_markets.py`, saves `src/data/market-snapshot.json`
and commits it; Cloudflare then rebuilds the site. GitHub's scheduler can start a few minutes late.

- Sector definitions (index or equal-weighted basket of companies) live in `src/data/market-config.json`.
- To refresh manually: GitHub → **Actions** → **Market data (4:00 PM IST)** → **Run workflow**.
- Price data comes from Yahoo Finance's public chart feed and is for information only.

## One-time settings

1. **Let GitHub open PRs:** repo **Settings → Actions → General → Workflow permissions** →
   tick **Allow GitHub Actions to create and approve pull requests** → **Save**.
2. **Hosting:** Cloudflare Pages → Workers & Pages → Create → Pages → Connect to Git → pick this repo →
   framework preset **Astro** (build `npm run build`, output `dist`) → Deploy.
3. **Domain (optional):** Pages project → Custom domains → add your domain.
4. **Access token:** the scheduled task uses a fine-grained token limited to this repo. When it expires,
   create a new one with the same permissions (Contents, Pull requests, Workflows = Read and write) and ask Claude to update the task.

## Day-to-day

| Task | How |
|---|---|
| Approve today's brief | Open the PR in the GitHub mobile app → **Merge** |
| Fix a typo before publishing | In the PR, go to **Files changed** → **⋯ → Edit file** → commit, then merge |
| Skip a day | Close the PR without merging |
| Add a case study | Copy a file in `src/content/case-studies/`, edit it, commit |
| Add a glossary term | Edit `src/data/glossary.json` |
| Add or edit a deal | Edit `src/data/deals.json` (Claude also adds publicly announced deals automatically) |
| Change what Claude writes | Edit `prompts/daily_brief.md` (this is the editorial brief Claude follows) |
| Change the run time | Edit the `cron` line in `.github/workflows/daily-brief.yml` (UTC; IST is UTC+5:30) |

## Where things live

```
src/data/briefs/YYYY-MM-DD.json   one file per daily edition (ticker, key numbers, stories)
src/data/deals.json               public deal tracker
src/data/glossary.json            sector KPIs and deal terms
src/content/case-studies/*.md     case studies (Markdown)
prompts/daily_brief.md            instructions Claude follows each morning
scripts/daily_brief.py            calls Claude, validates output, writes files
.github/workflows/daily-brief.yml schedule and pull request automation
```

## Run locally (optional)
```
npm install
npm run dev                                         # http://localhost:4321
ANTHROPIC_API_KEY=... python scripts/daily_brief.py # draft a brief locally
```

## Built-in guardrails
- The prompt requires **public sources only**, with a link for every item and no invented figures.
- The script drops items without a valid URL and flags advice-like wording ("buy", "target price") for your review.
- Nothing is published until you merge. **Always skim the key numbers before merging.**
- The footer disclaimer and the About page state that content is not investment advice.
- Before launch, get written clearance from your employer's compliance team for outside publishing.

## Roadmap ideas
- Multi-model cross-check: a second model (e.g. GPT or Gemini) re-verifies each number and comments on the PR.
- Email newsletter (Buttondown or Beehiiv) that sends each merged brief.
- Data dashboards: monthly SIAM, FADA and Vahan charts, and trading comps.
- "Ask the Analyst": a chatbot over the archive using a Cloudflare Worker and the Claude API.
