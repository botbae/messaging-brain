# Unimind QA Sweep Report

_Generated: 2026-03-15 03:38:13_
_Cases run: 50 | Alpha-ready: 50 | Failed: 0 | Avg score: 8.5/10_

---

## 1. Executive Summary

**Alpha readiness verdict:** APPROACHING ALPHA
- 50/50 cases passed (100%)
- Average score: 8.5/10
- Total request errors: 0

### Top 5 Recurring Issues

1. **product** — 50 cases (100%)
2. **slot 'secondary_cta'** — 45 cases (90%)
3. **slot 'primary_cta'** — 24 cases (48%)
4. **slot 'what_this_is'** — 5 cases (10%)
5. **landing text** — 5 cases (10%)

### What Is Working Well

- API reliability: 50/50 cases completed without request errors
- Baseline generation: most cases produce structural output (avg 8.5/10)
- Landing slot completeness: 43 cases had no landing flags

### Atlas Hypothesis Comparison

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Generation reliability / hanging states | **NOT CONFIRMED — all cases completed** | 0 total request errors across 50 cases |
| Weak product field extraction | **CONFIRMED** | 50 cases with product field flags |
| Alternatives often missing | **MIXED** | 0 cases with missing/weak alternatives |
| Generic goal/tone | **MIXED** | 0 cases with generic goal/tone |
| Internal-sounding UX copy | **CONFIRMED** | 69 cases with internal-language UX flags |

---

## 2. Test-by-Test Audit

### Case 01 — qa-case-001 ✓

**Input:** _ok so basically i built this thing for sales teams where instead of them having to manually update their crm notes after every call it just listens and does it automatically. but idk how to explain wh…_

**Extracted Brain:**
- **icp:** Sales Team Leads
- **problem:** Manually updating CRM notes after every call is time-consuming and prone to errors.
- **category:** Automated CRM Note Takers
- **differentiation:** Listens and transcribes calls in real-time, eliminating manual data entry.
- **goal:** Streamline sales team workflows
- **tone:** Practical and Efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 84.5s**

### Case 02 — qa-case-002 ✓

**Input:** _we help fintech startups that just raised series A get their compliance docs in order before regulators come knocking. its not legal software exactly its more like a structured process with some AI he…_

**Extracted Brain:**
- **icp:** Series A fintech startup founders
- **problem:** Regulators demand compliance documentation without clear templates
- **category:** Compliance Document Organizer
- **differentiation:** Streamlines process with AI-assisted template guidance
- **goal:** Get regulatory-ready in weeks, not months
- **tone:** Practical and Confident

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 82.2s**

### Case 03 — qa-case-003 ✓

**Input:** _i made a slack bot that notices when your team is stuck on a decision for too long and gently nudges them to either decide or escalate. honestly hard to explain without showing it_

**Extracted Brain:**
- **icp:** team leads in software development
- **problem:** stale discussions lead to delayed project timelines
- **category:** decision facilitation bot for teams
- **differentiation:** proactively suggests next steps, not just nudges
- **goal:** reach a timely decision with minimal friction
- **tone:** practical and supportive

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 81.2s**

### Case 04 — qa-case-004 ✓

**Input:** _its a tool for dev agencies to track client feedback across slack, email and loom and turn it into actual task tickets. clients hate linear and jira so this keeps them out of it_

**Extracted Brain:**
- **icp:** Dev agency owners
- **problem:** Client feedback gets lost in Slack, email, and Loom
- **category:** Client Feedback Management
- **differentiation:** Automates task ticket creation from client feedback
- **goal:** Turn client feedback into actionable tasks
- **tone:** Practical and Efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 81.2s**

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

**Score: 8/10 | Alpha-ready: YES | Total time: 85.3s**

### Case 06 — qa-case-006 ✓

**Input:** _i write cold emails for people but AI-assisted. no not another cold email writer, this one actually researches the prospect and writes it like a human who did their homework not a template_

