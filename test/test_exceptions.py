"""Render baselines of the `TAT_Error` hierarchy (EXCEPTIONS.md §3).

Every approved rendering is asserted verbatim, and asserted to appear
verbatim in docs/RENDER_BASELINES.md, so the code and the approved wording
cannot drift apart.  Run: python -m pytest test/test_exceptions.py
"""

import pytest

from isabelle_theory_agent.exceptions import (
    AmbiguousId, BadEdit, BadSessionNodeParent, BadTheoryNodeParent,
    ChildrenNotInheritable, ConstructFailed,
    ConstructNotSupported, DuplicateName, DuplicateTheoryShortName,
    HoldsNoChildren, InvalidField, InvalidName, MalformedRawAST, MissingField,
    MoveIntoOwnSubtree, NodeNotFound, ProtectedNode, RawASTError,
    ResolutionError, TAT_DisasterError, TAT_Error, TAT_InternalError,
    TAT_IsabelleError, TAT_StartupError, UnexpectedChildren, UnexpectedField,
    UnknownKind)

from baselines import DOCS, fenced_lines

# §3 is evaluation text, not exception renderings; the forest walk's test
# pins its Python-side line (the plan's §7, step 4).
BASELINES = set(fenced_lines(DOCS / "RENDER_BASELINES.md", "1.", "2."))
COVERED = set()


def check(exc, expected):
    """`expected` must be one complete fenced line of RENDER_BASELINES §1–§2;
    `test_every_baseline_is_covered` closes the other direction."""
    assert str(exc) == expected
    assert expected in BASELINES
    COVERED.add(expected)


# --- cause lines (RENDER_BASELINES §2) --------------------------------------

def test_node_not_found():
    check(NodeNotFound(id="lemma_fo", near_matches=["lemma_foo", "lemma_fold"]),
          "`lemma_fo` is not found. Did you mean `lemma_foo` or `lemma_fold`?")
    assert (str(NodeNotFound(id="x", near_matches=["a", "b", "c"]))
            == "`x` is not found. Did you mean `a`, `b` or `c`?")
    assert (str(NodeNotFound(id="x", near_matches=["a"]))
            == "`x` is not found. Did you mean `a`?")
    # No near matches: the doc documents only the first sentence of its line.
    short = str(NodeNotFound(id="lemma_fo", near_matches=[]))
    assert short == "`lemma_fo` is not found."
    assert any(line.startswith(short + " ") for line in BASELINES)

def test_ambiguous_id():
    check(AmbiguousId(id="lemma_P",
                      candidates=["theory_X.lemma_P", "theory_Y.lemma_P"]),
          "The id `lemma_P` matches more than one node: `theory_X.lemma_P`,"
          " `theory_Y.lemma_P`. Choose the one you meant.")

def test_malformed_raw_ast():
    check(MalformedRawAST(missing_kind=False),
          "Expected a construct object.")
    check(MalformedRawAST(missing_kind=True),
          "The field `kind` is missing.")

def test_unknown_kind():
    check(UnknownKind(kind="lemna",
                      available_kinds=["lemma", "theorem", "corollary",
                                       "definition", "section", "text",
                                       "theory", "session"]),
          "Unknown kind `lemna`. Available kinds: `lemma`, `theorem`,"
          " `corollary`, `definition`, `section`, `text`, `theory`,"
          " `session`.")

def test_missing_field():
    check(MissingField(kind="lemma", field="statement"),
          "A `lemma` needs the field `statement`.")

def test_invalid_field():
    # The doc holds the shape with a <reason> placeholder.
    placeholder = "The field `statement` <reason>."
    assert placeholder in BASELINES
    COVERED.add(placeholder)
    assert (str(InvalidField(field="statement", reason="is not a term"))
            == "The field `statement` is not a term.")
    # A reason ending in a period does not double it.
    assert (str(InvalidField(field="statement", reason="is not a term."))
            == "The field `statement` is not a term.")
    # The schema check's own reason form.
    check(InvalidField(field="statement", reason="must be a string"),
          "The field `statement` must be a string.")


