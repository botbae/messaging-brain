#!/usr/bin/env python3
"""
QA Sweep — 50-case harness for the Messaging Brain backend API.

Usage:
    python scripts/run_qa_sweep.py [--base-url http://127.0.0.1:8001] [--timeout 180] [--max-cases 50]
                                   [--pause-between-cases 3] [--pause-between-steps 1]

Runs each case through:
    POST /idea → POST /brain/save → POST /generate/landing → POST /generate/ux

Saves per-case JSON to  qa_runs/<timestamp>/cases/<case_id>.json
Writes final report to   qa_runs/<timestamp>/qa_report.md
Writes progress log to   qa_runs/<timestamp>/run.log
"""

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# 50 messy founder ideas
# ---------------------------------------------------------------------------

IDEAS = [
    # --- B2B SaaS founders struggling with positioning ---
    (1,  "ok so basically i built this thing for sales teams where instead of them having to manually update their crm notes after every call it just listens and does it automatically. but idk how to explain what it is on the website without it sounding like every other AI tool"),
    (2,  "we help fintech startups that just raised series A get their compliance docs in order before regulators come knocking. its not legal software exactly its more like a structured process with some AI help"),
    (3,  "i made a slack bot that notices when your team is stuck on a decision for too long and gently nudges them to either decide or escalate. honestly hard to explain without showing it"),
    (4,  "its a tool for dev agencies to track client feedback across slack, email and loom and turn it into actual task tickets. clients hate linear and jira so this keeps them out of it"),
    (5,  "enterprise HR teams spend way too long building onboarding plans for each new hire — we automate that based on their role, team and skills gaps. mainly targeting people ops leads at 200-500 person companies"),
    # --- indie hackers, solo founders ---
    (6,  "i write cold emails for people but AI-assisted. no not another cold email writer, this one actually researches the prospect and writes it like a human who did their homework not a template"),
    (7,  "subscription tracker but for B2B — it reminds your finance person which SaaS tools your team actually uses vs which ones you're just paying for. built it for myself tbh"),
    (8,  "built a thing that turns long meeting recordings into short opinionated summaries. like it doesnt just transcribe — it tells you what decisions were made and who owns what"),
    (9,  "newsletter ghostwriting for founders who have the ideas but cant sit down and write. i use AI but heavily edited. package is 4 posts per month for like $800"),
    (10, "i'm trying to turn my notion consulting practice into a productized service but i dont know how to say what the outcome is on a landing page without it sounding like every other notion consultant"),
    # --- agencies pitching services ---
    (11, "we're a small design studio that specializes in SaaS onboarding flows. we've shipped 30+ products and we know what works but our website looks like a generic design agency"),
    (12, "brand strategy for early stage startups — mostly helping founders who just got funded figure out their positioning before they build their website. 6 week engagement"),
    (13, "fractional CMO for B2B SaaS companies between $1M and $5M ARR. not content marketing, actual strategy — ICP, messaging, channel mix"),
    (14, "we do conversion rate optimization for ecom brands. specifically focused on the checkout and post-purchase experience. most CRO agencies do the landing page we do the bottom of funnel"),
    (15, "technical SEO agency. we go into big legacy sites and fix the crawl architecture, site speed, schema and internal linking. the kind of work that moves the needle for enterprise clients but most SEO agencies cant do"),
    # --- product marketers trying to launch something ---
    (16, "i'm a PMM at a big company building a side product that helps startup founders write their investor update emails faster. i have a template but i want to turn it into a proper product"),
    (17, "competitive battlecards SaaS. sales reps waste time finding and updating battlecards — ours auto-updates from product changelogs, G2 reviews and sales call transcripts"),
    (18, "customer story toolkit — helps PMMs collect, format and publish customer case studies faster. the bottleneck is always chasing the customer for a quote and the approval process"),
    (19, "i built an internal wiki tool specifically for remote customer success teams. not confluence, not notion — designed specifically for the CSM workflow with templates built in"),
    (20, "we make pitch deck teardowns as a service. you send us your deck we come back with a written audit in 48 hours. $299 flat. thinking about how to position this for post-seed founders"),
    # --- consumer-ish / creator tools ---
    (21, "an app for people who want to invest in index funds but are anxious about timing — it helps them stick to a DCA plan by hiding the noise and just showing them what to do next"),
    (22, "fitness app but specifically for people who travel a lot for work and can only work out in hotel rooms or airports. the plans adjust automatically based on what you have available"),
    (23, "a journaling app that actually helps you process anxiety not just dump thoughts. it prompts you based on CBT patterns but doesnt feel clinical or like therapy homework"),
    (24, "recipe app for people who have exactly 20 minutes, whatever is in their fridge, and a toddler underfoot. not another pinterest but actually fast and practical"),
    (25, "subscription box for small batch specialty coffee but the twist is it adapts to your palate over time — you rate each bag and the selections get better. built by a former barista"),
    # --- internal tools pain ---
    (26, "we built an internal tool at our agency for tracking proposal statuses across email, notion and our PM tool. it got out of hand and now we want to sell it to other agencies"),
    (27, "used to manually QA our design handoffs against Figma specs. built an internal script that does it automatically. now we want to productize it for design-dev teams"),
    (28, "a dashboard for founder-led sales — shows you which deals went cold and why, based on email thread analysis. built it because we were losing deals and couldnt figure out the pattern"),
    (29, "engineering manager tool that tracks team health signals — PR review times, standup participation, deploy frequency. not spyware. for EMs who care about team performance"),
    (30, "a tool that watches your runway spreadsheet and tells you when you need to start fundraising based on your current burn, pipeline and hiring plans. for founders who hate finance"),
    # --- launch copy pain specifically ---
    (31, "launching a SaaS in 3 weeks and have no idea how to write the hero section. the product is an automated invoice chaser for freelancers who hate awkward payment conversations"),
    (32, "need website copy for a new HR analytics tool for mid-size companies. the problem is the VP HR buyers hate the word analytics but they love dashboards and reports"),
    (33, "building a landing page for a new product that automates press release distribution but with AI-generated targeting so it only goes to relevant journalists not everyone on a list"),
    (34, "trying to write the homepage for my cybersecurity awareness training platform. problem is everyone in this space says the same thing about reducing risk and phishing attacks"),
    (35, "need to rewrite the positioning for a B2B video testimonial collection tool. we got beta users but they all describe it differently so we dont know what the real value prop is"),
    # --- website vs in-product tone mismatch ---
    (36, "our website promises enterprise-grade reliability and security but then when users get inside the app it sounds like a college hackathon project. need help making the product copy match the brand"),
    (37, "i write all the in-app copy for our startup and it's always this weird mix of overly formal and weirdly casual. some buttons say 'Submit' and some say 'Let\u2019s go' and it\u2019s embarrassing"),
    (38, "we rebranded from a dev-first tool to a no-code platform but the product UI still has all the old technical copy everywhere. users keep getting confused by terms meant for developers"),
    (39, "our checkout flow has 12 steps and the copy on each step was written by a different person at a different time. it's a mess and we know it's killing conversion"),
    (40, "built by engineers for engineers so all our UX copy is extremely dry and functional. now we're trying to go upmarket to less technical buyers and the copy isnt landing"),
    # --- harder edge cases / messy briefs ---
    (41, "i have this idea for a platform where coaches and consultants can create and sell group programs. but there's already kajabi and circle and thinkific so i need to explain why this is different"),
    (42, "blockchain-based supply chain visibility tool. before you judge, the use case is actually real — luxury goods brands need to prove provenance and existing tools are expensive legacy systems"),
    (43, "i dont know what category i'm in. we do research sprints for startups that need to validate a new market fast. its not consulting its not a survey tool its like a structured 2 week engagement"),
    (44, "AI writing tool specifically for compliance teams at insurance companies. not chatgpt, not copy.ai — trained on their internal policy language and regulatory requirements"),
    (45, "a marketplace for fractional execs — CFOs, CTOs, CMOs. the problem is both sides of the marketplace have to trust each other and that's hard when the engagements are high stakes"),
    # --- more realistic messy pitches ---
    (46, "real estate agents hate writing listing descriptions. i built a thing that takes the MLS fields and generates a really compelling narrative listing copy in seconds. saves like 45 minutes per listing"),
    (47, "podcast production service for B2B companies. we do everything — editing, show notes, chapters, clips for social. the pain point is consistent output without having to manage a VA"),
    (48, "a tool for customer success teams to write better QBR decks. they always leave it to the last minute and the decks are always the same template every time. this actually pulls the usage data in"),
    (49, "we help D2C brands figure out their CAC problem. not ads agency, not attribution tool — we do a diagnostic and then build them a 90-day playbook. mostly brands doing $1M-$10M revenue"),
    (50, "SaaS for property managers to handle maintenance request triage. tenants submit via text or app, AI categorizes urgency, assigns to the right vendor, tracks resolution. the current process is a mess"),
]