**Extracted Brain:**
- **icp:** ambitious startup entrepreneurs
- **problem:** can't craft compelling cold emails without wasting time on research
- **category:** AI-assisted cold email writer for founders
- **differentiation:** combines AI-driven insights with human-written content
- **goal:** generate a high-converting cold email campaign
- **tone:** practical and results-oriented

**Brain Weaknesses:**
- product: empty

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 85.3s**

### Case 07 — qa-case-007 ✓

**Input:** _subscription tracker but for B2B — it reminds your finance person which SaaS tools your team actually uses vs which ones you're just paying for. built it for myself tbh_

**Extracted Brain:**
- **icp:** B2B finance professionals
- **problem:** waste money on unused SaaS subscriptions
- **category:** SaaS subscription tracker
- **differentiation:** tracks actual usage, not just invoices
- **goal:** optimize subscription spend
- **tone:** practical and analytical

**Brain Weaknesses:**
- product: empty

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 79.5s**

### Case 08 — qa-case-008 ✓

**Input:** _built a thing that turns long meeting recordings into short opinionated summaries. like it doesnt just transcribe — it tells you what decisions were made and who owns what_

**Extracted Brain:**
- **icp:** busy startup CEOs
- **problem:** meetings are too long, decisions unclear
- **category:** meeting summary software
- **differentiation:** identifies key takeaways and action items
- **goal:** make strategic decisions faster
- **tone:** practical and concise

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 80.3s**

### Case 09 — qa-case-009 ✓

**Input:** _newsletter ghostwriting for founders who have the ideas but cant sit down and write. i use AI but heavily edited. package is 4 posts per month for like $800_

**Extracted Brain:**
- **icp:** founder-entrepreneurs with ideas to share
- **problem:** struggle to articulate their vision in engaging newsletters
- **category:** newsletter ghostwriting for founders
- **differentiation:** combines AI-generated content with human editing expertise
- **goal:** establish thought leadership through consistent newsletter publishing
- **tone:** practical and supportive

**Brain Weaknesses:**
- product: empty

**Landing Issues:**
- slot 'why_current_options_fail': generic phrase detected

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 88.0s**

### Case 10 — qa-case-010 ✓

**Input:** _i'm trying to turn my notion consulting practice into a productized service but i dont know how to say what the outcome is on a landing page without it sounding like every other notion consultant_

**Extracted Brain:**
- **icp:** Notion consultants seeking productization
- **problem:** struggle to articulate their service's value proposition
- **category:** Notion-based consulting services
- **differentiation:** structures Notion templates for clarity, not just notes
- **goal:** deliver a productized service that resonates
- **tone:** practical and consultative

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 83.5s**

### Case 11 — qa-case-011 ✓

**Input:** _we're a small design studio that specializes in SaaS onboarding flows. we've shipped 30+ products and we know what works but our website looks like a generic design agency_

**Extracted Brain:**
- **icp:** SaaS founders seeking clarity
- **problem:** struggle to articulate their value proposition
- **category:** onboarding flow copywriting
- **differentiation:** uses design studio expertise to craft compelling narratives
- **goal:** launch a website that resonates with target audience
- **tone:** confident and consultative

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 81.4s**

### Case 12 — qa-case-012 ✓

**Input:** _brand strategy for early stage startups — mostly helping founders who just got funded figure out their positioning before they build their website. 6 week engagement_

**Extracted Brain:**
- **icp:** first-time SaaS founders
- **problem:** struggle to articulate their unique value proposition
- **category:** startup positioning services
- **differentiation:** uses proprietary framework for clarity and focus
- **goal:** define a compelling brand story
- **tone:** practical and consultative

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing Issues:**
- slot 'what_this_is': empty

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 81.9s**

### Case 13 — qa-case-013 ✓

**Input:** _fractional CMO for B2B SaaS companies between $1M and $5M ARR. not content marketing, actual strategy — ICP, messaging, channel mix_

