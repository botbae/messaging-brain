# Unimind QA Sweep Report

_Generated: 2026-03-15 13:16:30_
_Cases run: 10 | Alpha-ready: 10 | Failed: 0 | Avg score: 9.1/10_

---

## 1. Executive Summary

**Alpha readiness verdict:** APPROACHING ALPHA
- 10/10 cases passed (100%)
- Average score: 9.1/10
- Total request errors: 0

### Top 5 Recurring Issues

1. **slot 'secondary_cta'** — 9 cases (90%)
2. **slot 'primary_cta'** — 7 cases (70%)
3. **landing text** — 2 cases (20%)
4. **advantage** — 1 cases (10%)

### What Is Working Well

- API reliability: 10/10 cases completed without request errors
- Baseline generation: most cases produce structural output (avg 9.1/10)
- Landing slot completeness: 8 cases had no landing flags

### Atlas Hypothesis Comparison

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Generation reliability / hanging states | **NOT CONFIRMED — all cases completed** | 0 total request errors across 10 cases |
| Weak product field extraction | **PARTIAL** | 0 cases with product field flags |
| Alternatives often missing | **MIXED** | 0 cases with missing/weak alternatives |
| Generic goal/tone | **MIXED** | 0 cases with generic goal/tone |
| Internal-sounding UX copy | **CONFIRMED** | 16 cases with internal-language UX flags |

---

## 2. Test-by-Test Audit

### Case 01 — qa-case-001 ✓

**Input:** _ok so basically i built this thing for sales teams where instead of them having to manually update their crm notes after every call it just listens and does it automatically. but idk how to explain wh…_

**Extracted Brain:**
- **product:** Automated CRM note-taking bot for sales teams
- **icp:** Sales team leaders and reps
- **problem:** Manually updating CRM notes after every call is time-consuming and prone to errors
- **category:** Sales productivity tools
- **differentiation:** Listens in on calls to automatically update CRM notes, no manual input required
- **goal:** Streamline sales team workflows and reduce administrative tasks
- **tone:** Practical and efficient

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 94.3s**

### Case 02 — qa-case-002 ✓

**Input:** _we help fintech startups that just raised series A get their compliance docs in order before regulators come knocking. its not legal software exactly its more like a structured process with some AI he…_

**Extracted Brain:**
- **product:** Compliance document organizer for fintech startups
- **icp:** Fintech startup founders who just raised series A funding
- **problem:** Regulators' surprise audits put compliance in disarray, causing delays and fines
- **category:** Financial Compliance Support
- **differentiation:** Streamlines the process with AI-assisted templates and expert guidance
- **goal:** Ensure regulatory compliance without disrupting business operations
- **tone:** Practical and Proactive

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 102.9s**

### Case 03 — qa-case-003 ✓

**Input:** _i made a slack bot that notices when your team is stuck on a decision for too long and gently nudges them to either decide or escalate. honestly hard to explain without showing it_

**Extracted Brain:**
- **product:** Slack bot that detects stuck decision-making
- **icp:** Product managers in software development teams
- **problem:** Decision paralysis leads to delayed project timelines
- **category:** Collaboration workflow management
- **differentiation:** Gently nudges teams towards resolution, rather than dictating a solution
- **goal:** Enable informed decision-making and timely project progress
- **tone:** Practical and supportive

**Brain Weaknesses:**
- advantage: generic phrases detected ([' solution'])

**Landing Issues:**
- landing text: generic phrases [' solution']

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 96.6s**

### Case 04 — qa-case-004 ✓

**Input:** _its a tool for dev agencies to track client feedback across slack, email and loom and turn it into actual task tickets. clients hate linear and jira so this keeps them out of it_

**Extracted Brain:**
- **product:** Slack-based client feedback aggregator for dev agencies
- **icp:** Dev agency owners and project managers
- **problem:** Clients' ad-hoc feedback is lost in Slack, email, or Loom, leading to misunderstandings and delayed …
- **category:** Client feedback management for dev agencies
- **differentiation:** Automatically converts client feedback into actionable task tickets, eliminating manual data entry
- **goal:** Turn client feedback into actionable tasks without overwhelming clients with Jira or linear workflow…
- **tone:** Practical and efficient

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 105.0s**

### Case 05 — qa-case-005 ✓

**Input:** _enterprise HR teams spend way too long building onboarding plans for each new hire — we automate that based on their role, team and skills gaps. mainly targeting people ops leads at 200-500 person com…_

**Extracted Brain:**
- **product:** onboarding automation software tool for people ops leads at 200-500 person companies
- **icp:** people ops leads at 200-500 person companies
- **problem:** spend too much time building individualized onboarding plans
- **category:** onboarding automation software
- **differentiation:** builds plans based on role, team and skills gaps
- **goal:** streamline new hire onboarding process
- **tone:** practical and efficient

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 94.9s**