# ---------------------------------------------------------------------------
# Generic / weak phrase detection
# ---------------------------------------------------------------------------

GENERIC_PHRASES = [
    "ai-powered",
    "innovative platform",
    "unleash the power",
    "cutting-edge",
    " platform",
    " solution",
    "source of truth",
    "structured messaging",
    "reasoning layer",
    "aligned across channels",
    "clear landing page quickly",
    "practical and concise",
    "next-generation",
    "next generation",
    "all-in-one",
    "seamless experience",
    "modern platform",
    "powerful solution",
    "end-to-end",
    "game.changer",
    "game changer",
    "best.in.class",
    "best in class",
    "transformative",
    "disruptive",
    "leverage",
]

UX_INTERNAL_PHRASES = [
    "define icp",
    "review brief",
    "profile generation failed",
    "brief intake",
    "decision review",
    "generation review",
    "update messaging brain",
    "run positioning",
    "check brain",
]

LANDING_REQUIRED_SLOTS = [
    "headline",
    "subhead",
    "problem",
    "why_current_options_fail",
    "what_this_is",
    "primary_cta",
]

UX_REQUIRED_SLOTS = [
    "primary_cta",
    "secondary_cta",
    "empty_state",
    "helper_text",
    "error_message",
]

BRAIN_FIELDS = ["product", "audience", "problem", "alternatives", "advantage", "goal", "tone"]