**Extracted Brain:**
- **icp:** B2B SaaS founders $1M-$5M ARR
- **problem:** struggle to articulate their unique value proposition
- **category:** CMO strategy consultant for B2B SaaS
- **differentiation:** develops tailored positioning strategies from deep market research
- **goal:** define a compelling value proposition that drives growth
- **tone:** practical and results-driven

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 88.3s**

### Case 14 — qa-case-014 ✓

**Input:** _we do conversion rate optimization for ecom brands. specifically focused on the checkout and post-purchase experience. most CRO agencies do the landing page we do the bottom of funnel_

**Extracted Brain:**
- **icp:** ecommerce store owners
- **problem:** struggle to optimize the checkout process for abandoned carts
- **category:** checkout optimization services
- **differentiation:** specializes in post-purchase experience improvement
- **goal:** minimize cart abandonment and increase revenue
- **tone:** practical and analytical

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 82.9s**

### Case 15 — qa-case-015 ✓

**Input:** _technical SEO agency. we go into big legacy sites and fix the crawl architecture, site speed, schema and internal linking. the kind of work that moves the needle for enterprise clients but most SEO ag…_

**Extracted Brain:**
- **icp:** Enterprise Marketing Directors
- **problem:** Legacy website architecture hinders search engine crawlability and ranking
- **category:** Technical SEO Services
- **differentiation:** Expertly optimizes complex websites for improved crawlability and ranking
- **goal:** Maximize organic traffic and conversion rates
- **tone:** Practical and Expert

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 68.7s**

### Case 16 — qa-case-016 ✓

**Input:** _i'm a PMM at a big company building a side product that helps startup founders write their investor update emails faster. i have a template but i want to turn it into a proper product_

**Extracted Brain:**
- **icp:** venture-backed startup founders
- **problem:** struggle to craft compelling investor updates on time
- **category:** investor email writer for startups
- **differentiation:** uses AI-powered template with customizable fields
- **goal:** secure funding with confidence
- **tone:** practical and supportive

**Brain Weaknesses:**
- product: empty
- advantage: generic phrases detected (['ai-powered'])

**Suggestions:** 1 suggestion(s) provided

**Landing Issues:**
- slot 'what_this_is': generic phrase detected
- landing text: generic phrases ['ai-powered']

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 76.6s**

### Case 17 — qa-case-017 ✓

**Input:** _competitive battlecards SaaS. sales reps waste time finding and updating battlecards — ours auto-updates from product changelogs, G2 reviews and sales call transcripts_

**Extracted Brain:**
- **icp:** sales reps in software companies
- **problem:** waste time finding and updating battlecards manually
- **category:** battlecard generator for sales teams
- **differentiation:** auto-updates from product changelogs, G2 reviews, and sales call transcripts
- **goal:** save time and improve sales performance
- **tone:** practical and efficient

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 84.8s**

### Case 18 — qa-case-018 ✓

**Input:** _customer story toolkit — helps PMMs collect, format and publish customer case studies faster. the bottleneck is always chasing the customer for a quote and the approval process_

**Extracted Brain:**
- **icp:** PMMs in software companies
- **problem:** struggle to get timely customer quotes for case studies
- **category:** customer story formatting tool
- **differentiation:** pre-populates templates with customer data, not manual input
- **goal:** publish a high-quality case study within hours
- **tone:** practical and efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 82.6s**

### Case 19 — qa-case-019 ✓

**Input:** _i built an internal wiki tool specifically for remote customer success teams. not confluence, not notion — designed specifically for the CSM workflow with templates built in_

**Extracted Brain:**
- **icp:** remote customer success managers
- **problem:** manually updating knowledge bases causes delays
- **category:** internal wiki tool for CSMs
- **differentiation:** pre-built templates streamline workflow optimization
- **goal:** quickly access relevant information to resolve customer issues
- **tone:** practical and organized

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 76.6s**

### Case 20 — qa-case-020 ✓