def test_unexpected_field():
    check(UnexpectedField(holder="lemma", field="statment",
                          takes=["statement", "name", "facts"],
                          holder_is_kind=True),
          "A `lemma` has no field `statment`; it takes `statement`, `name`,"
          " `facts`.")
    check(UnexpectedField(holder="facts[1]", field="nmae", takes=["name"],
                          holder_is_kind=False),
          "`facts[1]` has no field `nmae`; it takes `name`.")

def test_duplicate_name():
    check(DuplicateName(id_component="lemma_assoc",
                        taken_by="theory_Sorting.lemma_assoc"),
          "The id component `lemma_assoc` is already taken by"
          " `theory_Sorting.lemma_assoc`. Amend that node, or give this one"
          " another name.")
    check(DuplicateName(id_component="lemma_assoc", taken_by="constructs[0]"),
          "The id component `lemma_assoc` is already used by `constructs[0]`"
          " of this call.")
    # A nested collision coordinate takes the batch rendering too.
    assert (str(DuplicateName(id_component="t_x", taken_by="children[2]"))
            == "The id component `t_x` is already used by `children[2]` of this call.")

def test_invalid_name():
    check(InvalidName(name="Ch 2"),
          "`Ch 2` is not a valid name: a name starts with a letter and"
          " continues with letters, digits, underscores, primes (') and"
          " interior hyphens, and does not end with a hyphen or an"
          " underscore.")
    check(InvalidName(name="Foo-Bar", theory_name=True),
          "`Foo-Bar` is not a valid theory name: a theory name starts with a"
          " letter and continues with letters, digits, underscores and"
          " primes ('), with no hyphen and no dot.")

def test_duplicate_theory_short_name():
    check(DuplicateTheoryShortName(short_name="List", holder="HOL.List"),
          "The theory name `List` conflicts with the short name of"
          " `HOL.List`. No two theories can share a short name.")
    check(DuplicateTheoryShortName(short_name="Foo",
                                   holder="constructs[1].children[0]"),
          "The theory name `Foo` is also used by `constructs[1].children[0]`"
          " of this call.")

def test_holds_no_children():
    check(HoldsNoChildren(id="theory_X.lemma_P", kind="lemma"),
          "`theory_X.lemma_P` is a `lemma`, and it cannot hold children.")

def test_unexpected_children():
    check(UnexpectedChildren(kind="section", is_leaf=False),
          "When amending a non-leaf node, `children` is not allowed: the"
          " amended node inherits its existing children. To change the"
          " children, use `delete` to remove them and `append` or"
          " `insert_before` to add new ones.")
    check(UnexpectedChildren(kind="lemma", is_leaf=True),
          "`children` is not allowed: a `lemma` holds no children.")

def test_children_not_inheritable():
    check(ChildrenNotInheritable(old_id="theory_X.section_Basics",
                                 new_kind="lemma", children_count=3),
          "`theory_X.section_Basics` has 3 children, which a `lemma` cannot"
          " hold. Move or delete them first.")
    check(ChildrenNotInheritable(old_id="theory_X.section_Basics",
                                 new_kind="lemma", children_count=1),
          "`theory_X.section_Basics` has 1 child, which a `lemma` cannot"
          " hold. Move or delete it first.")

def test_bad_node_parent():
    check(BadSessionNodeParent(kind="session", parent_id="theory_X"),
          "A `session` cannot be placed under `theory_X`; a session lives"
          " directly under `Sessions`.")
    check(BadTheoryNodeParent(kind="theory", parent_id="section_Basics"),
          "A `theory` cannot be placed under `section_Basics`; a theory lives"
          " directly under a session.")

def test_move_into_own_subtree():
    check(MoveIntoOwnSubtree(id="theory_X.section_Basics",
                             destination="theory_X.section_Basics.text_a"),
          "`theory_X.section_Basics` cannot move into its own subtree.")

def test_protected_node():
    check(ProtectedNode(id="Sessions"),
          "The `Sessions` cannot be edited.")

def test_construct_not_supported():
    check(ConstructNotSupported(id="theory_X.text_intro"),
          "`theory_X.text_intro` does not support construct.")