# Retry settings for generation endpoints
_RETRY_ENDPOINTS = {"/generate/landing", "/generate/ux"}
_RETRY_PAUSE = 5  # seconds to wait before retrying a failed generation call


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _post(base_url: str, path: str, body: dict, timeout: int) -> tuple[dict | None, float, str | None]:
    """POST JSON, return (parsed_json, elapsed_seconds, error_string)."""
    url = f"{base_url}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.monotonic() - t0
            raw = resp.read().decode()
            return json.loads(raw), elapsed, None
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - t0
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = str(e)
        return None, elapsed, f"HTTP {e.code}: {detail}"
    except Exception as e:
        elapsed = time.monotonic() - t0
        return None, elapsed, str(e)


def _post_with_retry(
    base_url: str,
    path: str,
    body: dict,
    timeout: int,
    pause_between_steps: float,
) -> tuple[dict | None, float, str | None]:
    """POST with one retry for generation endpoints. Non-generation paths are not retried."""
    result, elapsed, err = _post(base_url, path, body, timeout)
    if err is not None and path in _RETRY_ENDPOINTS:
        time.sleep(_RETRY_PAUSE)
        result2, elapsed2, err2 = _post(base_url, path, body, timeout)
        if err2 is None:
            return result2, elapsed + elapsed2, None
        # Both attempts failed — return the second error (more recent)
        return None, elapsed + elapsed2, f"{err2} (retry also failed: was '{err}')"
    return result, elapsed, err


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def _has_generic(text: str, phrases: list[str]) -> list[str]:
    t = text.lower()
    return [p for p in phrases if p in t]


def _slug(case_id: int) -> str:
    return f"qa-case-{case_id:03d}"


def _extract_brain_summary(idea_resp: dict | None) -> dict:
    if not idea_resp:
        return {}
    ie = idea_resp.get("idea_extract", {}) or {}
    # idea_extract may be nested or flat
    if isinstance(ie, dict):
        return {
            "product": ie.get("product", ""),
            "icp": ie.get("icp", ""),
            "problem": ie.get("problem", ""),
            "category": ie.get("category", ""),
            "differentiation": ie.get("differentiation", ""),
            "alternatives": ie.get("alternatives", ""),
            "advantage": ie.get("advantage", ""),
            "goal": ie.get("goal", ""),
            "tone": ie.get("tone", ""),
        }
    return {}


def _flag_brain_weaknesses(brain: dict) -> list[str]:
    flags = []

    product = brain.get("product", "")
    if len(product.split()) > 15:
        flags.append("product: looks like a full pitch sentence rather than product/category name")
    elif not product:
        flags.append("product: empty")

    audience = brain.get("icp", "") or brain.get("audience", "")
    if not audience:
        flags.append("audience/icp: empty")
    elif any(w in audience.lower() for w in ["everyone", "anyone", "all businesses", "any company"]):
        flags.append("audience/icp: too broad")

    problem = brain.get("problem", "")
    if not problem:
        flags.append("problem: empty")
    elif len(problem.split()) < 5:
        flags.append("problem: suspiciously short / generic")

    alternatives = brain.get("alternatives", "") or brain.get("differentiation", "")
    if not alternatives or len(str(alternatives).strip()) < 10:
        flags.append("alternatives: empty or near-empty despite idea mentioning competitors")

    advantage = brain.get("advantage", "") or brain.get("differentiation", "")
    if not advantage:
        flags.append("advantage/differentiation: empty")
    elif _has_generic(str(advantage), GENERIC_PHRASES):
        flags.append(f"advantage: generic phrases detected ({_has_generic(str(advantage), GENERIC_PHRASES)})")

    goal = brain.get("goal", "")
    if not goal:
        flags.append("goal: empty")
    elif _has_generic(str(goal), ["clear messaging", "structured", "better copy", "launch faster"]):
        flags.append("goal: boilerplate-sounding")

    tone = brain.get("tone", "")
    if not tone:
        flags.append("tone: empty")
    elif tone.lower().strip() in ["professional", "clear", "concise", "friendly", "professional and clear"]:
        flags.append(f"tone: generic / boilerplate ('{tone}')")

    return flags


def _flag_landing(slots: dict | None, text: str) -> list[str]:
    flags = []
    if not slots:
        flags.append("slots: missing entirely")
        return flags
    for slot in LANDING_REQUIRED_SLOTS:
        val = slots.get(slot, "")
        if not val or str(val).strip() in ("", "—", "N/A", "None"):
            flags.append(f"slot '{slot}': empty")
        elif _has_generic(str(val), GENERIC_PHRASES):
            flags.append(f"slot '{slot}': generic phrase detected")

    full = text or ""
    generic_hits = _has_generic(full, GENERIC_PHRASES)
    if generic_hits:
        flags.append(f"landing text: generic phrases {generic_hits[:5]}")
    return flags


