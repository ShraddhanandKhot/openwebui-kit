# OpenWebUI — Customized OpenWebUI with Spryntworks patches, AnyDoc pipeline, and file-generation tools

A customized OpenWebUI delivered by Spryntworks. Includes Custom Theming (CSS), Backend Source Patches, AnyDoc Pipeline, Workspace Tools (8 tools), Workspace Content (Skills + Prompts), Sprynt CLI (one-command client tool).

## Quick start

1. Install [Docker](https://docs.docker.com/get-docker/) (Docker Desktop on Windows/Mac).
2. Open a terminal in this folder.
3. Run:

```bash
./install.sh
```

4. Open http://localhost:8080 and sign up (first account = admin).

## Easier: the sprynt CLI (recommended)

Install the one-word command, then use it for everything:

```bash
sudo bash install-sprynt.sh          # installs the 'sprynt' command
sprynt install                       # install (same as ./install.sh)
sprynt login <admin-api-key>         # save your key once
sprynt list                          # see bundled tools/skills/models
sprynt import                        # import everything
sprynt import tools pdf_generator    # import specific items only
sprynt status                        # is it running? which version?
sprynt update                        # update later
sprynt remove                        # uninstall
```

No scripts, no paths — just short commands.

## Settings

Edit `.env` to change the port or add your API key before installing:

```bash
cp .env.example .env
nano .env
```

## Connect your models

In the browser: **Settings → Model Connections** → paste your
OpenAI / OpenRouter / Ollama key. You choose your models — we never
ship our keys.

## Import your content (Tools / Skills / Prompts)

All-in-one (everything bundled):
```bash
./import-content.sh <your-admin-api-key>
```

Or separately:
```bash
./import-tools.sh    <your-admin-api-key>   # Tools only
./import-skills.sh   <your-admin-api-key>   # Skills only
./import-prompts.sh  <your-admin-api-key>   # Prompts only
./import-models.sh   <your-admin-api-key>   # Models only
```

Key location: Settings → Admin Panel → API Keys → Generate.

## Models

The bundled models are configs/wrappers (name, base model, attached
tools/skills, parameters). Connect YOUR provider first:
**Settings → Model Connections** → paste your OpenAI / OpenRouter /
Ollama key — then import the model configs:

```bash
./import-models.sh <your-admin-api-key>
```

Your API key is never shipped — it stays on your machine.

## Update

```bash
./upgrade.sh
```

Pulls the newest image. Your data in `./data/` is never touched.

## Remove

```bash
./uninstall.sh          # keeps your data
./uninstall.sh --delete-data   # also deletes data
```

## Data

Everything (chats, users, settings, KB) is stored in `./data/`.
It survives every update — never delete it unless you want to start fresh.

## What's included

- Custom Theming (CSS), Backend Source Patches, AnyDoc Pipeline, Workspace Tools (8 tools), Workspace Content (Skills + Prompts), Sprynt CLI (one-command client tool)

## Support

For help, contact Spryntworks.
