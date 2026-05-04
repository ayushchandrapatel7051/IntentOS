"""
Universal Text Extractor
Supports: PDF, DOCX, DOC, XLSX, XLS, ODS, PPTX, CSV, TSV, JSON, JSONL,
          TXT, Markdown, code files, RTF, EPUB, IPYNB, images (OCR), archives
"""

import os
import sys
import json
import argparse
from pathlib import Path


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _require(pkg, install_hint):
    """Attempt import; raise with install hint on failure."""
    try:
        return __import__(pkg)
    except ImportError:
        raise ImportError(f"Missing package '{pkg}'. Install: {install_hint}")


# ──────────────────────────────────────────────
# Extractors
# ──────────────────────────────────────────────

def extract_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pip install pypdf")
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        pages.append(f"--- Page {i} ---\n{text}")
    return "\n\n".join(pages)


def extract_docx(path: str) -> str:
    try:
        import docx
    except ImportError:
        raise ImportError("pip install python-docx")
    doc = docx.Document(path)
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    # Tables
    for table in doc.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def extract_xlsx(path: str, ext: str = ".xlsx") -> str:
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pip install pandas openpyxl")

    engine_map = {".xls": "xlrd", ".ods": "odf"}
    engine = engine_map.get(ext, "openpyxl")

    xl = pd.ExcelFile(path, engine=engine)
    sheets = []
    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name)
        sheets.append(f"=== Sheet: {sheet_name} ===\n{df.to_string(index=False)}")
    return "\n\n".join(sheets)


def extract_pptx(path: str) -> str:
    try:
        from pptx import Presentation
    except ImportError:
        raise ImportError("pip install python-pptx")
    prs = Presentation(path)
    slides = []
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                texts.append(shape.text)
        slides.append(f"--- Slide {i} ---\n" + "\n".join(texts))
    return "\n\n".join(slides)


def extract_csv(path: str, sep: str = ",") -> str:
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pip install pandas")
    df = pd.read_csv(path, sep=sep)
    return df.to_string(index=False)


def extract_json(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    try:
        data = json.loads(content)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return content  # Return raw if invalid JSON


def extract_jsonl(path: str) -> str:
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    lines.append(f"[{i}] {json.dumps(obj, ensure_ascii=False)}")
                except json.JSONDecodeError:
                    lines.append(f"[{i}] {line}")
    return "\n".join(lines)


def extract_text_plain(path: str) -> str:
    """For .txt, .md, code files, logs, etc."""
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError(f"Could not decode file with tried encodings: {encodings}")


def extract_rtf(path: str) -> str:
    try:
        from striprtf.striprtf import rtf_to_text
    except ImportError:
        raise ImportError("pip install striprtf")
    with open(path, "r", encoding="latin-1") as f:
        return rtf_to_text(f.read())


def extract_epub(path: str) -> str:
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("pip install EbookLib beautifulsoup4")
    book = epub.read_epub(path)
    texts = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.content, "html.parser")
        texts.append(soup.get_text(separator="\n"))
    return "\n\n".join(texts)


def extract_ipynb(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    cells = []
    for cell in nb.get("cells", []):
        cell_type = cell.get("cell_type", "")
        source = "".join(cell.get("source", []))
        if cell_type == "markdown":
            cells.append(f"[MARKDOWN]\n{source}")
        elif cell_type == "code":
            cells.append(f"[CODE]\n{source}")
            # Include output text if present
            for output in cell.get("outputs", []):
                if output.get("output_type") in ("stream", "execute_result", "display_data"):
                    out_text = "".join(output.get("text", output.get("data", {}).get("text/plain", [])))
                    if out_text.strip():
                        cells.append(f"[OUTPUT]\n{out_text}")
    return "\n\n".join(cells)


def extract_image_ocr(path: str) -> str:
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        raise ImportError("pip install Pillow pytesseract  (also install Tesseract OCR binary)")
    img = Image.open(path)
    return pytesseract.image_to_string(img)


def extract_archive_listing(path: str) -> str:
    """Lists archive contents without extracting."""
    import zipfile, tarfile
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
        return f"ZIP archive — {len(names)} entries:\n" + "\n".join(names)
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as tf:
            names = tf.getnames()
        return f"TAR archive — {len(names)} entries:\n" + "\n".join(names)
    return "[Archive format not recognized]"


# ──────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────

# Code / plain-text extensions
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".hpp", ".cs", ".go", ".rb", ".php", ".rs", ".swift", ".kt", ".r",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".sql", ".html", ".css",
    ".scss", ".less", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".env", ".md", ".rst", ".tex", ".log", ".txt", ".gitignore",
    ".dockerfile", ".makefile",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z"}


def extract(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = p.suffix.lower()

    if ext == ".pdf":
        return extract_pdf(path)
    elif ext in (".docx",):
        return extract_docx(path)
    elif ext in (".xlsx", ".xlsm"):
        return extract_xlsx(path, ".xlsx")
    elif ext == ".xls":
        return extract_xlsx(path, ".xls")
    elif ext == ".ods":
        return extract_xlsx(path, ".ods")
    elif ext == ".pptx":
        return extract_pptx(path)
    elif ext == ".csv":
        return extract_csv(path, sep=",")
    elif ext == ".tsv":
        return extract_csv(path, sep="\t")
    elif ext == ".json":
        return extract_json(path)
    elif ext == ".jsonl":
        return extract_jsonl(path)
    elif ext == ".rtf":
        return extract_rtf(path)
    elif ext == ".epub":
        return extract_epub(path)
    elif ext == ".ipynb":
        return extract_ipynb(path)
    elif ext in IMAGE_EXTENSIONS:
        return extract_image_ocr(path)
    elif ext in ARCHIVE_EXTENSIONS:
        return extract_archive_listing(path)
    elif ext in CODE_EXTENSIONS or ext == "":
        return extract_text_plain(path)
    else:
        # Best-effort: try plain text for unknown extensions
        print(f"[WARN] Unknown extension '{ext}', attempting plain text read.", file=sys.stderr)
        return extract_text_plain(path)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract text from PDF, Word, Excel, CSV, JSON, code files, images, and more."
    )
    parser.add_argument("files", nargs="+", help="File path(s) to extract text from")
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Directory to save .txt output files (default: print to stdout)"
    )
    parser.add_argument(
        "--separator",
        default="\n" + "=" * 60 + "\n",
        help="Separator between multiple files when printing to stdout"
    )
    args = parser.parse_args()

    for file_path in args.files:
        print(f"[INFO] Processing: {file_path}", file=sys.stderr)
        try:
            text = extract(file_path)
        except Exception as e:
            print(f"[ERROR] {file_path}: {e}", file=sys.stderr)
            continue

        if args.output_dir:
            out_dir = Path(args.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / (Path(file_path).stem + ".txt")
            out_file.write_text(text, encoding="utf-8")
            print(f"[SAVED] {out_file}", file=sys.stderr)
        else:
            if len(args.files) > 1:
                print(f"\n{'='*60}")
                print(f"FILE: {file_path}")
                print(f"{'='*60}\n")
            print(text)


if __name__ == "__main__":
    main()
