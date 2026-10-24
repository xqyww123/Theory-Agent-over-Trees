"""Render baselines of the `TAT_Error` hierarchy (EXCEPTIONS.md §3).

Every approved rendering is asserted verbatim, and asserted to appear
verbatim in docs/RENDER_BASELINES.md, so the code and the approved wording
cannot drift apart.  Run: python -m pytest test/test_exceptions.py
"""

import pytest

from isabelle_theory_agent.exceptions import (
    AmbiguousId, BadAnswer, BadEdit, BadPlacement, BadSessionNodeParent, BadTheoryNodeParent, ChildRefused,
    ChildrenNotInheritable, ConstructionError,
    ConstructNotSupported, ConstructOwnedByAnother, DuplicateName, DuplicateTheoryShortName,
    HoldsNoChildren, InvalidField, InvalidName, MalformedRawAST, MissingField,
    MoveBesideItself, MoveIntoOwnSubtree, NodeNotFound, NoQuestionPending, ProtectedNode, RawASTError,
    ReservedSessionName, ReservedTheoryName, ResolutionError, TAT_DisasterError, TAT_Error,
    TAT_InternalError,
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
                      available_kinds=["lemma", "theorem", "corollary", "proposition",
                                       "definition", "section", "text",
                                       "theory", "session"]),
          "Unknown kind `lemna`. Available kinds: `lemma`, `theorem`,"
          " `corollary`, `proposition`, `definition`, `section`, `text`, `theory`,"
          " `session`.")

def of_tool(exc):
    """A shape error about a tool call's own arguments, marked the way
    `plugin.check_call` marks it."""
    exc._mark_of_tool()
    return exc


def test_missing_field():
    check(MissingField(holder="lemma", field="statement"),
          "A `lemma` needs the field `statement`.")
    check(of_tool(MissingField(holder="edit", field="evaluate")),
          "The `edit` tool needs the argument `evaluate`.")

def test_invalid_field():
    # The doc holds the shape with a <reason> placeholder, in both forms.
    for placeholder in ("The field `statement` <reason>.", "The argument `constructs` <reason>."):
        assert placeholder in BASELINES
        COVERED.add(placeholder)
    assert (str(InvalidField(field="statement", reason="is not a term"))
            == "The field `statement` is not a term.")
    # A reason ending in a period does not double it.
    assert (str(InvalidField(field="statement", reason="is not a term."))
            == "The field `statement` is not a term.")
    # The schema check's own reasons, for a tool call's arguments.
    check(of_tool(InvalidField("action", "must be one of `append`, `insert_before`,"
                               " `insert_after`, `amend`")),
          "The argument `action` must be one of `append`, `insert_before`, `insert_after`, `amend`.")
    check(of_tool(InvalidField("constructs", "must not be empty")),
          "The argument `constructs` must not be empty.")
    # The tool call's entry point's own refusal, before the check (MODULE_STRUCTURE §4.4).
    check(of_tool(InvalidField("constructs", "must not be nested deeper than 100 levels")),
          "The argument `constructs` must not be nested deeper than 100 levels.")
    # The schema check's own reasons, for a construct's fields.
    check(InvalidField(field="statement", reason="must be an object"),
          "The field `statement` must be an object.")
    check(InvalidField(field="implicit_structure", reason="must be a string or null"),   # a union's null arm
          "The field `implicit_structure` must be a string or null.")
    check(InvalidField(field="types", reason="must not be empty"),
          "The field `types` must not be empty.")
    check(InvalidField(field="types[0].constructors[1].syntax.priority", reason="must be a 64-bit integer"),
          "The field `types[0].constructors[1].syntax.priority` must be a 64-bit integer.")
    check(InvalidField(field="types[0].constructors[1].syntax.form",
                       reason="must be one of `infix`, `infixl`, `infixr`, `binder`, `mixfix`, `NoSyntax`"),
          "The field `types[0].constructors[1].syntax.form` must be one of `infix`, `infixl`, `infixr`,"
          " `binder`, `mixfix`, `NoSyntax`.")