**Input:** _we make pitch deck teardowns as a service. you send us your deck we come back with a written audit in 48 hours. $299 flat. thinking about how to position this for post-seed founders_

**Extracted Brain:**
- **icp:** post-seed startup founders
- **problem:** struggle to articulate their unique value proposition
- **category:** pitch deck teardowns
- **differentiation:** provides actionable feedback in 48 hours, not vague insights
- **goal:** secure funding with confidence
- **tone:** practical and constructive

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 82.1s**

### Case 21 — qa-case-021 ✓

**Input:** _an app for people who want to invest in index funds but are anxious about timing — it helps them stick to a DCA plan by hiding the noise and just showing them what to do next_

**Extracted Brain:**
- **icp:** retail investors
- **problem:** constantly checking market fluctuations, second-guessing investment decisions
- **category:** index fund investment tracker
- **differentiation:** simplifies the process with clear next steps, eliminating emotional decision-making
- **goal:** achieve long-term financial stability
- **tone:** calm and reassuring

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 79.5s**

### Case 22 — qa-case-022 ✓

**Input:** _fitness app but specifically for people who travel a lot for work and can only work out in hotel rooms or airports. the plans adjust automatically based on what you have available_

**Extracted Brain:**
- **icp:** frequent business travelers
- **problem:** can't fit in workouts due to limited space and equipment
- **category:** hotel room workout app
- **differentiation:** adapts to available space with AI-powered exercises
- **goal:** stay healthy on the road
- **tone:** practical and motivational

**Brain Weaknesses:**
- product: empty
- advantage: generic phrases detected (['ai-powered'])

**Suggestions:** 1 suggestion(s) provided

**Landing Issues:**
- slot 'what_this_is': generic phrase detected
- landing text: generic phrases ['ai-powered']

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 85.1s**

### Case 23 — qa-case-023 ✓

**Input:** _a journaling app that actually helps you process anxiety not just dump thoughts. it prompts you based on CBT patterns but doesnt feel clinical or like therapy homework_

**Extracted Brain:**
- **icp:** anxious individuals seeking mental clarity
- **problem:** struggle to organize and make sense of racing thoughts
- **category:** digital journaling apps
- **differentiation:** employs CBT-based prompts for anxiety processing, not just note-taking
- **goal:** achieve a sense of calm and control
- **tone:** warm and practical

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 83.0s**

### Case 24 — qa-case-024 ✓

**Input:** _recipe app for people who have exactly 20 minutes, whatever is in their fridge, and a toddler underfoot. not another pinterest but actually fast and practical_

**Extracted Brain:**
- **icp:** busy parents with toddlers
- **problem:** can't find a recipe that uses ingredients they have on hand in under 20 minutes
- **category:** quick meal planning app
- **differentiation:** generates recipes based on fridge contents and cooking time constraints
- **goal:** serve a healthy meal without stress
- **tone:** practical and encouraging

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 87.4s**

### Case 25 — qa-case-025 ✓

**Input:** _subscription box for small batch specialty coffee but the twist is it adapts to your palate over time — you rate each bag and the selections get better. built by a former barista_

**Extracted Brain:**
- **icp:** coffee connoisseurs seeking variety
- **problem:** can't find specialty coffee that consistently meets their taste preferences
- **category:** specialty coffee subscription box
- **differentiation:** adapts to your palate through user ratings and feedback
- **goal:** discover new favorite specialty coffees
- **tone:** curated and knowledgeable

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 73.6s**

### Case 26 — qa-case-026 ✓

**Input:** _we built an internal tool at our agency for tracking proposal statuses across email, notion and our PM tool. it got out of hand and now we want to sell it to other agencies_

**Extracted Brain:**
- **icp:** agency operations managers
- **problem:** manually tracking proposal statuses across multiple tools is time-consuming and error-prone
- **category:** proposal status tracker
- **differentiation:** integrates with popular agency tools, not just email and Notion
- **goal:** streamline proposal tracking to reduce administrative burdens
- **tone:** practical and efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 85.4s**