### Case 06 — qa-case-006 ✓

**Input:** _i write cold emails for people but AI-assisted. no not another cold email writer, this one actually researches the prospect and writes it like a human who did their homework not a template_

**Extracted Brain:**
- **product:** AI-assisted cold email writer that researches prospects
- **icp:** venture-backed startup founders
- **problem:** cold emails lack personalization and relevance
- **category:** research-driven cold outreach
- **differentiation:** writes personalized emails based on prospect research, not templates
- **goal:** generate a high-converting cold email campaign
- **tone:** practical and results-oriented

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 10/10 | Alpha-ready: YES | Total time: 87.4s**

### Case 07 — qa-case-007 ✓

**Input:** _subscription tracker but for B2B — it reminds your finance person which SaaS tools your team actually uses vs which ones you're just paying for. built it for myself tbh_

**Extracted Brain:**
- **product:** SaaS tool usage tracker for finance teams
- **icp:** B2B finance professionals
- **problem:** can't accurately track which SaaS tools their team is actively using
- **category:** SaaS expense management
- **differentiation:** integrates with existing accounting software to automate tracking
- **goal:** maximize ROI by optimizing SaaS tool usage
- **tone:** practical and organized

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 93.2s**

### Case 08 — qa-case-008 ✓

**Input:** _built a thing that turns long meeting recordings into short opinionated summaries. like it doesnt just transcribe — it tells you what decisions were made and who owns what_

**Extracted Brain:**
- **product:** meeting summarization software tool for executives and team leaders
- **icp:** executives and team leaders
- **problem:** wasting time reviewing lengthy meeting recordings to extract key decisions
- **category:** meeting summarization software
- **differentiation:** provides actionable insights on who owns what and what decisions were made
- **goal:** make informed decisions quickly
- **tone:** practical and informative

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 86.2s**

### Case 09 — qa-case-009 ✓

**Input:** _newsletter ghostwriting for founders who have the ideas but cant sit down and write. i use AI but heavily edited. package is 4 posts per month for like $800_

**Extracted Brain:**
- **product:** AI-powered newsletter ghostwriter for busy founders
- **icp:** founders with innovative ideas but no time to write
- **problem:** struggle to consistently produce engaging newsletters without sacrificing quality or sanity
- **category:** newsletter writing services for entrepreneurs
- **differentiation:** heavily edited AI-generated content tailored to each founder's unique voice and style
- **goal:** deliver high-quality, engaging newsletters that build trust with their audience
- **tone:** practical and supportive

**Landing Issues:**
- landing text: generic phrases ['ai-powered']

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 94.5s**

### Case 10 — qa-case-010 ✓

**Input:** _i'm trying to turn my notion consulting practice into a productized service but i dont know how to say what the outcome is on a landing page without it sounding like every other notion consultant_

**Extracted Brain:**
- **product:** Customized Notion setup service for consultants
- **icp:** Notion consultants
- **problem:** struggle to standardize their consulting process
- **category:** Notion setup services
- **differentiation:** tailored to the consultant's unique needs and workflow
- **goal:** streamline their consulting practice
- **tone:** practical and supportive

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 93.4s**

---

## 3. Pattern Analysis

### Most Frequently Weak Brain Fields

- **advantage**: 1 cases (10%)

### Most Common Missing / Poor Suggestion Types

- No pattern-level suggestion issues detected

### Weakest Landing Page Slots

- No slot-level failures detected

### Weakest UX Slots

- **secondary_cta**: 9 failures (90%)
- **primary_cta**: 7 failures (70%)

### Recurring Generic Phrases

- ` solution`: 1 cases (10%)
- `ai-powered`: 1 cases (10%)

### Score Distribution

| Score | Cases |
|---|---|
| 10/10 | 2 |
| 9/10 | 7 |
| 8/10 | 1 |

### Most Common Failure Modes

- No request errors (API layer is reliable)

---

## 4. Priority Fixes

### Must Fix Before Alpha

- **slot 'secondary_cta'** (9 cases, 90%)
- **slot 'primary_cta'** (7 cases, 70%)

### Should Fix Soon

- **landing text** (2 cases, 20%)

### Nice to Have Later

- **advantage** (1 cases)

---

## 5. Recommended Next Action

> **Single highest-leverage fix:** Address `slot 'secondary_cta'` — this is the most recurring failure pattern and has downstream impact on both landing and UX output quality.

Fix the root cause in `/idea` extraction before improving generation quality — garbage-in garbage-out applies directly here.
