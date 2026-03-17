# Unimind QA Sweep Report

_Generated: 2026-03-15 02:02:52_
_Cases run: 10 | Alpha-ready: 10 | Failed: 0 | Avg score: 8.3/10_

---

## 1. Executive Summary

**Alpha readiness verdict:** APPROACHING ALPHA
- 10/10 cases passed (100%)
- Average score: 8.3/10
- Total request errors: 0

### Top 5 Recurring Issues

1. **product** — 10 cases (100%)
2. **slot 'secondary_cta'** — 10 cases (100%)
3. **slot 'primary_cta'** — 7 cases (70%)

### What Is Working Well

- API reliability: 10/10 cases completed without request errors
- Baseline generation: most cases produce structural output (avg 8.3/10)
- Landing slot completeness: 10 cases had no landing flags

### Atlas Hypothesis Comparison

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Generation reliability / hanging states | **NOT CONFIRMED — all cases completed** | 0 total request errors across 10 cases |
| Weak product field extraction | **CONFIRMED** | 10 cases with product field flags |
| Alternatives often missing | **MIXED** | 0 cases with missing/weak alternatives |
| Generic goal/tone | **MIXED** | 0 cases with generic goal/tone |
| Internal-sounding UX copy | **CONFIRMED** | 17 cases with internal-language UX flags |

---

## 2. Test-by-Test Audit

### Case 01 — qa-case-001 ✓

**Input:** _ok so basically i built this thing for sales teams where instead of them having to manually update their crm notes after every call it just listens and does it automatically. but idk how to explain wh…_

**Extracted Brain:**
- **icp:** Sales Team Leads
- **problem:** Manually updating CRM notes after every call is time-consuming and prone to errors
- **category:** Automated CRM Note Taker
- **differentiation:** Listens to calls in real-time, accurately capturing key information without manual input
- **goal:** Streamline sales team workflows with accurate and up-to-date CRM notes
- **tone:** Practical and Efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 143.7s**

### Case 02 — qa-case-002 ✓

**Input:** _we help fintech startups that just raised series A get their compliance docs in order before regulators come knocking. its not legal software exactly its more like a structured process with some AI he…_

**Extracted Brain:**
- **icp:** Series A fintech startup founders
- **problem:** Regulators' surprise audits put compliance at risk
- **category:** Compliance Document Organizer
- **differentiation:** Streamlines process with AI-assisted templates
- **goal:** Ensure regulatory readiness before audit
- **tone:** Practical and reassuring

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 90.5s**

### Case 03 — qa-case-003 ✓

**Input:** _i made a slack bot that notices when your team is stuck on a decision for too long and gently nudges them to either decide or escalate. honestly hard to explain without showing it_

**Extracted Brain:**
- **icp:** team leads in software development
- **problem:** stale discussions causing project delays
- **category:** decision facilitation bot for teams
- **differentiation:** proactively nudges to action, doesn't just summarize
- **goal:** get projects back on track with timely decisions
- **tone:** friendly and encouraging

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 98.5s**

### Case 04 — qa-case-004 ✓

**Input:** _its a tool for dev agencies to track client feedback across slack, email and loom and turn it into actual task tickets. clients hate linear and jira so this keeps them out of it_

**Extracted Brain:**
- **icp:** Dev agency owners
- **problem:** Manually tracking client feedback across multiple channels
- **category:** Client Feedback Manager
- **differentiation:** Automates task ticket creation from diverse feedback sources
- **goal:** Streamline client communication and project management
- **tone:** Practical and Efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 100.3s**

### Case 05 — qa-case-005 ✓

**Input:** _enterprise HR teams spend way too long building onboarding plans for each new hire — we automate that based on their role, team and skills gaps. mainly targeting people ops leads at 200-500 person com…_

**Extracted Brain:**
- **icp:** People Ops Leads
- **problem:** Manual onboarding plan creation takes too much time
- **category:** HR Onboarding Automation
- **differentiation:** Automates plans based on role, team, and skills gaps
- **goal:** Streamline new hire integration
- **tone:** Practical and Efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 107.2s**

