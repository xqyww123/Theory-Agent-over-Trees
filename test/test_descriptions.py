"""Description baselines of the node classes TAT ships (PLUGIN_SYSTEM §3):
every `description` in a shipped class's construct schema is one fenced
line of the class's document under docs/node_classes/, and every fenced
line of the sections named in DOCUMENTS is a description of the schema —
pinned the way test_exceptions.py pins RENDER_BASELINES.md.  A shipped
class missing from the table below fails the test.
Run: python -m pytest test/test_descriptions.py
"""

from baselines import DOCS, fenced_lines

from isabelle_theory_agent import model as M
from isabelle_theory_agent.model import Session, Theory

# document -> (the sections holding the descriptions, the classes it specifies)
DOCUMENTS = {
    "SESSION_AND_THEORY.md": (("1.", "2."), [Session, Theory]),
}


def descriptions(schema) -> list[str]:
    """Every `description` value under `schema`, in document order."""
    if isinstance(schema, dict):
        own = [schema["description"]] if isinstance(schema.get("description"), str) else []
        return own + [d for v in schema.values() for d in descriptions(v)]
    if isinstance(schema, list):
        return [d for v in schema for d in descriptions(v)]
    return []


def test_every_shipped_class_is_specified():
    specified = [cls for _, classes in DOCUMENTS.values() for cls in classes]
    assert specified == M.FRAMEWORK_NODE_CLASSES


def test_descriptions_are_the_documents_fenced_lines():
    for document, (sections, classes) in DOCUMENTS.items():
        doc = fenced_lines(DOCS / "node_classes" / document, *sections)
        code = [d for cls in classes for d in descriptions(cls.construct_schema)]
        assert sorted(code) == sorted(doc), document
        assert len(set(doc)) == len(doc), document      # each line pins one description
