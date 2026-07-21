"""Rebuild individual files and folder structure from MIGRATION-FILES-CONTENT.txt.

The consolidated file contains records in this format:

    ================================================================================
    Area: <area>
    File path: <relative/path>
    ================================================================================
    <file content>
    <blank line>

Usage:
    python rebuild_from_content.py <input> <output-root>

    <input>        Either the consolidated MIGRATION-FILES-CONTENT.txt, or a
                   directory containing split part files
                   (MIGRATION-FILES-CONTENT-PART-XX-of-NN.txt).
    <output-root>  Directory where the file/folder structure will be created.

Examples:
    python rebuild_from_content.py MIGRATION-FILES-CONTENT.txt C:\\rebuild
    python rebuild_from_content.py split-parts C:\\rebuild

Notes:
- Handles large files split across parts with "[chunk k of m]" markers.
- Skips placeholder records (self-referential consolidated file, missing files).
- If the consolidated file embeds a snapshot of itself, duplicate records are
  detected and only the first occurrence of each file path is written.
- Binary files (e.g. .xlsx) cannot be restored faithfully from the text dump;
  they are written as-is and reported so you can copy them separately.
"""

import os
import re
import sys

SEP = "=" * 80
HEADER_RE = re.compile(
    r"^={80}\nArea: (?P<area>.*)\nFile path: (?P<fpath>.*)\n={80}\n",
    re.MULTILINE,
)
CHUNK_RE = re.compile(
    r"^(?P<path>.*?)\s+\[chunk (?P<k>\d+) of (?P<m>\d+)\]", re.IGNORECASE
)
PART_HEADER_RE = re.compile(r"^### PART \d+ of \d+ .*###\s*\n?", re.MULTILINE)
CONTINUES_MARKER = "[CONTINUES in next chunk...]"
SKIP_CONTENT_PREFIXES = (
    "[Self-referential record:",
    "[FILE NOT FOUND on disk]",
    "[ERROR reading file:",
)
BINARY_EXTS = {".xlsx", ".xlsm", ".xls", ".png", ".jpg", ".jpeg", ".gif",
               ".ico", ".pdf", ".zip", ".db", ".pyc", ".woff", ".woff2"}


def part_sort_key(name):
    m = re.search(r"PART-(\d+)", name)
    return int(m.group(1)) if m else 0


def load_input(path):
    """Return the full consolidated text from a file or a directory of parts."""
    if os.path.isdir(path):
        parts = sorted(
            (f for f in os.listdir(path)
             if f.upper().startswith("MIGRATION-FILES-CONTENT-PART")
             and f.lower().endswith(".txt")),
            key=part_sort_key,
        )
        if not parts:
            sys.exit(f"No MIGRATION-FILES-CONTENT-PART-*.txt files found in {path}")
        print(f"Reading {len(parts)} part files from {path}")
        texts = []
        for f in parts:
            with open(os.path.join(path, f), "r", encoding="utf-8") as fh:
                texts.append(PART_HEADER_RE.sub("", fh.read(), count=1))
        return "".join(texts)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def parse_records(text):
    """Yield (fpath, chunk_no, total_chunks, content) for every record."""
    headers = list(HEADER_RE.finditer(text))
    for i, m in enumerate(headers):
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        content = text[start:end]
        # strip the blank separator line appended after each record
        if content.endswith("\n\n"):
            content = content[:-1]
        fpath = m.group("fpath").strip()
        chunk_no, total_chunks = 1, 1
        cm = CHUNK_RE.match(fpath)
        if cm:
            fpath = cm.group("path").strip()
            chunk_no, total_chunks = int(cm.group("k")), int(cm.group("m"))
        # strip continuation marker line if present
        marker_at = content.rfind(CONTINUES_MARKER)
        if marker_at != -1:
            content = content[:marker_at].rstrip("\n") + "\n"
        yield fpath, chunk_no, total_chunks, content


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    input_path, out_root = sys.argv[1], sys.argv[2]

    text = load_input(input_path)
    written = {}          # fpath -> content written (first occurrence wins)
    pending = {}          # fpath -> {chunk_no: content, "total": m}
    skipped, duplicates, binaries = [], [], []

    def write_file(fpath, content):
        norm = fpath.replace("\\", "/")
        if norm in written:
            duplicates.append(norm)
            return
        if content == "\n":
            # empty source files are stored as a single newline in the dump
            content = ""
        dest = os.path.join(out_root, norm.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest) or out_root, exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        written[norm] = content
        if os.path.splitext(norm)[1].lower() in BINARY_EXTS:
            binaries.append(norm)

    for fpath, chunk_no, total_chunks, content in parse_records(text):
        first_line = content.split("\n", 1)[0]
        if any(first_line.startswith(p) for p in SKIP_CONTENT_PREFIXES):
            skipped.append((fpath, first_line[:60]))
            continue
        if total_chunks == 1:
            write_file(fpath, content)
        else:
            slot = pending.setdefault(fpath, {"total": total_chunks})
            slot[chunk_no] = content
            got = [k for k in slot if isinstance(k, int)]
            if len(got) == slot["total"]:
                joined = "".join(slot[k] for k in sorted(got))
                del pending[fpath]
                write_file(fpath, joined)

    print(f"\nFiles written: {len(written)}")
    print(f"Output root:   {os.path.abspath(out_root)}")
    if skipped:
        print(f"\nSkipped records ({len(skipped)}):")
        for fp, why in skipped:
            print(f"  - {fp}  ({why})")
    if duplicates:
        print(f"\nDuplicate records ignored (first occurrence kept): {len(duplicates)}")
    if pending:
        print(f"\nWARNING - incomplete chunked files (missing chunks): ")
        for fp, slot in pending.items():
            have = sorted(k for k in slot if isinstance(k, int))
            print(f"  - {fp}: have chunks {have} of {slot['total']}")
    if binaries:
        print(f"\nWARNING - binary files cannot be restored faithfully from a text "
              f"dump; copy these {len(binaries)} file(s) separately:")
        for fp in binaries:
            print(f"  - {fp}")


if __name__ == "__main__":
    main()
