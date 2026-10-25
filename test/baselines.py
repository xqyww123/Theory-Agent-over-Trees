"""Reading approved wording and tables out of the documents (not a pytest
module): a baseline test pins every fenced line of the sections that hold
agent-facing text, the log's tests pin the events and their levels to
LOGGING.md §4's tables, and the plugin's test pins the placement check's
answers to node_classes/COMMON.md §1's table, so the code and the
documents cannot drift apart."""

from collections.abc import Iterator
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"


def composed_refusal(kind: str, ancestor_id: str, remedy: str) -> str:
    """RENDER_BASELINES §3's form line filled in — the head for `kind`, with
    the article §2 states, and `ancestor_id`, then `remedy` —: what the
    placement check tells, composed from the documents alone."""
    [form] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "3.") if line.startswith("<A|An>")]
    article = "An" if kind[:1].lower() in "aeiou" else "A"
    return (form.replace("<A|An>", article).replace("<node's kind>", kind)
            .replace("<ancestor's full id>", ancestor_id).replace("<remedy>", remedy))


def _section_lines(doc: Path, *section_prefixes: str) -> Iterator[str]:
    """The lines inside the `## ` sections whose title starts with one of
    `section_prefixes`, in document order, the headings left out."""
    in_section = False
    for line in doc.read_text().splitlines():
        if line.startswith("## "):
            in_section = line.removeprefix("## ").startswith(section_prefixes)
        elif in_section:
            yield line


def fenced_blocks(doc: Path, *section_prefixes: str) -> list[list[str]]:
    """Every ``` fence within the `## ` sections whose title starts with one
    of `section_prefixes`, in document order, each as its lines.  A fence
    inside a list item is indented: its lines are read less that indent,
    and it closes at a fence line of the same indent."""
    blocks: list[list[str]] = []
    indent = None                               # the open fence's indent; None outside one
    for line in _section_lines(doc, *section_prefixes):
        if indent is None and line.lstrip(" ").startswith("```"):
            indent = " " * (len(line) - len(line.lstrip(" ")))
            blocks.append([])
        elif indent is not None and line.startswith(indent + "```"):
            indent = None
        elif indent is not None:
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
    category = ""
    for line in _section_lines(doc, section_prefix):
        if line.startswith("### "):
            category = line.removeprefix("### ").strip("`")
            tables[category] = {}
        elif category and line.startswith("| `"):
            cells = _cells(line)
            tables[category][cells[0].strip("`")] = cells[1]
    return tables


def table_rows(doc: Path, *section_prefixes: str) -> list[list[str]]:
    """The cells of every table row opening with a backticked cell, within
    the `## ` sections whose title starts with one of `section_prefixes`."""
    return [_cells(line) for line in _section_lines(doc, *section_prefixes) if line.startswith("| `")]


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip("|").split("|")]


def stated(doc: Path, label: str) -> list[str]:
    """The backticked text of every prose line `<label>: \\`...\\``, in
    document order — TOOL_SCHEMAS.md's `Tool description:` lines."""
    return [line.split("`")[1] for line in doc.read_text().splitlines()
            if line.startswith(f"{label}: `")]