### Case 06 — qa-case-006 ✓

**Input:** _i write cold emails for people but AI-assisted. no not another cold email writer, this one actually researches the prospect and writes it like a human who did their homework not a template_

**Extracted Brain:**
- **icp:** ambitious startup marketers
- **problem:** can't craft compelling cold emails without wasting time on research
- **category:** AI-assisted cold email writer
- **differentiation:** combines AI with human-written content based on prospect profiles
- **goal:** generate high-quality leads for early-stage startups
- **tone:** practical and results-driven

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 104.2s**

### Case 07 — qa-case-007 ✓

**Input:** _subscription tracker but for B2B — it reminds your finance person which SaaS tools your team actually uses vs which ones you're just paying for. built it for myself tbh_

**Extracted Brain:**
- **icp:** B2B finance professionals
- **problem:** waste money on unused SaaS subscriptions
- **category:** SaaS subscription trackers
- **differentiation:** provides actionable insights for cost optimization
- **goal:** maximize ROI by identifying unused tools
- **tone:** practical and analytical

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 80.2s**

### Case 08 — qa-case-008 ✓

**Input:** _built a thing that turns long meeting recordings into short opinionated summaries. like it doesnt just transcribe — it tells you what decisions were made and who owns what_

**Extracted Brain:**
- **icp:** founder-CEOs of scaling startups
- **problem:** long meeting recordings are overwhelming and unclear on key decisions
- **category:** meeting summary generator
- **differentiation:** identifies key takeaways and action items from meetings
- **goal:** make strategic business decisions with clarity
- **tone:** practical and concise

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 103.7s**

### Case 09 — qa-case-009 ✓

**Input:** _newsletter ghostwriting for founders who have the ideas but cant sit down and write. i use AI but heavily edited. package is 4 posts per month for like $800_

**Extracted Brain:**
- **icp:** founder-entrepreneurs with ideas
- **problem:** struggle to articulate their vision into engaging content
- **category:** newsletter ghostwriting for founders
- **differentiation:** combines AI-generated content with human editing expertise
- **goal:** establish thought leadership and drive website traffic
- **tone:** practical and results-driven

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 117.0s**

### Case 10 — qa-case-010 ✓

**Input:** _i'm trying to turn my notion consulting practice into a productized service but i dont know how to say what the outcome is on a landing page without it sounding like every other notion consultant_

**Extracted Brain:**
- **icp:** Notion consultants seeking productization
- **problem:** struggling to articulate the value of their services
- **category:** Notion-based consulting services
- **differentiation:** uses Notion's structure to clarify complex concepts
- **goal:** secure a steady stream of clients
- **tone:** practical and consultative

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 109.1s**

---

## 3. Pattern Analysis

### Most Frequently Weak Brain Fields

- **product**: 10 cases (100%)

### Most Common Missing / Poor Suggestion Types

- No pattern-level suggestion issues detected

### Weakest Landing Page Slots

- No slot-level failures detected

### Weakest UX Slots

- **secondary_cta**: 10 failures (100%)
- **primary_cta**: 7 failures (70%)

### Recurring Generic Phrases

- No widespread generic phrases detected

### Score Distribution

| Score | Cases |
|---|---|
| 9/10 | 3 |
| 8/10 | 7 |

### Most Common Failure Modes

- No request errors (API layer is reliable)

---

## 4. Priority Fixes

### Must Fix Before Alpha

- **product** (10 cases, 100%)
- **slot 'secondary_cta'** (10 cases, 100%)
- **slot 'primary_cta'** (7 cases, 70%)

### Should Fix Soon

- No high-frequency issues in 15–30% range

### Nice to Have Later

- N/A

---

## 5. Recommended Next Action

> **Single highest-leverage fix:** Address `product` — this is the most recurring failure pattern across all 50 cases and has downstream impact on both landing and UX output quality.

Fix the root cause in `/idea` extraction before improving generation quality — garbage-in garbage-out applies directly here.
