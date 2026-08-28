"""
title: Excel Query & Export Tools
author: you
description: Query live Excel files (list, describe, filter, aggregate) and export results to downloadable .xlsx files.
required_open_webui_version: 0.4.0
requirements: pandas, openpyxl
version: 1.0
"""

import os
import re
import time
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        excel_dir: str = Field(
            default="/opt/data/excels",
            description="Folder on the server containing the Excel files",
        )
        export_dir: str = Field(
            default="/opt/data/exports",
            description="Folder where exported .xlsx files are written",
        )
        export_base_url: str = Field(
            default="http://your-vps-ip:8081/exports",
            description="Public base URL that serves export_dir (e.g. via nginx)",
        )
        max_rows_returned: int = Field(
            default=50,
            description="Max rows returned to the chat before suggesting export",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ------------------------- helpers ---------------------------------

    def _resolve(self, file_name: str) -> Path:
        """Safely resolve a file inside excel_dir (no path escapes)."""
        base = Path(self.valves.excel_dir).resolve()
        # match by name anywhere under the folder
        for p in base.rglob("*.xls*"):
            if p.name.lower() == file_name.lower():
                return p
        raise FileNotFoundError(
            f"File '{file_name}' not found. Use list_excel_files to see options."
        )

    def _load(self, file_name: str, sheet: str = "") -> pd.DataFrame:
        path = self._resolve(file_name)
        xl = pd.ExcelFile(path)
        sheet_name = sheet if sheet and sheet in xl.sheet_names else xl.sheet_names[0]
        df = xl.parse(sheet_name)
        return df.dropna(how="all")

    def _apply_filter(self, df: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
        if not column:
            return df
        if column not in df.columns:
            raise ValueError(
                f"Column '{column}' not found. Available: {list(df.columns)}"
            )
        series = df[column].astype(str).str.lower()
        return df[series.str.contains(str(value).lower(), na=False)]

    # ------------------------- tools -----------------------------------

    def list_excel_files(self) -> str:
        """
        List all Excel files available on the server, with their sheet names.
        Use this first when the user asks about spreadsheet data and you don't
        know which file to use.
        """
        base = Path(self.valves.excel_dir)
        if not base.exists():
            return f"Excel folder not found: {base}"
        lines = []
        for p in sorted(base.rglob("*.xls*")):
            if p.name.startswith("~$"):
                continue
            try:
                sheets = pd.ExcelFile(p).sheet_names
                lines.append(f"- {p.name} (sheets: {', '.join(sheets)})")
            except Exception as e:
                lines.append(f"- {p.name} (unreadable: {e})")
        return "\n".join(lines) if lines else "No Excel files found."

    def describe_sheet(self, file_name: str, sheet: str = "") -> str:
        """
        Show the columns, data types, row count and first 3 rows of a sheet.
        Use this before filtering/aggregating so you know the exact column names.

        :param file_name: Excel file name, e.g. 'invoices.xlsx'
        :param sheet: Sheet name (optional, defaults to the first sheet)
        """
        try:
            df = self._load(file_name, sheet)
        except Exception as e:
            return f"Error: {e}"
        info = [
            f"File: {file_name} | Rows: {len(df)}",
            f"Columns: {', '.join(f'{c} ({df[c].dtype})' for c in df.columns)}",
            "First rows:",
            df.head(3).to_markdown(index=False),
        ]
        return "\n".join(info)

    def query_excel(
        self,
        file_name: str,
        sheet: str = "",
        filter_column: str = "",
        filter_value: str = "",
        operation: str = "list",
        target_column: str = "",
    ) -> str:
        """
        Query an Excel sheet with an optional filter and an operation.
        Operations: 'list' (show matching rows), 'count', 'sum', 'mean',
        'min', 'max' (these need target_column with a numeric column).

        :param file_name: Excel file name, e.g. 'invoices.xlsx'
        :param sheet: Sheet name (optional)
        :param filter_column: Column to filter on (optional)
        :param filter_value: Value to match, case-insensitive substring (optional)
        :param operation: list | count | sum | mean | min | max
        :param target_column: Numeric column for sum/mean/min/max
        """
        try:
            df = self._load(file_name, sheet)
            df = self._apply_filter(df, filter_column, filter_value)
        except Exception as e:
            return f"Error: {e}"

        op = (operation or "list").lower()
        if op == "count":
            return f"Count: {len(df)}"
        if op in ("sum", "mean", "min", "max"):
            if target_column not in df.columns:
                return (
                    f"Error: target_column '{target_column}' not found. "
                    f"Available: {list(df.columns)}"
                )
            col = pd.to_numeric(df[target_column], errors="coerce").dropna()
            if col.empty:
                return f"Error: no numeric values in '{target_column}' after filtering."
            result = getattr(col, op)()
            return f"{op} of {target_column}: {result} (over {len(col)} rows)"

        # default: list rows
        n = self.valves.max_rows_returned
        shown = df.head(n)
        msg = shown.to_markdown(index=False)
        if len(df) > n:
            msg += (
                f"\n\n({len(df)} rows matched, showing first {n}. "
                "Use export_to_excel to get the full result as a file.)"
            )
        return msg if len(df) else "No matching rows."

    def export_to_excel(
        self,
        file_name: str,
        sheet: str = "",
        filter_column: str = "",
        filter_value: str = "",
        export_name: str = "export",
    ) -> str:
        """
        Filter an Excel sheet and export the matching rows to a new .xlsx
        file the user can download. Use this when the user asks for results
        'as a file', 'as excel', 'as a sheet', or when a query matches many rows.

        :param file_name: Source Excel file name
        :param sheet: Sheet name (optional)
        :param filter_column: Column to filter on (optional; empty = all rows)
        :param filter_value: Value to match (optional)
        :param export_name: Base name for the exported file
        """
        try:
            df = self._load(file_name, sheet)
            df = self._apply_filter(df, filter_column, filter_value)
        except Exception as e:
            return f"Error: {e}"
        if df.empty:
            return "No matching rows — nothing to export."

        out_dir = Path(self.valves.export_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", export_name) or "export"
        out_name = f"{safe}_{int(time.time())}.xlsx"
        out_path = out_dir / out_name
        try:
            df.to_excel(out_path, index=False)
        except Exception as e:
            return f"Error writing export: {e}"

        url = self.valves.export_base_url.rstrip("/") + "/" + out_name
        return (
            f"Exported {len(df)} rows to {out_name}.\n"
            f"Download link: {url}\n"
            "Tell the user the link and how many rows it contains."
        )
