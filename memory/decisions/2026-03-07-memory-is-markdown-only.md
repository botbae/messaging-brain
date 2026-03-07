# Memory is plain markdown — no vector DB, no embeddings

**Date:** 2026-03-07
**Status:** active

## Decision

All project memory (System Brain and Product Brain) is stored as plain markdown files. No vector database, no embedding model, no retrieval library, no external memory service.

## Why

- The project is stdlib-only. Adding a vector DB or embedding model would introduce external dependencies that conflict with the "no new frameworks" constraint.
- At the current scale (one repo, a handful of clients, a few dozen memory files), semantic search adds no practical value over reading the relevant file directly.
- Plain markdown is readable and editable by humans without tooling. AI tools can read it via normal file access. No index needs to stay in sync.
- Complexity introduced by retrieval infrastructure would outweigh the benefit until the memory corpus is significantly larger.

## Alternatives considered

- **ChromaDB or similar**: rejected — external dependency, requires a running service or embedded binary
- **JSONL with embedding index**: rejected — adds an embedding model dependency and a build step to maintain the index
- **SQLite full-text search**: rejected — adds a query layer for content that is currently simple enough to navigate by folder structure

## When to reconsider

- If the number of clients exceeds ~50 and manually locating a specific memory entry becomes slow
- If a retrieval step is added to the generation pipeline (e.g. "find the most relevant past decisions for this brief")
- If the memory corpus grows to the point where a flat file list is unwieldy
