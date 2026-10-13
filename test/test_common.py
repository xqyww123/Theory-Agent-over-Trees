"""What the classes of `Isabelle_Std` share (node_classes/COMMON.md), with
no Isabelle: `NotInsideTheory`'s sentence, and `Theory_Member` over every
class the package registers (§1).
Run: python -m pytest test/test_common.py
"""

import pytest

import test_session_theory as ts
from baselines import DOCS, fenced_lines
from isabelle_theory_agent import edit, model as M, plugin
from isabelle_theory_agent.exceptions import BadEdit
from isabelle_theory_agent.std import theorem
from isabelle_theory_agent.std.common import NotInsideTheory, Theory_Member
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import lemma

table = ts.table                    # the fake state slot table and the fake wire, per test
COMMON = DOCS / "node_classes" / "COMMON.md"

# One construct per kind the package registers, valid under a theory; held
# to the registered kinds, so a new class adds its example here.
EXAMPLES = {kind: lemma("p", kind=kind) for kind in theorem.KINDS}


def test_not_inside_theory_is_section_1_s_sentence():
    [line] = fenced_lines(COMMON, "1.")
    e = NotInsideTheory("datatype", "session_Arith")
    assert str(e) == line and (e.kind, e.parent_id) == ("datatype", "session_Arith")
    assert issubclass(NotInsideTheory, BadEdit)


def test_every_registered_class_is_a_theory_member_refused_outside_a_theory():
    """§1: every class the package registers derives from `Theory_Member`;
    a construct of each placed under a `Session` or the root is refused by
    its `gen` with `NotInsideTheory`, a move there by `on_moving`, the
    parent's id as the agent sees it; under a nesting node under the
    theory it is accepted, by `gen` and by a move, and directly under
    another theory by a move; `theory()` is, each time, the theory it
    lives in."""
    loaded = plugin.load(["isabelle_theory_agent.std"])
    registered = {kind: cls for kind, cls in loaded.kinds.items() if cls not in M.FRAMEWORK_NODE_CLASSES}
    assert set(registered) == set(EXAMPLES)
    kinds = {**ts.KINDS, **registered}
    f = Forest_Under_Test(kinds=kinds)
    (s,) = run(locked(f, edit.insert(f, 0, [session("Arith", theory("X") | {"children": [
        {"kind": "block", "name": "B", "children": [{"kind": "block", "name": "C"}]}]}, theory("Y"))], kinds)))
    x, y = s.sub_nodes
    (b,) = x.sub_nodes
    (c,) = b.sub_nodes
    outside = ((s, "session_Arith"), (f, "Sessions"))
    for kind, construct in EXAMPLES.items():
        cls = registered[kind]
        assert issubclass(cls, Theory_Member)
        for parent, parent_id in outside:
            with pytest.raises(NotInsideTheory) as e:
                run(locked(f, edit.insert(parent, 0, [construct], kinds)))
            assert (e.value.kind, e.value.parent_id, e.value.raw_ast_path) == (kind, parent_id, "constructs[0]")
        (node,) = run(locked(f, edit.insert(c, 0, [construct], kinds)))
        assert isinstance(node, cls) and node.theory() is x
        run(locked(f, edit.move(node, b, 0)))
        assert node.parent is b and node.theory() is x
        run(locked(f, edit.move(node, y, 0)))
        assert node.parent is y and node.theory() is y
        for parent, parent_id in outside:
            with pytest.raises(NotInsideTheory) as e:
                run(locked(f, edit.move(node, parent, 0)))
            assert (e.value.kind, e.value.parent_id) == (kind, parent_id)
        assert node.parent is y
        run(locked(f, edit.delete(node)))
    assert f.sub_nodes == [s] and s.sub_nodes == [x, y] and x.sub_nodes == [b] and b.sub_nodes == [c]
    assert y.sub_nodes == []