def _flag_ux(slots: dict | None, text: str) -> list[str]:
    flags = []
    if not slots:
        flags.append("slots: missing entirely")
        return flags
    for slot in UX_REQUIRED_SLOTS:
        val = slots.get(slot, "")
        if not val or str(val).strip() in ("", "—", "N/A", "None"):
            flags.append(f"slot '{slot}': empty")
        elif _has_generic(str(val), GENERIC_PHRASES):
            flags.append(f"slot '{slot}': generic phrase")
        elif _has_generic(str(val).lower(), UX_INTERNAL_PHRASES):
            flags.append(f"slot '{slot}': internal/tooling language detected")
    full = text or ""
    internal_hits = _has_generic(full.lower(), UX_INTERNAL_PHRASES)
    if internal_hits:
        flags.append(f"ux text: internal/process language {internal_hits[:3]}")
    return flags


def _score(
    brain_flags: list[str],
    suggestions_flags: list[str],
    landing_flags: list[str],
    ux_flags: list[str],
    errors: list[str],
) -> int:
    """Score 0-10. Start at 10, deduct for each issue."""
    score = 10

    # Hard errors / request failures
    score -= len([e for e in errors if e]) * 3

    # Brain quality (-0.5 per flag, max -3)
    brain_deduct = min(3, len(brain_flags) * 0.5)
    score -= brain_deduct

    # Landing quality (-0.5 per flag, max -3)
    landing_deduct = min(3, len(landing_flags) * 0.5)
    score -= landing_deduct

    # UX quality (-0.5 per flag, max -2)
    ux_deduct = min(2, len(ux_flags) * 0.5)
    score -= ux_deduct

    # Missing suggestions when brain is weak
    if len(brain_flags) >= 3 and not suggestions_flags:
        score -= 0.5

    return max(0, round(score))


def _alpha_ready(score: int, errors: list[str]) -> bool:
    has_error = any(e for e in errors if e)
    return score >= 7 and not has_error


# ---------------------------------------------------------------------------
# Log helpers
# ---------------------------------------------------------------------------

