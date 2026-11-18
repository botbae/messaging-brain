# Messaging Brain API

**Local prototyping only. No auth, no database, no production infra.**

This is a thin FastAPI wrapper over the existing CLI backend. It exposes the same
idea → brain → generate flow over HTTP so a frontend can call it locally.

---

## Entry point

```
src/api/app.py
```

## Start the server

Run from the **repo root** with the venv active:

```bash
PYTHONPATH=src uvicorn src.api.app:app --reload --port 8000
```

Interactive docs available at: `http://localhost:8000/docs`

---

## Endpoints

### POST /idea

Extract ICP, problem, category, and differentiation from a product idea string.
Optionally seeds `clients/<client>/product_profile.json` (the Messaging Brain).

**Request:**
```json
{
  "idea": "An AI tool that writes landing pages for B2B SaaS founders",
  "client": "myproduct"
}
```

**Response:**
```json
{
  "client": "myproduct",
  "idea_extract": {
    "icp": "...",
    "problem": "...",
    "category": "...",
    "differentiation": "..."
  },
  "product_profile_path": "clients/myproduct/product_profile.json"
}
```

---

### POST /brain

Run the full positioning LLM pass from a brief. Saves `clients/<client>/brief.json`
and `clients/<client>/product_profile.json` (the Messaging Brain).

**Request:**
```json
{
  "client": "myproduct",
  "brief": {
    "product": "Acme",
    "audience": "B2B SaaS founders",
    "pain": "Can't explain their product clearly to buyers",
    "offer": "AI-generated landing pages and UX copy",
    "tone": "clear, confident, and human",
    "cta": "Start your free brief",
    "context": "",
    "examples": ""
  }
}
```

**Response:**
```json
{
  "client": "myproduct",
  "product_profile": {
    "product": "...",
    "audience": "...",
    "problem": "...",
    "tone": "...",
    "decisions": { ... }
  }
}
```

---

### POST /brain/save

Persist edited Messaging Brain fields back to `clients/<client>/product_profile.json`.
The profile must already exist (run `POST /brain` first). Only supplied non-empty fields are
overwritten; all other existing data is preserved.

**Field mapping** (`idea_extract` → stored brain):

| Request field     | decisions key        | top-level profile field |
|-------------------|----------------------|-------------------------|
| `icp`             | `icp`                | —                       |
| `problem`         | `primary_problem`    | `problem`               |
| `category`        | `category_frame`     | —                       |
| `differentiation` | `differentiation`    | `advantage`             |

**Request:**
```json
{
  "client": "myproduct",
  "idea_extract": {
    "icp": "B2B SaaS founders",
    "problem": "Can't explain their product clearly to buyers",
    "category": "AI writing tools",
    "differentiation": "The only tool that writes from your positioning, not a blank prompt"
  }
}
```

**Response:**
```json
{
  "client": "myproduct",
  "product_profile": { ... }
}
```

**Errors:**
- `404` — no `product_profile.json` found; run `POST /brain` first.

---

### POST /generate/landing

Generate a landing page using the client's stored brain.
Requires `/brain` to have been run first (brief and product_profile must exist).

**Request:**
```json
{ "client": "myproduct" }
```

**Response:**
```json
{
  "mode": "landing",
  "text": "...",
  "latest_path": "clients/myproduct/outputs/landing_latest.md",
  "versioned_path": "clients/myproduct/outputs/landing_v1.md"
}
```

---

### POST /generate/ux

Generate a UX pack using the client's stored brain.
Requires `/brain` to have been run first.

**Request:**
```json
{ "client": "myproduct" }
```

**Response:**
```json
{
  "mode": "ux",
  "text": "...",
  "latest_path": "clients/myproduct/outputs/ux_latest.md",
  "versioned_path": "clients/myproduct/outputs/ux_v1.md"
}
```

---

## curl examples

```bash
# /idea
curl -X POST http://localhost:8000/idea \
  -H "Content-Type: application/json" \
  -d '{"idea": "An AI tool that writes landing pages for B2B SaaS founders", "client": "myproduct"}'

# /brain
curl -X POST http://localhost:8000/brain \
  -H "Content-Type: application/json" \
  -d '{
    "client": "myproduct",
    "brief": {
      "product": "Acme",
      "audience": "B2B SaaS founders",
      "pain": "Cannot explain their product clearly to buyers",
      "offer": "AI-generated landing pages and UX copy",
      "tone": "clear, confident, and human",
      "cta": "Start your free brief"
    }
  }'

# /brain/save
curl -X POST http://localhost:8000/brain/save \
  -H "Content-Type: application/json" \
  -d '{
    "client": "myproduct",
    "idea_extract": {
      "icp": "B2B SaaS founders",
      "problem": "Cannot explain their product clearly to buyers",
      "category": "AI writing tools",
      "differentiation": "The only tool that writes from your positioning, not a blank prompt"
    }
  }'

# /generate/landing
curl -X POST http://localhost:8000/generate/landing \
  -H "Content-Type: application/json" \
  -d '{"client": "myproduct"}'

# /generate/ux
curl -X POST http://localhost:8000/generate/ux \
  -H "Content-Type: application/json" \
  -d '{"client": "myproduct"}'
```

---

## Notes

- The server must be started from the **repo root** so relative paths (`clients/`, `outputs/`) resolve correctly.
- Ollama must be running at `localhost:11434` before calling any generation endpoint.
- The CLI (`python src/main.py`) continues to work unchanged alongside the API.
- This is not production-hardened: no auth, no rate limiting, no persistent sessions.
- CORS is enabled for `http://localhost:3000` only — for local frontend development with the Next.js dev server.
