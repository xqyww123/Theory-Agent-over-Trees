"""Reading approved wording and the event tables out of the documents (not
a pytest module): a baseline test pins every fenced line of the sections
that hold agent-facing text, and the log's tests pin the events and their
levels to LOGGING.md §4's tables, so the code and the documents cannot
drift apart."""

from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"


def fenced_blocks(doc: Path, *section_prefixes: str) -> list[list[str]]:
    """Every ``` fence within the `## ` sections whose title starts with one
    of `section_prefixes`, in document order, each as its lines."""
    blocks: list[list[str]] = []
    in_section, in_fence = False, False
    for line in doc.read_text().splitlines():
        if line.startswith("## "):
            in_section = line.removeprefix("## ").startswith(section_prefixes)
        elif in_section and line.startswith("```"):
            in_fence = not in_fence
            if in_fence:
                blocks.append([])
        elif in_section and in_fence:
            blocks[-1].append(line)
    return blocks


def fenced_lines(doc: Path, *section_prefixes: str) -> list[str]:
    """Every non-empty line inside a ``` fence, within the `## ` sections
    whose title starts with one of `section_prefixes`, in document order."""
    return [line for block in fenced_blocks(doc, *section_prefixes) for line in block if line]


def event_tables(doc: Path, section_prefix: str) -> dict[str, dict[str, str]]:
    """The event tables of the `## ` section whose title starts with
    `section_prefix`, one per `### `<category>`` heading: each row's event
    (the first cell, its backticks stripped) to its level (the second
    cell) — LOGGING.md §4."""
    tables: dict[str, dict[str, str]] = {}
    in_section, category = False, ""
    for line in doc.read_text().splitlines():
        if line.startswith("## "):
            in_section = line.removeprefix("## ").startswith(section_prefix)
        elif in_section and line.startswith("### "):
            category = line.removeprefix("### ").strip("`")
            tables[category] = {}
        elif in_section and category and line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            tables[category][cells[0].strip("`")] = cells[1]
    return tables


def stated(doc: Path, label: str) -> list[str]:
    """The backticked text of every prose line `<label>: \\`...\\``, in
    document order — TOOL_SCHEMAS.md's `Tool description:` lines."""
    return [line.split("`")[1] for line in doc.read_text().splitlines()
            if line.startswith(f"{label}: `")]