### Case 27 — qa-case-027 ✓

**Input:** _used to manually QA our design handoffs against Figma specs. built an internal script that does it automatically. now we want to productize it for design-dev teams_

**Extracted Brain:**
- **icp:** design-dev team leads
- **problem:** manually verifying design handoffs is time-consuming and prone to errors
- **category:** design QA automation
- **differentiation:** integrates with Figma, not just a generic design validation tool
- **goal:** ensure accurate and timely design implementation
- **tone:** practical and efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 88.7s**

### Case 28 — qa-case-028 ✓

**Input:** _a dashboard for founder-led sales — shows you which deals went cold and why, based on email thread analysis. built it because we were losing deals and couldnt figure out the pattern_

**Extracted Brain:**
- **icp:** founder-led sales teams
- **problem:** deals go cold due to unclear communication
- **category:** sales performance dashboard
- **differentiation:** analyzes email threads to identify patterned issues
- **goal:** identify and address root causes of lost deals
- **tone:** practical and analytical

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 84.3s**

### Case 29 — qa-case-029 ✓

**Input:** _engineering manager tool that tracks team health signals — PR review times, standup participation, deploy frequency. not spyware. for EMs who care about team performance_

**Extracted Brain:**
- **icp:** Engineering Manager Leaders
- **problem:** can't measure team performance accurately
- **category:** Team Health Analytics
- **differentiation:** tracks multiple health signals, not just one metric
- **goal:** Optimize Team Velocity
- **tone:** Practical and Data-Driven

**Brain Weaknesses:**
- product: empty

**Suggestions:** 3 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 82.3s**

### Case 30 — qa-case-030 ✓

**Input:** _a tool that watches your runway spreadsheet and tells you when you need to start fundraising based on your current burn, pipeline and hiring plans. for founders who hate finance_

**Extracted Brain:**
- **icp:** venture-backed startup founders
- **problem:** can't accurately forecast runway exhaustion
- **category:** runway forecasting tool
- **differentiation:** uses proprietary financial modeling algorithms
- **goal:** avoid premature fundraising
- **tone:** practical and reassuring

**Brain Weaknesses:**
- product: empty

**Suggestions:** 3 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 84.5s**

### Case 31 — qa-case-031 ✓

**Input:** _launching a SaaS in 3 weeks and have no idea how to write the hero section. the product is an automated invoice chaser for freelancers who hate awkward payment conversations_

**Extracted Brain:**
- **icp:** freelance entrepreneurs
- **problem:** delayed or missed payments due to awkward conversations
- **category:** invoice automation software
- **differentiation:** uses natural language processing for personalized follow-ups
- **goal:** streamline payment processes with minimal effort
- **tone:** practical and relatable

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 82.4s**

### Case 32 — qa-case-032 ✓

**Input:** _need website copy for a new HR analytics tool for mid-size companies. the problem is the VP HR buyers hate the word analytics but they love dashboards and reports_

**Extracted Brain:**
- **icp:** mid-size HR VPs
- **problem:** don't want to wade through complex data sets
- **category:** HR analytics dashboard
- **differentiation:** provides actionable insights without overwhelming data
- **goal:** make informed people decisions
- **tone:** practical and approachable

**Brain Weaknesses:**
- product: empty

**Suggestions:** 2 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 81.8s**

### Case 33 — qa-case-033 ✓

**Input:** _building a landing page for a new product that automates press release distribution but with AI-generated targeting so it only goes to relevant journalists not everyone on a list_

**Extracted Brain:**
- **icp:** PR agency owners
- **problem:** can't guarantee press release visibility for target journalists
- **category:** AI-powered press release distribution
- **differentiation:** uses AI-generated targeting to ensure relevant journalist outreach
- **goal:** generate buzz and drive media coverage
- **tone:** professional and efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing Issues:**
- slot 'what_this_is': empty
- landing text: generic phrases ['ai-powered']

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 80.0s**

### Case 34 — qa-case-034 ✓

