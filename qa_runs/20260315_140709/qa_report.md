# Unimind QA Sweep Report

_Generated: 2026-03-15 14:23:10_
_Cases run: 10 | Alpha-ready: 10 | Failed: 0 | Avg score: 9.7/10_

---

## 1. Executive Summary

**Alpha readiness verdict:** APPROACHING ALPHA
- 10/10 cases passed (100%)
- Average score: 9.7/10
- Total request errors: 0

### Top 5 Recurring Issues

1. **slot 'what_this_is'** — 2 cases (20%)
2. **landing text** — 2 cases (20%)
3. **advantage** — 1 cases (10%)

### What Is Working Well

- API reliability: 10/10 cases completed without request errors
- Baseline generation: most cases produce structural output (avg 9.7/10)
- Landing slot completeness: 8 cases had no landing flags

### Atlas Hypothesis Comparison

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Generation reliability / hanging states | **NOT CONFIRMED — all cases completed** | 0 total request errors across 10 cases |
| Weak product field extraction | **PARTIAL** | 0 cases with product field flags |
| Alternatives often missing | **MIXED** | 0 cases with missing/weak alternatives |
| Generic goal/tone | **MIXED** | 0 cases with generic goal/tone |
| Internal-sounding UX copy | **MIXED** | 0 cases with internal-language UX flags |

---

## 2. Test-by-Test Audit

### Case 01 — qa-case-001 ✓

**Input:** _ok so basically i built this thing for sales teams where instead of them having to manually update their crm notes after every call it just listens and does it automatically. but idk how to explain wh…_

**Extracted Brain:**
- **product:** Sales call note-taking bot for CRM updates
- **icp:** Sales team leaders
- **problem:** Manual CRM note-taking after every sales call is time-consuming and prone to errors
- **category:** Sales productivity tools
- **differentiation:** Automatically transcribes and updates CRM notes in real-time, eliminating manual effort
- **goal:** Streamline sales team workflows and reduce administrative tasks
- **tone:** Practical and efficient

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 96.8s**

### Case 02 — qa-case-002 ✓

**Input:** _we help fintech startups that just raised series A get their compliance docs in order before regulators come knocking. its not legal software exactly its more like a structured process with some AI he…_

**Extracted Brain:**
- **product:** Compliance document organizer for fintech startups
- **icp:** Fintech founders who just raised series A funding
- **problem:** Regulators' unexpected audits cause costly delays in product launches
- **category:** Financial Compliance Support
- **differentiation:** Streamlines the process with AI-powered templates and checklists
- **goal:** Ensure regulatory compliance without disrupting product development
- **tone:** Practical and Proactive

**Brain Weaknesses:**
- advantage: generic phrases detected (['ai-powered'])

**Suggestions:** 1 suggestion(s) provided

**Landing Issues:**
- slot 'what_this_is': generic phrase detected
- landing text: generic phrases ['ai-powered']

**UX:** No flags

**Score: 8/10 | Alpha-ready: YES | Total time: 98.4s**

### Case 03 — qa-case-003 ✓

**Input:** _i made a slack bot that notices when your team is stuck on a decision for too long and gently nudges them to either decide or escalate. honestly hard to explain without showing it_

**Extracted Brain:**
- **product:** Slack bot that detects stuck team decisions
- **icp:** mid-sized project managers
- **problem:** team members get stuck in indecision, causing delays
- **category:** decision facilitation software
- **differentiation:** proactively nudges teams to decide or escalate
- **goal:** keep projects on track by making timely decisions
- **tone:** helpful and timely

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 98.1s**

### Case 04 — qa-case-004 ✓

**Input:** _its a tool for dev agencies to track client feedback across slack, email and loom and turn it into actual task tickets. clients hate linear and jira so this keeps them out of it_

**Extracted Brain:**
- **product:** Slack-based client feedback aggregator with task ticketing
- **icp:** Dev agency project managers
- **problem:** Clients' ad-hoc feedback is lost in Slack, email, and Loom, causing misunderstandings and delayed pr…
- **category:** Client Feedback Management for Dev Agencies
- **differentiation:** Automates task ticket creation from client feedback across multiple channels
- **goal:** Turn client feedback into actionable project tasks without overwhelming clients with Jira or linear …
- **tone:** Practical and efficient

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 104.7s**

### Case 05 — qa-case-005 ✓

**Input:** _enterprise HR teams spend way too long building onboarding plans for each new hire — we automate that based on their role, team and skills gaps. mainly targeting people ops leads at 200-500 person com…_

