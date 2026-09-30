# Cloud Manager — Discord and Flask Server Dashboard

A Python prototype for managing V2Ray server configurations through Discord commands and a Flask dashboard with Discord OAuth login.

**Stack:** Python · discord.py · Flask · Flask-Discord · SQLite · aiohttp

## Project highlights

- Discord commands for server administration and client configuration operations.
- Web dashboard for browsing guilds and their associated servers.
- SQLite persistence for guild, role, server, and client records.
- Shared database and API utilities for the bot and dashboard.

## Architecture

```text
Discord bot / slash commands ─┐
                             ├─ SQLite + API manager → configured servers
Flask dashboard / OAuth ──────┘
```

## Local setup

Use Python 3.10+ and your own Discord application and test infrastructure.

```bash
git clone https://github.com/ChalanaGimhanaX/Cloud-Manager.git
cd Cloud-Manager
python -m venv .venv
```

Activate `.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate` on macOS/Linux, then:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`. Set your own bot token, OAuth client ID and secret, Flask session secret, superadmin IDs, and database path. Use an absolute `DB_PATH` so the bot and dashboard open the same database.

Set `DASHBOARD_URL=http://localhost:5000` and register `http://localhost:5000/callback` as the Discord OAuth redirect. Enable the privileged intents requested by `discord.Intents.all()` in `main.py`.

From the repository root, start the bot:

```bash
python main.py
```

In a second terminal with the same environment activated:

```bash
python run_dashboard.py
```

Open <http://localhost:5000>. The bot initializes a fresh database; bring your own test server configuration.

## Code guide

| Location | Responsibility |
| --- | --- |
| `main.py` | Bot startup, guild setup, command loading |
| `commands/` | Administration and configuration commands |
| `dashboard/app.py` | Flask routes and Discord OAuth |
| `dashboard/templates/` | HTML interface |
| `utils/db.py` | SQLite persistence |
| `utils/api_manager.py` | Server API integration |
| `run_dashboard.py` | Dashboard entry point |

## Development status

This is a prototype, not a production-ready hosting control panel.

- The command loader references `commands.config` and `commands.usage`, but those modules are not included.
- Development entry points enable insecure OAuth transport. Production needs HTTPS and removal of that setting.
- The bot can create administrative roles on joining a guild. Review `setup_default_roles` before inviting it to an existing community.
- Authorization and guild isolation need end-to-end tests before use with customers or real infrastructure.
- Environment files, SQLite databases, logs, and bytecode must remain outside Git.

For manual verification, start in a dedicated test guild, confirm database initialization, sign in through the dashboard, and verify access boundaries for each role. No live infrastructure tests are implied by this documentation.

## Author

[Chalana Gimhana](https://github.com/ChalanaGimhanaX) — Python, APIs, and server automation.