**Input:** _trying to write the homepage for my cybersecurity awareness training platform. problem is everyone in this space says the same thing about reducing risk and phishing attacks_

**Extracted Brain:**
- **icp:** cybersecurity training managers
- **problem:** repetitive messages about phishing attacks don't resonate with employees
- **category:** cybersecurity awareness training
- **differentiation:** uses real-world scenarios to educate employees
- **goal:** increase employee engagement in security best practices
- **tone:** practical and informative

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 81.5s**

### Case 35 — qa-case-035 ✓

**Input:** _need to rewrite the positioning for a B2B video testimonial collection tool. we got beta users but they all describe it differently so we dont know what the real value prop is_

**Extracted Brain:**
- **icp:** Marketing VPs at mid-sized B2B companies
- **problem:** can't get authentic customer stories to fuel their marketing campaigns
- **category:** video testimonial collection software
- **differentiation:** uses AI-powered conversation starters, not scripted questions
- **goal:** get a 3x increase in conversion rates from new customer testimonials
- **tone:** practical and encouraging

**Brain Weaknesses:**
- product: empty
- advantage: generic phrases detected (['ai-powered'])

**Landing Issues:**
- slot 'what_this_is': generic phrase detected
- landing text: generic phrases ['ai-powered']

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 90.3s**

### Case 36 — qa-case-036 ✓

**Input:** _our website promises enterprise-grade reliability and security but then when users get inside the app it sounds like a college hackathon project. need help making the product copy match the brand_

**Extracted Brain:**
- **icp:** Enterprise SaaS product managers
- **problem:** confusing app experience undermines brand reputation
- **category:** Enterprise-grade productivity apps
- **differentiation:** transforms raw technical language into clear, concise messaging
- **goal:** establish credibility with potential customers
- **tone:** professional and approachable

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 81.5s**

### Case 37 — qa-case-037 ✓

**Input:** _i write all the in-app copy for our startup and it's always this weird mix of overly formal and weirdly casual. some buttons say 'Submit' and some say 'Let’s go' and it’s embarrassing_

**Extracted Brain:**
- **icp:** founders of early-stage startups
- **problem:** inconsistent tone in app copy makes them look unprofessional
- **category:** in-app copywriting for founders
- **differentiation:** tailors tone to founder's brand voice, not generic templates
- **goal:** create a consistent brand voice that resonates with users
- **tone:** practical and empathetic

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 85.4s**

### Case 38 — qa-case-038 ✓

**Input:** _we rebranded from a dev-first tool to a no-code platform but the product UI still has all the old technical copy everywhere. users keep getting confused by terms meant for developers_

**Extracted Brain:**
- **icp:** founder-CEO of early-stage startups
- **problem:** struggle to articulate their unique value proposition
- **category:** product positioning platform
- **differentiation:** uses proprietary semantic analysis for accurate messaging
- **goal:** secure funding or attract strategic partners
- **tone:** practical and consultative

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 86.2s**

### Case 39 — qa-case-039 ✓

**Input:** _our checkout flow has 12 steps and the copy on each step was written by a different person at a different time. it's a mess and we know it's killing conversion_

**Extracted Brain:**
- **icp:** eCommerce store owners
- **problem:** confusing checkout process with inconsistent messaging
- **category:** checkout flow writer
- **differentiation:** writes step-by-step copy from a unified brand voice
- **goal:** maximize conversion rates through streamlined checkout
- **tone:** practical and concise

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 85.9s**

### Case 40 — qa-case-040 ✓

**Input:** _built by engineers for engineers so all our UX copy is extremely dry and functional. now we're trying to go upmarket to less technical buyers and the copy isnt landing_

**Extracted Brain:**
- **icp:** non-technical startup leaders
- **problem:** struggle to articulate their product's value proposition
- **category:** product positioning services
- **differentiation:** uses data-driven insights to inform messaging
- **goal:** generate interest and drive early traction
- **tone:** practical and consultative

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 82.6s**

