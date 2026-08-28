"""
title: Knowledge Data Compute (Async)
author: you
description: Performs EXACT computations (sum, count, mean, min, max, group-by) on tabular data stored as .converted.md files in Knowledge collections. Use this for ANY totals, counts, or aggregations — never compute these mentally.
required_open_webui_version: 0.4.0
requirements: httpx
version: 1.0
"""

import re
import httpx
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        openwebui_url: str = Field(
            default="http://localhost:8080",
            description="Base URL of this Open WebUI instance (from the server itself)",
        )
        api_key: str = Field(
            default="",
            description="Open WebUI API key (Settings -> Account -> API Keys)",
        )
        default_collection: str = Field(
            default="",
            description="Optional default collection name/ID when the user doesn't specify",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ----------------------------- helpers ------------------------------

    def _headers(self):
        return {"Authorization": f"Bearer {self.valves.api_key}"}

    def _base(self):
        return self.valves.openwebui_url.rstrip("/")

    def _client(self):
        return httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0))

    def _check(self):
        if not self.valves.api_key:
            raise RuntimeError("api_key valve is not set.")

    async def _collections(self, client):
        r = await client.get(
            f"{self._base()}/api/v1/knowledge/", headers=self._headers()
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            data = data.get("items") or data.get("data") or []
        return data

    async def _resolve_collection(self, client, collection):
        target = (collection or self.valves.default_collection or "").strip()
        cols = await self._collections(client)
        if not target:
            if len(cols) == 1:
                return cols[0]
            raise RuntimeError(
                "No collection specified and multiple exist: "
                + ", ".join(c.get("name", "?") for c in cols)
            )
        for c in cols:
            if c.get("id") == target or (c.get("name") or "").lower() == target.lower():
                return c
        partial = [c for c in cols if target.lower() in (c.get("name") or "").lower()]
        if len(partial) == 1:
            return partial[0]
        raise RuntimeError(
            f"Collection '{target}' not found/ambiguous. Available: "
            + ", ".join(c.get("name", "?") for c in cols)
        )

    async def _collection_files(self, client, cid):
        r = await client.get(
            f"{self._base()}/api/v1/knowledge/{cid}", headers=self._headers()
        )
        r.raise_for_status()
        files = r.json().get("files", []) or []
        out = []
        for f in files:
            name = (
                (f.get("meta") or {}).get("name")
                or f.get("filename")
                or f.get("name")
                or ""
            )
            out.append({"id": f.get("id"), "name": name})
        return out

    async def _file_text(self, client, file_id):
        r = await client.get(
            f"{self._base()}/api/v1/files/{file_id}/content", headers=self._headers()
        )
        r.raise_for_status()
        return r.text

    def _parse_rows(self, text):
        """Parse converted row-lines into list of dicts with _sheet key."""
        rows = []
        for line in text.splitlines():
            m = re.match(r"^\[([^\]/]+)/\s*([^\]]+)\]\s*(.+)$", line)
            if not m:
                continue
            sheet = m.group(2).strip()
            body = m.group(3)
            rec = {"_sheet": sheet}
            for part in body.split(" | "):
                if ": " in part:
                    k, v = part.split(": ", 1)
                    rec[k.strip()] = v.strip()
            rows.append(rec)
        return rows

    @staticmethod
    def _num(v):
        try:
            f = float(str(v).replace(",", ""))
            return f
        except (ValueError, TypeError):
            return None

    async def _load_rows(self, client, collection, file_name, sheet):
        col = await self._resolve_collection(client, collection)
        files = await self._collection_files(client, col["id"])
        data_files = [f for f in files if f["name"].endswith(".md")]
        if file_name:
            match = [f for f in data_files if file_name.lower() in f["name"].lower()]
            if not match:
                raise RuntimeError(
                    f"No data file matching '{file_name}' in '{col.get('name')}'. "
                    f"Files: {[f['name'] for f in data_files]}"
                )
            data_files = match[:1]
        rows = []
        used = []
        for f in data_files:
            text = await self._file_text(client, f["id"])
            parsed = self._parse_rows(text)
            if parsed:
                used.append(f["name"])
                rows.extend(parsed)
        if sheet:
            rows = [r for r in rows if r["_sheet"].lower() == sheet.lower()]
        return col.get("name", "?"), used, rows

    @staticmethod
    def _apply_filter(rows, filter_column, filter_value):
        if not filter_column:
            return rows
        fv = str(filter_value).lower()
        out = []
        for r in rows:
            val = r.get(filter_column)
            if val is None:
                continue
            if str(val).lower() == fv or fv in str(val).lower():
                out.append(r)
        return out

    # ------------------------------ tools --------------------------------

    async def list_data_sources(self, collection: str = "") -> str:
        """
        List the data files and sheets available for computation in a
        Knowledge collection, with row counts and column names.
        Use this first if unsure what data exists.

        :param collection: Collection name or ID (optional if default set)
        """
        try:
            self._check()
            async with self._client() as client:
                cname, used, rows = await self._load_rows(client, collection, "", "")
        except Exception as e:
            return f"Error: {e}"
        if not rows:
            return f"No parseable data rows found in collection '{cname}'."
        sheets = {}
        for r in rows:
            s = r["_sheet"]
            if s not in sheets:
                sheets[s] = {"count": 0, "cols": set()}
            sheets[s]["count"] += 1
            sheets[s]["cols"].update(k for k in r.keys() if k != "_sheet")
        lines = [f"Collection: {cname} | Files: {', '.join(used)}"]
        for s, info in sheets.items():
            lines.append(
                f"- Sheet '{s}': {info['count']} rows | Columns: {', '.join(sorted(info['cols']))}"
            )
        return "\n".join(lines)

    async def compute_aggregate(
        self,
        operation: str,
        target_column: str = "",
        file_name: str = "",
        sheet: str = "",
        filter_column: str = "",
        filter_value: str = "",
        collection: str = "",
    ) -> str:
        """
        Compute an EXACT aggregate over data rows. ALWAYS use this for totals,
        sums, counts, averages — never calculate these yourself.
        Operations: 'sum', 'mean', 'min', 'max' (need target_column with numeric
        values) or 'count' (target_column optional).

        Example: total of pending invoices ->
        operation='sum', target_column='Total (INR)',
        filter_column='Status', filter_value='Pending', sheet='Invoices'

        :param operation: sum | count | mean | min | max
        :param target_column: Numeric column to aggregate (exact name incl. e.g. '(INR)')
        :param file_name: Limit to one data file, e.g. 'client_invoices' (optional)
        :param sheet: Limit to one sheet, e.g. 'Invoices' (optional but recommended)
        :param filter_column: Column to filter on (optional)
        :param filter_value: Value to match, exact or substring, case-insensitive (optional)
        :param collection: Collection name or ID (optional if default set)
        """
        try:
            self._check()
            async with self._client() as client:
                cname, used, rows = await self._load_rows(
                    client, collection, file_name, sheet
                )
        except Exception as e:
            return f"Error: {e}"

        rows = self._apply_filter(rows, filter_column, filter_value)
        op = (operation or "").lower()
        filt = f" where {filter_column}={filter_value}" if filter_column else ""
        scope = f"[{cname} / {', '.join(used)}{' / sheet ' + sheet if sheet else ''}]"

        if op == "count":
            return f"EXACT RESULT {scope}: count{filt} = {len(rows)} rows"

        if op not in ("sum", "mean", "min", "max"):
            return "Error: operation must be one of sum, count, mean, min, max."
        if not target_column:
            return "Error: target_column is required for sum/mean/min/max."

        vals = []
        skipped = 0
        for r in rows:
            if target_column in r:
                n = self._num(r[target_column])
                if n is None:
                    skipped += 1
                else:
                    vals.append(n)
        if not vals:
            cols = sorted({k for r in rows for k in r.keys() if k != "_sheet"})
            return (
                f"Error: no numeric values in column '{target_column}'{filt}. "
                f"Available columns: {cols}"
            )
        if op == "sum":
            res = sum(vals)
        elif op == "mean":
            res = sum(vals) / len(vals)
        elif op == "min":
            res = min(vals)
        else:
            res = max(vals)
        res_str = f"{res:,.2f}".rstrip("0").rstrip(".")
        note = f" ({skipped} non-numeric rows skipped)" if skipped else ""
        return (
            f"EXACT RESULT {scope}: {op} of '{target_column}'{filt} = {res_str} "
            f"over {len(vals)} rows{note}. Quote this number verbatim."
        )

    async def group_summary(
        self,
        group_column: str,
        operation: str = "sum",
        target_column: str = "",
        file_name: str = "",
        sheet: str = "",
        filter_column: str = "",
        filter_value: str = "",
        collection: str = "",
    ) -> str:
        """
        Compute an EXACT aggregate grouped by a column — e.g. outstanding amount
        per client, matter count per advocate. ALWAYS use this instead of
        grouping/adding manually.

        Example: pending amount per client ->
        group_column='Client', operation='sum', target_column='Total (INR)',
        filter_column='Status', filter_value='Pending', sheet='Invoices'

        :param group_column: Column to group by (exact name)
        :param operation: sum | count | mean | min | max
        :param target_column: Numeric column (not needed for count)
        :param file_name: Limit to one data file (optional)
        :param sheet: Limit to one sheet (optional but recommended)
        :param filter_column: Column to filter on first (optional)
        :param filter_value: Filter value (optional)
        :param collection: Collection name or ID (optional if default set)
        """
        try:
            self._check()
            async with self._client() as client:
                cname, used, rows = await self._load_rows(
                    client, collection, file_name, sheet
                )
        except Exception as e:
            return f"Error: {e}"

        rows = self._apply_filter(rows, filter_column, filter_value)
        op = (operation or "sum").lower()
        groups = {}
        for r in rows:
            key = r.get(group_column)
            if key is None:
                continue
            groups.setdefault(key, []).append(r)
        if not groups:
            cols = sorted({k for r in rows for k in r.keys() if k != "_sheet"})
            return f"Error: no values for group column '{group_column}'. Available columns: {cols}"

        lines = []
        for key in sorted(groups):
            g = groups[key]
            if op == "count":
                lines.append(f"- {key}: {len(g)}")
                continue
            vals = [self._num(r.get(target_column)) for r in g]
            vals = [v for v in vals if v is not None]
            if not vals:
                lines.append(f"- {key}: (no numeric '{target_column}')")
                continue
            if op == "sum":
                res = sum(vals)
            elif op == "mean":
                res = sum(vals) / len(vals)
            elif op == "min":
                res = min(vals)
            else:
                res = max(vals)
            lines.append(
                f"- {key}: {res:,.2f}".rstrip("0").rstrip(".") + f" ({len(vals)} rows)"
            )
        filt = f" where {filter_column}={filter_value}" if filter_column else ""
        head = (
            f"EXACT RESULT [{cname} / {', '.join(used)}]: {op} of "
            f"'{target_column or 'rows'}' by '{group_column}'{filt}. Quote verbatim:"
        )
        return head + "\n" + "\n".join(lines)
