#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pdfplumber


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-layout", action="store_true")
    parser.add_argument("-nopgbrk", action="store_true")
    parser.add_argument("-f", type=int, default=1)
    parser.add_argument("-l", type=int, default=None)
    parser.add_argument("input_pdf")
    parser.add_argument("output_txt", nargs="?")
    parser.add_argument("-h", "--help", action="help")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_pdf = Path(args.input_pdf)
    output_txt = args.output_txt
    start = max(args.f - 1, 0)
    end = args.l
    pages_text: list[str] = []

    with pdfplumber.open(input_pdf) as pdf:
        selected_pages = pdf.pages[start:end]
        for page in selected_pages:
            text = page.extract_text(layout=args.layout) or ""
            pages_text.append(text.rstrip())

    separator = "\n\n" if args.nopgbrk else "\n\f\n"
    content = separator.join(pages_text)

    if output_txt and output_txt != "-":
        Path(output_txt).write_text(content)
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
