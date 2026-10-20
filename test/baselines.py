"""Reading approved wording and tables out of the documents (not a pytest
module): a baseline test pins every fenced line of the sections that hold
agent-facing text, the log's tests pin the events and their levels to
LOGGING.md §4's tables, and the plugin's test pins each class's
`placement` to node_classes/COMMON.md §1's table, so the code and the
documents cannot drift apart."""

from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"


def fenced_blocks(doc: Path, *section_prefixes: str) -> list[list[str]]:
    """Every ``` fence within the `## ` sections whose title starts with one
    of `section_prefixes`, in document order, each as its lines.  A fence
    inside a list item is indented: its lines are read less that indent,
    and it closes at a fence line of the same indent."""
    blocks: list[list[str]] = []
    in_section, indent = False, None            # the open fence's indent; None outside one
    for line in doc.read_text().splitlines():
        if line.startswith("## "):
            in_section = line.removeprefix("## ").startswith(section_prefixes)
        elif in_section and indent is None and line.lstrip(" ").startswith("```"):
            indent = " " * (len(line) - len(line.lstrip(" ")))
            blocks.append([])
        elif in_section and indent is not None and line.startswith(indent + "```"):
            indent = None
        elif in_section and indent is not None:
            blocks[-1].append(line.removeprefix(indent))
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
            cells = _cells(line)
            tables[category][cells[0].strip("`")] = cells[1]
    return tables


def table_rows(doc: Path, *section_prefixes: str) -> list[list[str]]:
    """The cells of every table row opening with a backticked cell, within
    the `## ` sections whose title starts with one of `section_prefixes`."""
    rows: list[list[str]] = []
    in_section = False
    for line in doc.read_text().splitlines():
        if line.startswith("## "):
            in_section = line.removeprefix("## ").startswith(section_prefixes)
        elif in_section and line.startswith("| `"):
            rows.append(_cells(line))
    return rows


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip("|").split("|")]


def stated(doc: Path, label: str) -> list[str]:
    """The backticked text of every prose line `<label>: \\`...\\``, in
    document order — TOOL_SCHEMAS.md's `Tool description:` lines."""
    return [line.split("`")[1] for line in doc.read_text().splitlines()
            if line.startswith(f"{label}: `")]
