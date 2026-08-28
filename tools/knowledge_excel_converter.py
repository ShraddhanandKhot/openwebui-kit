"""
title: Knowledge Excel Converter (Multi-Collection, Async)
author: you
description: Async version — lists Knowledge collections, finds Excel files inside a chosen collection, converts them to RAG-friendly .md, indexes the converted version back into that collection, and optionally removes the raw xlsx. Async HTTP avoids the self-request timeout when the tool calls its own Open WebUI instance.
required_open_webui_version: 0.4.0
requirements: pandas, openpyxl, httpx
version: 4.0
"""

import io
import json
import re
import asyncio
from pathlib import Path

import httpx
import pandas as pd
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        openwebui_url: str = Field(
            default="http://localhost:8080",
            description="Base URL of this Open WebUI instance as reachable from the server itself",
        )
        api_key: str = Field(
            default="",
            description="Open WebUI API key (Settings -> Account -> API Keys)",
        )
        default_collection: str = Field(
            default="",
            description="Optional: default collection name or ID used when the user doesn't specify one",
        )
        remove_original_xlsx: bool = Field(
            default=True,
            description="After converting, remove the raw .xlsx from the collection so RAG only retrieves the clean converted version",
        )
        state_dir: str = Field(
            default="/app/backend/data/excel_converter",
            description="Folder to remember which converted file replaced which Excel",
        )
        max_preview_lines: int = Field(
            default=12,
            description="How many converted lines to preview in chat",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ----------------------------- helpers ------------------------------

    def _headers(self):
        return {"Authorization": f"Bearer {self.valves.api_key}"}

    def _base(self):
        return self.valves.openwebui_url.rstrip("/")

    def _check_config(self):
        if not self.valves.api_key:
            raise RuntimeError(
                "api_key valve is not set. Open the tool's Valves settings and fill it in."
            )

    async def _get_collections(self, client: httpx.AsyncClient) -> list:
        r = await client.get(f"{self._base()}/api/v1/knowledge/", headers=self._headers())
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            data = data.get("items") or data.get("data") or []
        return data

    async def _resolve_collection(self, client: httpx.AsyncClient, collection: str) -> dict:
        target = (collection or self.valves.default_collection or "").strip()
        if not target:
            raise RuntimeError(
                "No collection specified. Ask the user which collection to use, "
                "or call list_collections to show the options."
            )
        cols = await self._get_collections(client)
        for c in cols:
            if c.get("id") == target:
                return c
        for c in cols:
            if (c.get("name") or "").lower() == target.lower():
                return c
        partial = [c for c in cols if target.lower() in (c.get("name") or "").lower()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            names = ", ".join(c.get("name", "?") for c in partial)
            raise RuntimeError(
                f"Multiple collections match '{target}': {names}. Ask the user to pick one."
            )
        names = ", ".join(c.get("name", "?") for c in cols) or "none"
        raise RuntimeError(f"No collection matches '{target}'. Available collections: {names}")

    async def _get_collection_files(self, client: httpx.AsyncClient, collection_id: str) -> list:
        r = await client.get(
            f"{self._base()}/api/v1/knowledge/{collection_id}", headers=self._headers()
        )
        r.raise_for_status()
        files = r.json().get("files", []) or []
        out = []
        for f in files:
            fid = f.get("id")
            name = (f.get("meta") or {}).get("name") or f.get("filename") or f.get("name") or ""
            out.append({"id": fid, "name": name})
        return out

    async def _download_file(self, client: httpx.AsyncClient, file_id: str) -> bytes:
        r = await client.get(
            f"{self._base()}/api/v1/files/{file_id}/content", headers=self._headers()
        )
        r.raise_for_status()
        return r.content

    def _convert_bytes(self, xlsx_bytes: bytes, display_name: str) -> str:
        lines = []
        xl = pd.ExcelFile(io.BytesIO(xlsx_bytes))
        for sheet in xl.sheet_names:
            df = xl.parse(sheet).dropna(how="all")
            if df.empty:
                continue
            lines.append(f"### File: {display_name} | Sheet: {sheet}")
            lines.append(f"Columns: {', '.join(str(c) for c in df.columns)}")
            for _, row in df.iterrows():
                parts = [
                    f"{col}: {row[col]}"
                    for col in df.columns
                    if pd.notna(row[col]) and str(row[col]).strip() != ""
                ]
                if parts:
                    lines.append(f"[{display_name} / {sheet}] " + " | ".join(parts))
            lines.append("")
        return "\n".join(lines)

    async def _upload_md(self, client: httpx.AsyncClient, name: str, text: str) -> str:
        r = await client.post(
            f"{self._base()}/api/v1/files/",
            headers=self._headers(),
            files={"file": (name, text.encode("utf-8"), "text/plain")},
        )
        r.raise_for_status()
        return r.json()["id"]

    async def _add_to_collection(self, client: httpx.AsyncClient, collection_id: str, file_id: str):
        r = await client.post(
            f"{self._base()}/api/v1/knowledge/{collection_id}/file/add",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"file_id": file_id},
        )
        r.raise_for_status()

    async def _remove_from_collection(
        self, client: httpx.AsyncClient, collection_id: str, file_id: str
    ) -> bool:
        try:
            r = await client.post(
                f"{self._base()}/api/v1/knowledge/{collection_id}/file/remove",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"file_id": file_id},
            )
            return r.status_code < 400
        except httpx.HTTPError:
            return False

    def _state_path(self) -> Path:
        p = Path(self.valves.state_dir) / "state.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load_state(self) -> dict:
        p = self._state_path()
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return {}
        return {}

    def _save_state(self, state: dict):
        self._state_path().write_text(json.dumps(state, indent=2))

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0))

    # ------------------------------ tools --------------------------------

    async def list_collections(self) -> str:
        """
        List all Knowledge collections with how many Excel files each contains.
        Use this when the user hasn't said which collection to work with.
        """
        try:
            self._check_config()
            async with self._client() as client:
                cols = await self._get_collections(client)
                if not cols:
                    return "No Knowledge collections found."
                lines = []
                for c in cols:
                    try:
                        files = await self._get_collection_files(client, c["id"])
                        n_xlsx = sum(
                            1 for f in files if re.search(r"\.xlsx?$", f["name"], re.I)
                        )
                        n_conv = sum(
                            1 for f in files if f["name"].endswith(".converted.md")
                        )
                        lines.append(
                            f"- {c.get('name','?')} — {len(files)} files "
                            f"({n_xlsx} excel to convert, {n_conv} already converted)"
                        )
                    except Exception:
                        lines.append(f"- {c.get('name','?')} — (could not read files)")
                return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    async def list_excels_in_collection(self, collection: str = "") -> str:
        """
        List the Excel files inside one Knowledge collection.

        :param collection: Collection name (or ID). Partial names work if unambiguous.
        """
        try:
            self._check_config()
            async with self._client() as client:
                col = await self._resolve_collection(client, collection)
                files = await self._get_collection_files(client, col["id"])
        except Exception as e:
            return f"Error: {e}"
        excels = [f["name"] for f in files if re.search(r"\.xlsx?$", f["name"], re.I)]
        converted = [f["name"] for f in files if f["name"].endswith(".converted.md")]
        lines = [f"Collection: {col.get('name','?')}"]
        lines.append(
            "Excel files to convert:\n" + "\n".join(f"- {n}" for n in excels)
            if excels
            else "No raw Excel files in this collection."
        )
        if converted:
            lines.append("Already converted:\n" + "\n".join(f"- {n}" for n in converted))
        return "\n".join(lines)

    async def convert_excel_in_collection(self, file_name: str, collection: str = "") -> str:
        """
        Fetch one Excel file from the chosen Knowledge collection, convert it to
        RAG-friendly row-text (.md), and index the converted version back into
        the same collection, replacing any previous converted version. If the
        remove_original_xlsx valve is on, the raw .xlsx is removed afterwards.

        :param file_name: Excel file name as shown in the collection, e.g. 'invoices.xlsx'
        :param collection: Collection name (or ID). Partial names work if unambiguous.
        """
        try:
            self._check_config()
            async with self._client() as client:
                col = await self._resolve_collection(client, collection)
                files = await self._get_collection_files(client, col["id"])

                match = next(
                    (f for f in files if f["name"].lower() == file_name.lower()), None
                )
                if not match:
                    excels = [
                        f["name"] for f in files if re.search(r"\.xlsx?$", f["name"], re.I)
                    ]
                    return (
                        f"'{file_name}' not found in collection '{col.get('name','?')}'. "
                        f"Excel files there: {excels or 'none'}"
                    )

                raw = await self._download_file(client, match["id"])
                text = self._convert_bytes(raw, match["name"])
                if not text.strip():
                    return f"'{file_name}' contains no data — nothing to index."

                state = self._load_state()
                state_key = f"{col['id']}::{match['name']}"
                notes = []

                conv_name = (
                    re.sub(r"\.xlsx?$", "", match["name"], flags=re.I) + ".converted.md"
                )
                old_id = state.get(state_key)
                if not old_id:
                    prev = next((f for f in files if f["name"] == conv_name), None)
                    old_id = prev["id"] if prev else None
                if old_id and await self._remove_from_collection(client, col["id"], old_id):
                    notes.append("old converted version removed")

                new_id = await self._upload_md(client, conv_name, text)
                await self._add_to_collection(client, col["id"], new_id)
                state[state_key] = new_id
                self._save_state(state)

                if self.valves.remove_original_xlsx:
                    if await self._remove_from_collection(client, col["id"], match["id"]):
                        notes.append("raw .xlsx removed from collection")
                    else:
                        notes.append("warning: could not remove raw .xlsx")

            rows = sum(1 for l in text.splitlines() if l.startswith("["))
            n = self.valves.max_preview_lines
            preview = "\n".join(text.splitlines()[:n])
            note_str = f" ({'; '.join(notes)})" if notes else ""
            return (
                f"Done: '{match['name']}' in collection '{col.get('name','?')}' converted "
                f"({rows} data rows) and indexed as '{conv_name}'{note_str}. "
                f"Now searchable via RAG.\n\nPreview:\n{preview}"
            )
        except Exception as e:
            return f"Error: {e}"

    async def convert_all_excels_in_collection(self, collection: str = "") -> str:
        """
        Convert and index EVERY Excel file in the chosen Knowledge collection.

        :param collection: Collection name (or ID). Partial names work if unambiguous.
        """
        try:
            self._check_config()
            async with self._client() as client:
                col = await self._resolve_collection(client, collection)
                files = await self._get_collection_files(client, col["id"])
        except Exception as e:
            return f"Error: {e}"
        excels = [f for f in files if re.search(r"\.xlsx?$", f["name"], re.I)]
        if not excels:
            return f"No Excel files found in collection '{col.get('name','?')}'."
        results = []
        for f in excels:
            res = await self.convert_excel_in_collection(f["name"], col["id"])
            results.append(res.split("\n\n")[0])
            await asyncio.sleep(0.5)
        return "\n".join(results)