def _log(log_path: Path, message: str) -> None:
    """Append a timestamped line to the run log."""
    ts = datetime.now().strftime("%H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"[{ts}] {message}\n")


# ---------------------------------------------------------------------------
# Main sweep runner
# ---------------------------------------------------------------------------

def run_sweep(
    base_url: str,
    timeout: int,
    max_cases: int,
    out_dir: Path,
    pause_between_cases: float,
    pause_between_steps: float,
) -> list[dict]:
    cases_dir = out_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "run.log"

    results = []
    ideas_to_run = IDEAS[:max_cases]
    total = len(ideas_to_run)

    header = (
        f"\n{'='*60}\n"
        f"  Messaging Brain QA Sweep — {total} cases\n"
        f"  Backend: {base_url}\n"
        f"  Output:  {out_dir}\n"
        f"  Timeout: {timeout}s | Pause/case: {pause_between_cases}s | Pause/step: {pause_between_steps}s\n"
        f"{'='*60}\n"
    )
    print(header)
    _log(log_path, f"Sweep started — {total} cases, backend={base_url}, timeout={timeout}s")

    sweep_start = time.monotonic()

    for idx, (case_id, idea_text) in enumerate(ideas_to_run, start=1):
        slug = _slug(case_id)
        case_start = time.monotonic()
        print(f"[{idx:02d}/{total:02d}] {slug} ...", end=" ", flush=True)
        _log(log_path, f"START case {idx:02d}/{total:02d}  {slug}")

        result = {
            "case_id": case_id,
            "slug": slug,
            "input_idea": idea_text,
            "timings": {},
            "errors": [],
            "responses": {},
            "brain_summary": {},
            "brain_flags": [],
            "suggestions_flags": [],
            "landing_flags": [],
            "ux_flags": [],
            "score": 0,
            "alpha_ready": False,
        }

        # --- Step 1: POST /idea ---
        idea_body = {"idea": idea_text, "client": slug}
        idea_resp, t, err = _post(base_url, "/idea", idea_body, timeout)
        result["timings"]["idea"] = round(t, 2)
        if err:
            result["errors"].append(f"/idea: {err}")
            _log(log_path, f"  /idea ERROR: {err[:120]}")
            print(f"ERROR /idea → {err[:80]}")
        else:
            _log(log_path, f"  /idea OK  t={t:.1f}s")

        # Extract brain + metadata
        brain_summary = _extract_brain_summary(idea_resp)
        result["brain_summary"] = brain_summary
        idea_metadata = idea_resp.get("idea_metadata") if idea_resp else None
        brain_suggestions = idea_resp.get("brain_suggestions") if idea_resp else None
        result["responses"]["idea"] = idea_resp
        result["responses"]["idea_metadata"] = idea_metadata
        result["responses"]["brain_suggestions"] = brain_suggestions

        brain_flags = _flag_brain_weaknesses(brain_summary)
        result["brain_flags"] = brain_flags

        # Suggestions quality check
        suggestions_flags = []
        if not brain_suggestions and len(brain_flags) >= 3:
            suggestions_flags.append("no suggestions despite multiple weak brain fields")
        if brain_suggestions and isinstance(brain_suggestions, list):
            for s in brain_suggestions:
                if _has_generic(str(s), GENERIC_PHRASES):
                    suggestions_flags.append(f"generic suggestion: '{str(s)[:80]}'")
        if idea_metadata:
            low_conf = [k for k, v in idea_metadata.items() if isinstance(v, dict) and v.get("confidence", 1.0) < 0.7]
            if low_conf:
                unaddressed = [k for k in low_conf if not brain_suggestions or not any(k in str(s) for s in (brain_suggestions or []))]
                if unaddressed:
                    suggestions_flags.append(f"low-confidence fields not flagged in suggestions: {unaddressed}")
        result["suggestions_flags"] = suggestions_flags

        if pause_between_steps > 0:
            time.sleep(pause_between_steps)

        # --- Step 2: POST /brain/save ---
        if idea_resp and not err:
            ie = idea_resp.get("idea_extract", {}) or {}
            save_body = {
                "client": slug,
                "idea_extract": {
                    "product": ie.get("product", ""),
                    "icp": ie.get("icp", ""),
                    "problem": ie.get("problem", ""),
                    "category": ie.get("category", ""),
                    "differentiation": ie.get("differentiation", ""),
                },
            }
            save_resp, t, err2 = _post(base_url, "/brain/save", save_body, timeout)
            result["timings"]["brain_save"] = round(t, 2)
            if err2:
                result["errors"].append(f"/brain/save: {err2}")
                _log(log_path, f"  /brain/save ERROR: {err2[:120]}")
            else:
                result["responses"]["brain_save"] = save_resp
                _log(log_path, f"  /brain/save OK  t={t:.1f}s")
        else:
            result["errors"].append("/brain/save: skipped (no idea response)")
            _log(log_path, "  /brain/save SKIPPED")

        if pause_between_steps > 0:
            time.sleep(pause_between_steps)

        # --- Step 3: POST /generate/landing (with retry) ---
        gen_body = {"client": slug}
        land_resp, t, err3 = _post_with_retry(base_url, "/generate/landing", gen_body, timeout, pause_between_steps)
        result["timings"]["landing"] = round(t, 2)
        if err3:
            result["errors"].append(f"/generate/landing: {err3}")
            _log(log_path, f"  /generate/landing ERROR: {err3[:120]}")
        else:
            result["responses"]["landing"] = {
                "text": land_resp.get("text", ""),
                "slots": land_resp.get("slots"),
            }
            _log(log_path, f"  /generate/landing OK  t={t:.1f}s")

        land_slots = land_resp.get("slots") if land_resp else None
        land_text = land_resp.get("text", "") if land_resp else ""
        landing_flags = _flag_landing(land_slots, land_text)
        result["landing_flags"] = landing_flags

        if pause_between_steps > 0:
            time.sleep(pause_between_steps)

        # --- Step 4: POST /generate/ux (with retry) ---
        ux_resp, t, err4 = _post_with_retry(base_url, "/generate/ux", gen_body, timeout, pause_between_steps)
        result["timings"]["ux"] = round(t, 2)
        if err4:
            result["errors"].append(f"/generate/ux: {err4}")
            _log(log_path, f"  /generate/ux ERROR: {err4[:120]}")
        else:
            result["responses"]["ux"] = {
                "text": ux_resp.get("text", ""),
                "slots": ux_resp.get("slots"),
            }
            _log(log_path, f"  /generate/ux OK  t={t:.1f}s")

        ux_slots = ux_resp.get("slots") if ux_resp else None
        ux_text = ux_resp.get("text", "") if ux_resp else ""
        ux_flags = _flag_ux(ux_slots, ux_text)
        result["ux_flags"] = ux_flags

        # --- Score ---
        score = _score(brain_flags, suggestions_flags, landing_flags, ux_flags, result["errors"])
        result["score"] = score
        result["alpha_ready"] = _alpha_ready(score, result["errors"])

        case_elapsed = time.monotonic() - case_start
        result["timings"]["total"] = round(case_elapsed, 2)
        status = "PASS" if result["alpha_ready"] else "FAIL"
        summary_line = (
            f"{status} score={score}/10  t={case_elapsed:.1f}s  "
            f"brain_flags={len(brain_flags)}  landing_flags={len(landing_flags)}  ux_flags={len(ux_flags)}"
        )
        print(summary_line)
        _log(log_path, f"  {summary_line}")

        # Save per-case JSON
        case_path = cases_dir / f"{slug}.json"
        with open(case_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        results.append(result)

        # Pace between cases (skip after last case)
        if pause_between_cases > 0 and idx < total:
            time.sleep(pause_between_cases)

    sweep_elapsed = time.monotonic() - sweep_start
    _log(log_path, f"Sweep finished — elapsed={sweep_elapsed:.1f}s")
    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _md_escape(s: str) -> str:
    return str(s).replace("|", "\\|")


def _truncate(s: str, n: int = 120) -> str:
    s = str(s).strip()
    return s[:n] + "…" if len(s) > n else s


def generate_report(results: list[dict], out_dir: Path) -> Path:
    passes = [r for r in results if r["alpha_ready"]]
    fails = [r for r in results if not r["alpha_ready"]]
    avg_score = sum(r["score"] for r in results) / len(results) if results else 0

    # Aggregate pattern analysis
    all_brain_flags = [f for r in results for f in r["brain_flags"]]
    all_suggestion_flags = [f for r in results for f in r["suggestions_flags"]]
    all_landing_flags = [f for r in results for f in r["landing_flags"]]
    all_ux_flags = [f for r in results for f in r["ux_flags"]]
    all_errors = [e for r in results for e in r["errors"] if e]

    def top_n(items: list[str], n: int = 10) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for item in items:
            # normalize: strip prefix up to first colon for grouping
            key = item.split(":")[0].strip() if ":" in item else item
            counts[key] = counts.get(key, 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])[:n]

    # Top recurring issues
    all_issues = all_brain_flags + all_landing_flags + all_ux_flags + all_errors
    top_issues = top_n(all_issues, 10)

    # Atlas hypothesis comparison
    atlas_comparison = [
        ("Generation reliability / hanging states",
         "MIXED" if any("/idea" in e or "/generate" in e for e in all_errors) else "NOT CONFIRMED — all cases completed",
         f"{len(all_errors)} total request errors across {len(results)} cases"),
        ("Weak product field extraction",
         "CONFIRMED" if sum(1 for f in all_brain_flags if "product:" in f) > 5 else "PARTIAL",
         f"{sum(1 for f in all_brain_flags if 'product:' in f)} cases with product field flags"),
        ("Alternatives often missing",
         "CONFIRMED" if sum(1 for f in all_brain_flags if "alternatives:" in f) > 10 else "MIXED",
         f"{sum(1 for f in all_brain_flags if 'alternatives:' in f)} cases with missing/weak alternatives"),
        ("Generic goal/tone",
         "CONFIRMED" if sum(1 for f in all_brain_flags if "goal:" in f or "tone:" in f) > 10 else "MIXED",
         f"{sum(1 for f in all_brain_flags if 'goal:' in f or 'tone:' in f)} cases with generic goal/tone"),
        ("Internal-sounding UX copy",
         "CONFIRMED" if sum(1 for f in all_ux_flags if "internal" in f.lower()) > 3 else "MIXED",
         f"{sum(1 for f in all_ux_flags if 'internal' in f.lower())} cases with internal-language UX flags"),
    ]

    # Slot-level failure frequency
    landing_slot_fails = {}
    for r in results:
        for f in r["landing_flags"]:
            m = re.match(r"slot '([^']+)':", f)
            if m:
                slot = m.group(1)
                landing_slot_fails[slot] = landing_slot_fails.get(slot, 0) + 1

    ux_slot_fails = {}
    for r in results:
        for f in r["ux_flags"]:
            m = re.match(r"slot '([^']+)':", f)
            if m:
                slot = m.group(1)
                ux_slot_fails[slot] = ux_slot_fails.get(slot, 0) + 1

    # Scores distribution
    score_dist = {}
    for r in results:
        s = r["score"]
        score_dist[s] = score_dist.get(s, 0) + 1

    # Priority fix categorization
    # Must-fix: issues appearing in > 30% of cases
    must_fix = [(issue, count) for issue, count in top_n(all_issues, 20) if count >= len(results) * 0.3]
    should_fix = [(issue, count) for issue, count in top_n(all_issues, 20) if len(results) * 0.15 <= count < len(results) * 0.3]
    nice_to_have = [(issue, count) for issue, count in top_n(all_issues, 20) if count < len(results) * 0.15]

    report_lines = [
        "# Messaging Brain QA Sweep Report",
        f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        f"_Cases run: {len(results)} | Alpha-ready: {len(passes)} | Failed: {len(fails)} | Avg score: {avg_score:.1f}/10_",
        "\n---\n",

        # ----------------------------------------------------------------
        "## 1. Executive Summary",
        "",
        f"**Alpha readiness verdict:** {'NOT READY' if len(passes) / len(results) < 0.6 else 'BORDERLINE' if len(passes) / len(results) < 0.8 else 'APPROACHING ALPHA'}",
        f"- {len(passes)}/{len(results)} cases passed ({100*len(passes)/len(results):.0f}%)",
        f"- Average score: {avg_score:.1f}/10",
        f"- Total request errors: {len(all_errors)}",
        "",
        "### Top 5 Recurring Issues",
        "",
    ]

    for i, (issue, count) in enumerate(top_issues[:5], 1):
        pct = 100 * count / len(results)
        report_lines.append(f"{i}. **{issue}** — {count} cases ({pct:.0f}%)")

    report_lines += [
        "",
        "### What Is Working Well",
        "",
    ]
    working = []
    if sum(1 for r in results if not r["errors"]) > len(results) * 0.8:
        working.append(f"- API reliability: {sum(1 for r in results if not r['errors'])}/{len(results)} cases completed without request errors")
    if avg_score >= 5:
        working.append(f"- Baseline generation: most cases produce structural output (avg {avg_score:.1f}/10)")
    landing_complete = sum(1 for r in results if len(r["landing_flags"]) == 0)
    if landing_complete > len(results) * 0.3:
        working.append(f"- Landing slot completeness: {landing_complete} cases had no landing flags")
    if not working:
        working.append("- API layer handles diverse input without crashing")
    report_lines += working

    report_lines += [
        "",
        "### Atlas Hypothesis Comparison",
        "",
        "| Hypothesis | Verdict | Evidence |",
        "|---|---|---|",
    ]
    for hyp, verdict, evidence in atlas_comparison:
        report_lines.append(f"| {_md_escape(hyp)} | **{verdict}** | {_md_escape(evidence)} |")

    report_lines += [
        "",
        "---\n",
        "## 2. Test-by-Test Audit",
        "",
    ]

    for r in results:
        status_icon = "✓" if r["alpha_ready"] else "✗"
        report_lines += [
            f"### Case {r['case_id']:02d} — {r['slug']} {status_icon}",
            "",
            f"**Input:** _{_truncate(r['input_idea'], 200)}_",
            "",
            "**Extracted Brain:**",
        ]
        bs = r["brain_summary"]
        if bs:
            for k, v in bs.items():
                if v:
                    report_lines.append(f"- **{k}:** {_truncate(str(v), 100)}")
        else:
            report_lines.append("- _(extraction failed)_")

        if r["brain_flags"]:
            report_lines.append("\n**Brain Weaknesses:**")
            for f in r["brain_flags"]:
                report_lines.append(f"- {f}")

        if r["suggestions_flags"]:
            report_lines.append("\n**Suggestions Quality Issues:**")
            for f in r["suggestions_flags"]:
                report_lines.append(f"- {f}")
        else:
            sug = r["responses"].get("brain_suggestions")
            if sug:
                report_lines.append(f"\n**Suggestions:** {len(sug)} suggestion(s) provided")

        if r["landing_flags"]:
            report_lines.append("\n**Landing Issues:**")
            for f in r["landing_flags"]:
                report_lines.append(f"- {f}")
        else:
            report_lines.append("\n**Landing:** No flags")

        if r["ux_flags"]:
            report_lines.append("\n**UX Issues:**")
            for f in r["ux_flags"]:
                report_lines.append(f"- {f}")
        else:
            report_lines.append("\n**UX:** No flags")

        if r["errors"]:
            report_lines.append("\n**Request Errors:**")
            for e in r["errors"]:
                report_lines.append(f"- `{e}`")

        timings = r["timings"]
        total_t = timings.get("total", sum(v for k, v in timings.items() if k != "total"))
        report_lines.append(f"\n**Score: {r['score']}/10 | Alpha-ready: {'YES' if r['alpha_ready'] else 'NO'} | Total time: {total_t:.1f}s**")
        report_lines.append("")

    report_lines += [
        "---\n",
        "## 3. Pattern Analysis",
        "",
        "### Most Frequently Weak Brain Fields",
        "",
    ]
    for issue, count in top_n(all_brain_flags):
        report_lines.append(f"- **{issue}**: {count} cases ({100*count/len(results):.0f}%)")

    report_lines += [
        "",
        "### Most Common Missing / Poor Suggestion Types",
        "",
    ]
    if all_suggestion_flags:
        for issue, count in top_n(all_suggestion_flags):
            report_lines.append(f"- **{issue}**: {count} cases")
    else:
        report_lines.append("- No pattern-level suggestion issues detected")

    report_lines += [
        "",
        "### Weakest Landing Page Slots",
        "",
    ]
    if landing_slot_fails:
        for slot, count in sorted(landing_slot_fails.items(), key=lambda x: -x[1]):
            report_lines.append(f"- **{slot}**: {count} failures ({100*count/len(results):.0f}%)")
    else:
        report_lines.append("- No slot-level failures detected")

    report_lines += [
        "",
        "### Weakest UX Slots",
        "",
    ]
    if ux_slot_fails:
        for slot, count in sorted(ux_slot_fails.items(), key=lambda x: -x[1]):
            report_lines.append(f"- **{slot}**: {count} failures ({100*count/len(results):.0f}%)")
    else:
        report_lines.append("- No slot-level UX failures detected")

    report_lines += [
        "",
        "### Recurring Generic Phrases",
        "",
    ]
    phrase_counts: dict[str, int] = {}
    for r in results:
        all_text = (
            json.dumps(r["responses"].get("landing", {})) + " " +
            json.dumps(r["responses"].get("ux", {}))
        ).lower()
        for p in GENERIC_PHRASES:
            if p in all_text:
                phrase_counts[p] = phrase_counts.get(p, 0) + 1
    if phrase_counts:
        for phrase, count in sorted(phrase_counts.items(), key=lambda x: -x[1])[:10]:
            report_lines.append(f"- `{phrase}`: {count} cases ({100*count/len(results):.0f}%)")
    else:
        report_lines.append("- No widespread generic phrases detected")

    report_lines += [
        "",
        "### Score Distribution",
        "",
        "| Score | Cases |",
        "|---|---|",
    ]
    for s in sorted(score_dist.keys(), reverse=True):
        report_lines.append(f"| {s}/10 | {score_dist[s]} |")

    report_lines += [
        "",
        "### Most Common Failure Modes",
        "",
    ]
    if all_errors:
        error_types: dict[str, int] = {}
        for e in all_errors:
            key = e.split(":")[0].strip() if ":" in e else e[:50]
            error_types[key] = error_types.get(key, 0) + 1
        for etype, count in sorted(error_types.items(), key=lambda x: -x[1]):
            report_lines.append(f"- **{etype}**: {count} occurrences")
    else:
        report_lines.append("- No request errors (API layer is reliable)")

    report_lines += [
        "",
        "---\n",
        "## 4. Priority Fixes",
        "",
        "### Must Fix Before Alpha",
        "",
    ]
    if must_fix:
        for issue, count in must_fix:
            report_lines.append(f"- **{issue}** ({count} cases, {100*count/len(results):.0f}%)")
    else:
        report_lines.append("- No critical issues found in > 30% of cases (review individual failures)")

    report_lines += [
        "",
        "### Should Fix Soon",
        "",
    ]
    if should_fix:
        for issue, count in should_fix:
            report_lines.append(f"- **{issue}** ({count} cases, {100*count/len(results):.0f}%)")
    else:
        report_lines.append("- No high-frequency issues in 15–30% range")

    report_lines += [
        "",
        "### Nice to Have Later",
        "",
    ]
    if nice_to_have:
        for issue, count in nice_to_have[:8]:
            report_lines.append(f"- **{issue}** ({count} cases)")
    else:
        report_lines.append("- N/A")

    # Highest leverage recommendation
    top_issue = top_issues[0][0] if top_issues else "brain extraction quality"
    report_lines += [
        "",
        "---\n",
        "## 5. Recommended Next Action",
        "",
        f"> **Single highest-leverage fix:** Address `{top_issue}` — this is the most recurring failure pattern and has downstream impact on both landing and UX output quality.",
        "",
        "Fix the root cause in `/idea` extraction before improving generation quality — garbage-in garbage-out applies directly here.",
        "",
    ]

    report_path = out_dir / "qa_report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))

    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Messaging Brain QA Sweep")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Backend base URL")
    parser.add_argument("--timeout", type=int, default=180, help="Per-request timeout in seconds (default: 180)")
    parser.add_argument("--max-cases", type=int, default=50, help="Number of cases to run (max 50)")
    parser.add_argument("--pause-between-cases", type=float, default=3.0,
                        help="Seconds to pause between cases (default: 3)")
    parser.add_argument("--pause-between-steps", type=float, default=1.0,
                        help="Seconds to pause between API steps within a case (default: 1)")
    args = parser.parse_args()

    max_cases = min(args.max_cases, len(IDEAS))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("qa_runs") / timestamp

    results = run_sweep(
        base_url=args.base_url,
        timeout=args.timeout,
        max_cases=max_cases,
        out_dir=out_dir,
        pause_between_cases=args.pause_between_cases,
        pause_between_steps=args.pause_between_steps,
    )
    report_path = generate_report(results, out_dir)

    passes = [r for r in results if r["alpha_ready"]]
    fails = [r for r in results if not r["alpha_ready"]]
    avg_score = sum(r["score"] for r in results) / len(results) if results else 0
    case_times = [r["timings"].get("total", sum(v for k, v in r["timings"].items() if k != "total")) for r in results]
    avg_case_time = sum(case_times) / len(case_times) if case_times else 0

    # Aggregate top 5 issues for terminal summary
    all_flags = (
        [f for r in results for f in r["brain_flags"]] +
        [f for r in results for f in r["landing_flags"]] +
        [f for r in results for f in r["ux_flags"]] +
        [e for r in results for e in r["errors"] if e]
    )
    counts: dict[str, int] = {}
    for f in all_flags:
        key = f.split(":")[0].strip()
        counts[key] = counts.get(key, 0) + 1
    top5 = sorted(counts.items(), key=lambda x: -x[1])[:5]

    print(f"\n{'='*60}")
    print(f"  QA Sweep Complete")
    print(f"{'='*60}")
    print(f"  Report:        {report_path}")
    print(f"  Log:           {out_dir / 'run.log'}")
    print(f"  Total cases:   {len(results)}")
    print(f"  Passes:        {len(passes)} ({100*len(passes)/len(results):.0f}%)")
    print(f"  Fails:         {len(fails)} ({100*len(fails)/len(results):.0f}%)")
    print(f"  Avg score:     {avg_score:.1f}/10")
    print(f"  Avg case time: {avg_case_time:.1f}s")
    print(f"\n  Top 5 Issues:")
    for i, (issue, count) in enumerate(top5, 1):
        print(f"  {i}. {issue} ({count} cases)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
