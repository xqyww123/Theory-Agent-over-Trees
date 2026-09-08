"""Reading approved wording out of the documents (not a pytest module): a
baseline test pins every fenced line of the sections that hold agent-facing
text, so the code and the approved wording cannot drift apart."""

from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"


def fenced_lines(doc: Path, *section_prefixes: str) -> list[str]:
    """Every non-empty line inside a ``` fence, within the `## ` sections
    whose title starts with one of `section_prefixes`, in document order."""
    lines, in_section, in_fence = [], False, False
    for line in doc.read_text().splitlines():
        if line.startswith("## "):
            in_section = line.removeprefix("## ").startswith(section_prefixes)
        elif in_section and line.startswith("```"):
            in_fence = not in_fence
        elif in_section and in_fence and line:
            lines.append(line)
    return lines