### Case 41 — qa-case-041 ✓

**Input:** _i have this idea for a platform where coaches and consultants can create and sell group programs. but there's already kajabi and circle and thinkific so i need to explain why this is different_

**Extracted Brain:**
- **icp:** experienced coaches and consultants
- **problem:** struggle to monetize their expertise in group programs
- **category:** group coaching program marketplace
- **differentiation:** curated, high-quality programs with built-in community features
- **goal:** generate consistent revenue from group programs
- **tone:** encouraging and supportive

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 87.0s**

### Case 42 — qa-case-042 ✓

**Input:** _blockchain-based supply chain visibility tool. before you judge, the use case is actually real — luxury goods brands need to prove provenance and existing tools are expensive legacy systems_

**Extracted Brain:**
- **icp:** luxury goods brand supply chain managers
- **problem:** can't track high-value items through complex global networks
- **category:** supply chain visibility software
- **differentiation:** verifies provenance on blockchain, not just tracking
- **goal:** prove authenticity to customers and regulators
- **tone:** professional and transparent

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX:** No flags

**Score: 10/10 | Alpha-ready: YES | Total time: 82.9s**

### Case 43 — qa-case-043 ✓

**Input:** _i dont know what category i'm in. we do research sprints for startups that need to validate a new market fast. its not consulting its not a survey tool its like a structured 2 week engagement_

**Extracted Brain:**
- **icp:** Startup Founders
- **problem:** Validate market potential in 2 weeks or less
- **category:** Research Sprint Service
- **differentiation:** Structured 2-week engagement, not consulting or survey tools
- **goal:** Gain Market Validation for Funding
- **tone:** Practical and Results-Focused

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 81.5s**

### Case 44 — qa-case-044 ✓

**Input:** _AI writing tool specifically for compliance teams at insurance companies. not chatgpt, not copy.ai — trained on their internal policy language and regulatory requirements_

**Extracted Brain:**
- **icp:** compliance officers at insurance companies
- **problem:** struggle to create accurate policy documents quickly
- **category:** policy writing assistant
- **differentiation:** trained on internal language and regulatory requirements, not general text
- **goal:** produce compliant policy documents efficiently
- **tone:** practical and authoritative

**Brain Weaknesses:**
- product: empty

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 81.8s**

### Case 45 — qa-case-045 ✓

**Input:** _a marketplace for fractional execs — CFOs, CTOs, CMOs. the problem is both sides of the marketplace have to trust each other and that's hard when the engagements are high stakes_

**Extracted Brain:**
- **icp:** ambitious startup CEOs
- **problem:** can't find the right CFO to scale their business
- **category:** fractional executive marketplace
- **differentiation:** vets all executives through rigorous assessments and references
- **goal:** secure a high-caliber CFO for a successful project
- **tone:** practical and professional

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 86.1s**

### Case 46 — qa-case-046 ✓

**Input:** _real estate agents hate writing listing descriptions. i built a thing that takes the MLS fields and generates a really compelling narrative listing copy in seconds. saves like 45 minutes per listing_

**Extracted Brain:**
- **icp:** real estate agents
- **problem:** writing listing descriptions takes too much time
- **category:** listing copy generator
- **differentiation:** generates compelling narratives from MLS fields in seconds
- **goal:** save time and increase listing visibility
- **tone:** practical and efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 77.6s**

### Case 47 — qa-case-047 ✓

**Input:** _podcast production service for B2B companies. we do everything — editing, show notes, chapters, clips for social. the pain point is consistent output without having to manage a VA_

**Extracted Brain:**
- **icp:** B2B marketing managers
- **problem:** struggle to maintain consistent podcast output without overburdening their teams
- **category:** podcast production service for B2B
- **differentiation:** provides turnkey solutions, handling all aspects of podcast creation from editing to show notes and …
- **goal:** deliver a professional-sounding podcast that drives business results
- **tone:** practical and supportive

