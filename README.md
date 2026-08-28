# OpenWebUI — Customized OpenWebUI with Spryntworks patches, AnyDoc pipeline, and file-generation tools

A customized OpenWebUI delivered by Spryntworks. Includes Custom Theming (CSS), Backend Source Patches, AnyDoc Pipeline, Workspace Tools (8 tools).

## Quick start

1. Install [Docker](https://docs.docker.com/get-docker/) (Docker Desktop on Windows/Mac).
2. Open a terminal in this folder.
3. Run:

```bash
./install.sh
```

4. Open http://localhost:8080 and sign up (first account = admin).

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

## Include the Workspace Tools (optional)

```bash
./import-tools.sh <your-admin-api-key>
```

Key location: Settings → Admin Panel → API Keys → Generate.

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

- Custom Theming (CSS), Backend Source Patches, AnyDoc Pipeline, Workspace Tools (8 tools)

## Support

For help, contact Spryntworks.