def test_unexpected_field():
    check(UnexpectedField(holder="lemma", field="statment",
                          takes=["name", "statement"],
                          holder_is_top=True),
          "A `lemma` has no field `statment`; it takes `name`, `statement`.")
    check(UnexpectedField(holder="statement.premises[1]", field="nmae", takes=["name", "term"],
                          holder_is_top=False),
          "`statement.premises[1]` has no field `nmae`; it takes `name`, `term`.")
    check(of_tool(UnexpectedField(holder="edit", field="kind",
                                  takes=["action", "target_id", "constructs", "evaluate",
                                         "auto_construct"],
                                  holder_is_top=True)),
          "The `edit` tool has no argument `kind`; it takes `action`, `target_id`,"
          " `constructs`, `evaluate`, `auto_construct`.")
    check(of_tool(UnexpectedField(holder="location", field="where", takes=["position", "node_id"],
                                  holder_is_top=False)),
          "`location` has no argument `where`; it takes `position`, `node_id`.")
    check(UnexpectedField(holder="note", field="children", takes=[], holder_is_top=True),
          "A `note` has no field `children`; it takes no fields.")
    check(of_tool(UnexpectedField(holder="answer", field="verdict", takes=[], holder_is_top=False)),
          "`answer` has no argument `verdict`; it takes no arguments.")

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
    check(InvalidName(name="Foo-Bar", grammar="theory name"),
          "`Foo-Bar` is not a valid theory name: a theory name starts with a"
          " letter and continues with letters, digits and underscores, with"
          " no hyphen and no dot.")
    check(InvalidName(name="S'", grammar="session name"),
          "`S'` is not a valid session name: a session name starts with a"
          " letter and continues with letters, digits, underscores and"
          " interior hyphens, and does not end with a hyphen or an"
          " underscore.")
    # The fact name's, the type name's, the constant name's and the locale name's grammars share one text.
    check(InvalidName("rev-length", "fact name"),
          "`rev-length` is not a valid fact name: a fact name starts with a letter and continues with"
          " letters, digits, underscores and primes ('), and does not end with an underscore.")
    check(InvalidName("my-list", "type name"),
          "`my-list` is not a valid type name: a type name starts with a letter and continues with"
          " letters, digits, underscores and primes ('), and does not end with an underscore.")
    check(InvalidName("dl-rev", "constant name"),
          "`dl-rev` is not a valid constant name: a constant name starts with a letter and continues with"
          " letters, digits, underscores and primes ('), and does not end with an underscore.")
    check(InvalidName("idempotent-semigroup", "locale name"),
          "`idempotent-semigroup` is not a valid locale name: a locale name starts with a letter and continues with"
          " letters, digits, underscores and primes ('), and does not end with an underscore.")

def test_duplicate_theory_short_name():
    check(DuplicateTheoryShortName(short_name="List", holder="HOL.List"),
          "The theory name `List` conflicts with the short name of"
          " `HOL.List`. No two theories can share a short name.")
    check(DuplicateTheoryShortName(short_name="Foo",
                                   holder="constructs[1].children[0]"),
          "The theory name `Foo` is also used by `constructs[1].children[0]`"
          " of this call.")

def test_reserved_theory_name():
    check(ReservedTheoryName(name="FOL"),
          "`FOL` is a reserved theory name; choose another name.")

def test_reserved_session_name():
    check(ReservedSessionName(name="Aux"),
          "`Aux` is a reserved session name; choose another name.")
    check(ReservedSessionName(name="ROOT"),
          "`ROOT` is a reserved session name; choose another name.")

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

def test_bad_placement():
    """`{through}` two kinds, and none."""
    check(BadPlacement(kind="note", parent_id="session_Arith", within="theory", through=["section", "subsection"]),
          "A node of kind `note` cannot be placed under `session_Arith`; it stands inside a node of kind"
          " `theory`, directly or under nodes of kind `section` or `subsection`.")
    check(BadPlacement(kind="top", parent_id="Sessions", within="theory", through=[]),
          "A node of kind `top` cannot be placed under `Sessions`; it stands inside a node of kind"
          " `theory`, directly.")