**Brain Weaknesses:**
- product: empty
- advantage: generic phrases detected ([' solution'])

**Suggestions:** 1 suggestion(s) provided

**Landing Issues:**
- landing text: generic phrases [' solution']

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 87.5s**

### Case 48 — qa-case-048 ✓

**Input:** _a tool for customer success teams to write better QBR decks. they always leave it to the last minute and the decks are always the same template every time. this actually pulls the usage data in_

**Extracted Brain:**
- **icp:** customer success managers
- **problem:** rely on generic templates for quarterly business reviews
- **category:** QBR deck builder
- **differentiation:** pulls usage data to inform insights, not just prompts
- **goal:** deliver a compelling review that drives growth
- **tone:** practical and consultative

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 81.8s**

### Case 49 — qa-case-049 ✓

**Input:** _we help D2C brands figure out their CAC problem. not ads agency, not attribution tool — we do a diagnostic and then build them a 90-day playbook. mostly brands doing $1M-$10M revenue_

**Extracted Brain:**
- **icp:** D2C brand marketers
- **problem:** can't optimize customer acquisition costs effectively
- **category:** customer acquisition strategy
- **differentiation:** provides actionable 90-day playbook, not just diagnostic report
- **goal:** achieve sustainable revenue growth
- **tone:** practical and consultative

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'primary_cta': internal/tooling language detected
- slot 'secondary_cta': internal/tooling language detected

**Score: 8/10 | Alpha-ready: YES | Total time: 84.1s**

### Case 50 — qa-case-050 ✓

**Input:** _SaaS for property managers to handle maintenance request triage. tenants submit via text or app, AI categorizes urgency, assigns to the right vendor, tracks resolution. the current process is a mess_

**Extracted Brain:**
- **icp:** property managers
- **problem:** tenants' maintenance requests are lost in a sea of unorganized emails and phone calls
- **category:** maintenance request management
- **differentiation:** automatically categorizes urgency and assigns tasks to the right vendors
- **goal:** streamline maintenance request resolution process
- **tone:** practical and efficient

**Brain Weaknesses:**
- product: empty

**Suggestions:** 1 suggestion(s) provided

**Landing:** No flags

**UX Issues:**
- slot 'secondary_cta': internal/tooling language detected

**Score: 9/10 | Alpha-ready: YES | Total time: 83.5s**

---

## 3. Pattern Analysis

### Most Frequently Weak Brain Fields

- **product**: 50 cases (100%)
- **advantage**: 4 cases (8%)

### Most Common Missing / Poor Suggestion Types

- No pattern-level suggestion issues detected

### Weakest Landing Page Slots

- **what_this_is**: 5 failures (10%)
- **why_current_options_fail**: 1 failures (2%)

### Weakest UX Slots

- **secondary_cta**: 45 failures (90%)
- **primary_cta**: 24 failures (48%)

### Recurring Generic Phrases

- `ai-powered`: 5 cases (10%)
- ` platform`: 2 cases (4%)
- ` solution`: 1 cases (2%)

### Score Distribution

| Score | Cases |
|---|---|
| 10/10 | 5 |
| 9/10 | 15 |
| 8/10 | 30 |

### Most Common Failure Modes

- No request errors (API layer is reliable)

---

## 4. Priority Fixes

### Must Fix Before Alpha

- **product** (50 cases, 100%)
- **slot 'secondary_cta'** (45 cases, 90%)
- **slot 'primary_cta'** (24 cases, 48%)

### Should Fix Soon

- No high-frequency issues in 15–30% range

### Nice to Have Later

- **slot 'what_this_is'** (5 cases)
- **landing text** (5 cases)
- **advantage** (4 cases)
- **slot 'why_current_options_fail'** (1 cases)

---

## 5. Recommended Next Action

> **Single highest-leverage fix:** Address `product` — this is the most recurring failure pattern and has downstream impact on both landing and UX output quality.

Fix the root cause in `/idea` extraction before improving generation quality — garbage-in garbage-out applies directly here.
