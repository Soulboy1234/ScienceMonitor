#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-png", action="store_true")
    parser.add_argument("input_pdf")
    parser.add_argument("output_prefix")
    parser.add_argument("-h", "--help", action="help")
    args = parser.parse_args()

    doc = fitz.open(args.input_pdf)
    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    for idx, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        suffix = "png" if args.png else "ppm"
        out = prefix.parent / f"{prefix.name}-{idx}.{suffix}"
        pix.save(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
