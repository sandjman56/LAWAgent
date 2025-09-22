from __future__ import annotations

import os
from pathlib import Path

PDF_MAGIC = b"%PDF-"


def sanitize_filename(filename: str) -> str:
    return os.path.basename(filename).replace("\x00", "")


def is_pdf_magic(data: bytes) -> bool:
    return data.startswith(PDF_MAGIC)


def ensure_pdf(path: Path) -> bool:
    with path.open("rb") as file:
        header = file.read(len(PDF_MAGIC))
    return is_pdf_magic(header)