# --- opening lines (RENDER_BASELINES §1) ------------------------------------

OPENINGS = [
    ("append", "theory_X.section_Basics"),
    ("insert_before", "theory_X.lemma_P"),
    ("insert_after", "theory_X.lemma_P"),
    ("amend", "theory_X.lemma_P"),
    ("move", "theory_Sorting to before theory_X.lemma_P"),
    ("move", "theory_Sorting to after theory_X.section_Basics"),
    ("move", "theory_Sorting to session_Arith"),
    ("delete", "theory_X.section_Basics"),
]

@pytest.mark.parametrize("opr,target", OPENINGS)
def test_opening_line(opr, target):
    exc = ProtectedNode(id="Sessions")
    exc._set_operation(opr, target)
    opening, cause = str(exc).split("\n")
    assert opening == f"Cannot {opr} {target}"
    assert opening in BASELINES
    COVERED.add(opening)
    assert cause == "The `Sessions` cannot be edited."


def test_set_operation_refuses_misuse():
    exc = ProtectedNode(id="Sessions")
    with pytest.raises(TAT_InternalError):
        exc._set_operation("frobnicate", "x")        # not an operation name
    exc._set_operation("delete", "theory_X")
    with pytest.raises(TAT_InternalError):
        exc._set_operation("delete", "theory_X")     # written once only


# --- the raw_ast_path field (EXCEPTIONS.md §5) ------------------------------

def test_raw_ast_path_accumulates_upward():
    exc = MissingField(kind="lemma", field="statement")
    try:
        try:
            raise exc                          # the raise site knows no path
        except TAT_Error as e:
            e._prefix_raw_ast_path("children[0]")
            raise                              # the same object re-raised
    except MissingField as e:                  # an outer except still catches
        e._prefix_raw_ast_path("constructs[2]")
        assert e is exc
    assert exc.raw_ast_path == "constructs[2].children[0]"
    check(exc,
          "At `constructs[2].children[0]`: A `lemma` needs the field"
          " `statement`.")

def test_opening_line_above_prefixed_cause():
    exc = MissingField(kind="lemma", field="statement")
    exc._prefix_raw_ast_path("constructs[2]")
    exc._set_operation("append", "theory_X.section_Basics")
    assert (str(exc) ==
            "Cannot append theory_X.section_Basics\n"
            "At `constructs[2]`: A `lemma` needs the field `statement`.")


# --- the hierarchy's shape (EXCEPTIONS.md §1, §3) ---------------------------

def test_the_four_kinds_are_disjoint():
    kinds = (TAT_Error, TAT_InternalError, TAT_StartupError, TAT_DisasterError)
    for kind in kinds:
        assert not issubclass(kind, tuple(k for k in kinds if k is not kind))
    # an exception escaping an ML callback is a bug (EXCEPTIONS.md §1)
    assert issubclass(TAT_IsabelleError, TAT_InternalError)
    assert not issubclass(TAT_IsabelleError, TAT_Error)

def test_groups():
    assert issubclass(NodeNotFound, ResolutionError)
    assert issubclass(MalformedRawAST, RawASTError)
    assert issubclass(DuplicateTheoryShortName, BadEdit)
    assert issubclass(BadSessionNodeParent, BadEdit)
    assert issubclass(BadTheoryNodeParent, BadEdit)
    assert issubclass(ConstructNotSupported, ConstructFailed)
    for group in (ResolutionError, RawASTError, BadEdit, ConstructFailed):
        assert issubclass(group, TAT_Error)

def test_group_bases_are_abstract():
    for cls in (TAT_Error, ResolutionError, RawASTError, BadEdit,
                ConstructFailed):
        with pytest.raises(TypeError):
            cls()


# --- completeness: runs last, after every check() above ---------------------

# Bad<Class>NodeParent renderings belong to the node classes
# (EXCEPTIONS.md §3); this list is the checklist that fails loudly when
# those classes land.
EXEMPT = {
    "A `lemma` cannot be placed under `session_Arith`; it belongs inside a"
    " theory.",
}

def test_every_baseline_is_covered():
    assert BASELINES - COVERED == EXEMPT