def test_child_refused():
    """The parent's sentence after a period."""
    check(ChildRefused(kind="lift_definition", parent_id="session_S.theory_T.typedef_fm",
                       reason="For technical reasons, this subtype does not support lifting; you cannot use the transfer"
                              " tactic or lift_definitions on this type."),
          "A node of kind `lift_definition` cannot be placed under `session_S.theory_T.typedef_fm`. For technical"
          " reasons, this subtype does not support lifting; you cannot use the transfer tactic or lift_definitions on"
          " this type.")


def test_move_into_own_subtree():
    check(MoveIntoOwnSubtree(id="theory_X.section_Basics",
                             destination="theory_X.section_Basics.text_a"),
          "`theory_X.section_Basics` cannot move into its own subtree.")

def test_move_beside_itself():
    check(MoveBesideItself(id="theory_X.lemma_P"),
          "`theory_X.lemma_P` is already in that position; a move must name another node.")

def test_protected_node():
    check(ProtectedNode(id="Sessions"),
          "The `Sessions` cannot be edited.")

def test_construct_not_supported():
    check(ConstructNotSupported(id="theory_X.section_Basics"),
          "`theory_X.section_Basics` has nothing to construct.")
    check(ConstructNotSupported(id=None),
          "None of these nodes has anything to construct.")

def test_the_answer_tools_refusals():
    """`NoQuestionPending`'s sentence is the framework's; `ConstructOwnedByAnother`
    carries the job class's `owned_by_another_refusal`; `BadAnswer` the
    question's own sentence (CONSTRUCT_INTERACTION §5)."""
    check(NoQuestionPending(id="theory_X.definition_f"),
          "`theory_X.definition_f` has no question waiting for an answer.")
    check(ConstructOwnedByAnother(id="theory_X.lemma_P",
                                  refusal="The proof construction on `lemma_P` belongs to another agent."),
          "The proof construction on `lemma_P` belongs to another agent.")
    assert str(BadAnswer("A verdict needs a reason.")) == "A verdict needs a reason."


# --- opening lines (RENDER_BASELINES §1) ------------------------------------

OPENINGS = [
    ("append", "theory_X.section_Basics"),
    ("insert_before", "theory_X.lemma_P"),
    ("insert_after", "theory_X.lemma_P"),
    ("amend", "theory_X.lemma_P"),
    ("move", "theory_Sorting before theory_X.lemma_P"),
    ("move", "theory_Sorting after theory_X.section_Basics"),
    ("move", "theory_Sorting into session_Arith"),
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
    exc = MissingField(holder="lemma", field="statement")
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
    exc = MissingField(holder="lemma", field="statement")
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
    assert issubclass(ReservedTheoryName, BadEdit)
    assert issubclass(ReservedSessionName, BadEdit)
    assert issubclass(BadSessionNodeParent, BadEdit)
    assert issubclass(BadTheoryNodeParent, BadEdit)
    assert issubclass(BadPlacement, BadEdit)
    assert issubclass(ChildRefused, BadEdit)
    for cls in (ConstructNotSupported, ConstructOwnedByAnother, NoQuestionPending):
        assert issubclass(cls, ConstructionError)
    for group in (ResolutionError, RawASTError, BadEdit, ConstructionError):
        assert issubclass(group, TAT_Error)
    assert issubclass(BadAnswer, TAT_Error) and not issubclass(BadAnswer, ConstructionError)

def test_group_bases_are_abstract():
    for cls in (TAT_Error, ResolutionError, RawASTError, BadEdit,
                ConstructionError):
        with pytest.raises(TypeError):
            cls()


# --- completeness: runs last, after every check() above ---------------------

def test_every_baseline_is_covered():
    assert BASELINES - COVERED == set()
