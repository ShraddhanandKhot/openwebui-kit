"""AnyDoc ingestion hook for OpenWebUI's file pipeline.

Runs the filtration layer + AnyDoc markdown converter BEFORE a file is chunked
and embedded. Returns clean markdown, or None on ANY failure so the caller
falls back to OpenWebUI's stock loader (ingestion never breaks).

Lives in the container's persistent dir: /app/backend/data/anydoc_py/
(requires filtration_layer.py and anydoc_markdown_converter.py alongside it).
"""

import logging
import os
import sys

log = logging.getLogger("open_webui")

# Make sure the pipeline modules are importable (this dir + fallback).
for _d in ("/app/backend/data/anydoc_py", "/tmp/anydoc_py"):
    if _d not in sys.path and os.path.isdir(_d):
        sys.path.insert(0, _d)
        break

from filtration_layer import analyze_file_complexity
from anydoc_markdown_converter import AnyDocMarkdownConverter

_converter = None


def _get_converter() -> AnyDocMarkdownConverter:
    global _converter
    if _converter is None:
        # enable_ocr=True -> scanned PDFs and images get OCR'd
        _converter = AnyDocMarkdownConverter(enable_ocr=True, enable_vision=False)
    return _converter


def convert_file_to_markdown(file_path: str, filename: str = "") -> str | None:
    """Convert a document to clean markdown via the filtration pipeline.

    - Simple files: direct conversion (fast path).
    - Complex files (scanned, images, tables, forms, comments): filtration layer
      routes them through OCR / enhanced extraction first.
    - Returns None (never raises) so the caller can fall back to the stock loader.
    """
    name = filename or file_path
    try:
        report = analyze_file_complexity(file_path)

        result = _get_converter().convert(
            file_path,
            extract_images=False,   # image file refs are noise for RAG; text only
            extract_tables=True,    # tables become real markdown tables
            image_output_dir="/tmp/anydoc_images",
        )

        if result.success and result.markdown and result.markdown.strip():
            md = result.markdown.strip()
            log.info(
                "AnyDoc hook: %s -> level=%s method=%s (%d chars)",
                name,
                report.complexity_level.value if report else "?",
                result.extraction_method,
                len(md),
            )
            return md

        log.warning("AnyDoc hook: conversion failed for %s: %s", name, result.error)
        return None
    except Exception as e:
        log.warning("AnyDoc hook: exception for %s: %s", name, e)
        return None
