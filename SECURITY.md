# Security Policy

## Reporting a problem

Please **don't open a public issue** for security problems.

Report it privately instead: go to the [Security tab](https://github.com/botbae/messaging-brain/security) and click **Report a vulnerability**. Include what you found, how to reproduce it, and what impact you think it has. You should hear back within a week.

## What's in scope

- The CLI (`src/main.py`) and the API server (`src/api/app.py`)
- How client names and files under `clients/` and `outputs/` are handled
- How API keys are loaded from `.env` or environment variables

## Things to know before you report

- **The API has no login and no rate limiting by design.** It's a local prototyping server. Run it on your own machine (the default `127.0.0.1`), not on the open internet. "Anyone who can reach the server can use it" is expected, not a bug.
- **Never commit your `.env` file.** It's in `.gitignore`. Secret scanning with push protection is turned on for this repo.
- Only the latest code on `main` is supported.
