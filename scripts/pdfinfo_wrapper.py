#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pypdf


def format_bool(value: bool) -> str:
    return "yes" if value else "no"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf")
    args = parser.parse_args()

    path = Path(args.input_pdf)
    reader = pypdf.PdfReader(str(path))
    meta = reader.metadata or {}
    first_page = reader.pages[0] if reader.pages else None
    width = float(first_page.mediabox.width) if first_page else 0.0
    height = float(first_page.mediabox.height) if first_page else 0.0

    print(f"Title: {meta.get('/Title', '')}")
    print(f"Author: {meta.get('/Author', '')}")
    print(f"Creator: {meta.get('/Creator', '')}")
    print(f"Producer: {meta.get('/Producer', '')}")
    print(f"Pages: {len(reader.pages)}")
    print(f"Encrypted: {format_bool(reader.is_encrypted)}")
    if first_page:
        print(f"Page size: {width:.0f} x {height:.0f} pts")
    print(f"File size: {path.stat().st_size} bytes")
    header = getattr(reader, "pdf_header", "")
    if isinstance(header, bytes):
        header = header.decode(errors="ignore")
    print(f"PDF version: {header or 'unknown'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