**Extracted Brain:**
- **product:** AI-powered onboarding plan builder for HR teams
- **icp:** people ops leads at 200-500 person companies
- **problem:** spend too much time building individualized onboarding plans
- **category:** HR onboarding automation
- **differentiation:** builds plans based on role, team and skills gaps
- **goal:** streamline new hire onboarding process
- **tone:** practical and efficient

**Landing Issues:**
- slot 'what_this_is': generic phrase detected
- landing text: generic phrases ['ai-powered']

**UX:** No flags

**Score: 9/10 | Alpha-ready: YES | Total time: 85.5s**

### Case 06 — qa-case-006 ✓

**Input:** _i write cold emails for people but AI-assisted. no not another cold email writer, this one actually researches the prospect and writes it like a human who did their homework not a template_

**Extracted Brain:**
- **product:** AI-assisted cold email writer that researches prospects
- **icp:** venture capital-backed startup founders
- **problem:** can't craft personalized, high-converting emails without sacrificing time
- **category:** cold email writing for VCs and startups
- **differentiation:** writes emails from thorough prospect research, not templates
- **goal:** secure a meeting with the right investor
- **tone:** practical and results-driven

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 91.2s**

### Case 07 — qa-case-007 ✓

**Input:** _subscription tracker but for B2B — it reminds your finance person which SaaS tools your team actually uses vs which ones you're just paying for. built it for myself tbh_

**Extracted Brain:**
- **product:** SaaS tool tracker that reconciles usage with invoices
- **icp:** B2B finance professionals
- **problem:** can't accurately track which SaaS tools their team is actively using
- **category:** SaaS expense management
- **differentiation:** automatically matches invoices to actual usage, not just tracking expenses
- **goal:** maximize ROI by optimizing SaaS tool utilization
- **tone:** practical and organized

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 90.3s**

### Case 08 — qa-case-008 ✓

**Input:** _built a thing that turns long meeting recordings into short opinionated summaries. like it doesnt just transcribe — it tells you what decisions were made and who owns what_

**Extracted Brain:**
- **product:** meeting summarization software tool for executives and team leaders
- **icp:** executives and team leaders
- **problem:** waste time reading through lengthy meeting recordings to identify key decisions and action items
- **category:** meeting summarization software
- **differentiation:** provides actionable insights and ownership assignments, not just transcription
- **goal:** make informed decisions quickly
- **tone:** practical and concise

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 87.1s**

### Case 09 — qa-case-009 ✓

**Input:** _newsletter ghostwriting for founders who have the ideas but cant sit down and write. i use AI but heavily edited. package is 4 posts per month for like $800_

**Extracted Brain:**
- **product:** Newsletter ghostwriter that crafts engaging articles from founder ideas
- **icp:** founders of early-stage startups
- **problem:** struggle to find time to write compelling newsletters
- **category:** newsletter writing services for founders
- **differentiation:** heavily edited AI-generated content tailored to founder's voice
- **goal:** establish thought leadership through consistent and high-quality newsletters
- **tone:** practical and supportive

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 88.9s**

### Case 10 — qa-case-010 ✓

**Input:** _i'm trying to turn my notion consulting practice into a productized service but i dont know how to say what the outcome is on a landing page without it sounding like every other notion consultant_

**Extracted Brain:**
- **product:** Customized Notion template builder for consultants
- **icp:** Notion consulting practitioners
- **problem:** struggle to standardize their workflow and deliver consistent results
- **category:** Notion templates for consultants
- **differentiation:** builds customized templates from a structured brief, not generic ones
- **goal:** streamline their consulting process
- **tone:** practical and organized

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 92.5s**

---

## 3. Pattern Analysis

### Most Frequently Weak Brain Fields

- **advantage**: 1 cases (10%)

### Most Common Missing / Poor Suggestion Types

- No pattern-level suggestion issues detected

### Weakest Landing Page Slots

- **what_this_is**: 2 failures (20%)

### Weakest UX Slots

- No slot-level UX failures detected

### Recurring Generic Phrases

- `ai-powered`: 2 cases (20%)

### Score Distribution

| Score | Cases |
|---|---|
| 10/10 | 8 |
| 9/10 | 1 |
| 8/10 | 1 |

### Most Common Failure Modes

- No request errors (API layer is reliable)

---

## 4. Priority Fixes

### Must Fix Before Alpha

- No critical issues found in > 30% of cases (review individual failures)

### Should Fix Soon

- **slot 'what_this_is'** (2 cases, 20%)
- **landing text** (2 cases, 20%)

### Nice to Have Later

- **advantage** (1 cases)

---

## 5. Recommended Next Action

> **Single highest-leverage fix:** Address `slot 'what_this_is'` — this is the most recurring failure pattern and has downstream impact on both landing and UX output quality.

Fix the root cause in `/idea` extraction before improving generation quality — garbage-in garbage-out applies directly here.
