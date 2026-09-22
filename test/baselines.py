"""Reading approved wording out of the documents (not a pytest module): a
baseline test pins every fenced line of the sections that hold agent-facing
text, so the code and the approved wording cannot drift apart."""

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


def stated(doc: Path, label: str) -> list[str]:
    """The backticked text of every prose line `<label>: \\`...\\``, in
    document order — TOOL_SCHEMAS.md's `Tool description:` lines."""
    return [line.split("`")[1] for line in doc.read_text().splitlines()
            if line.startswith(f"{label}: `")]
