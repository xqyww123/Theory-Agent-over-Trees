"""What the classes of `Isabelle_Std` share (node_classes/COMMON.md):
`NotInsideTheory`'s sentence, and `Theory_Member` over every class the
package registers (§1); the `text` line (§2); `Proof_Obligation`'s
abstraction, and its reading of the class's own words, callback, message
and records, through a stand-in, and `TAT_Proof_Obligation.decide` on a
raw ML process (§3); the shared `$defs` against the section's schema
text, the type parameters' checks and writer, the function-name pair's
check and writers, a type's head, and the mixfix writers (§4);
`Lifting_Closing`'s two hooks and its place among a class's bases (§6).
The rest of what `Proof_Obligation` does on a node is pinned through
`Theorem`, test_theorem.py, and what `Lifting_Closing` does through
`QuotientType`, test_quotient_type.py; the names' checks (§5) through
`Theorem` and `Datatype`.
Run: python -m pytest test/test_common.py
"""

import jsoncomment
import pytest

import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from isabelle_theory_agent import edit, isabelle_driver, model as M, plugin
from isabelle_theory_agent.exceptions import BadEdit, InvalidField
from isabelle_theory_agent.std import common, datatype, define, lift_definition, quotient_type, theorem, typedef
from isabelle_theory_agent.std.common import (
    Binder, Infix, Lifting_Closing, NotInsideTheory, Proof_Obligation, Template, Theory_Member, Type_Parameter, text_line)
from Isabelle_RPC_Host.unicode import IsaTerm
from ml_process import ROOT, ml_process, ml_string
from test_datatype import LIST, definition
from test_define import SUM_UPTO
from test_lift_definition import DL_REV
from test_model import locked, run
from test_quotient_type import FSET
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import lemma
from test_typedef import DLIST

table = ts.table                    # the fake state slot table and the fake wire, per test
COMMON = DOCS / "node_classes" / "COMMON.md"

# One construct per kind the package registers, valid under a theory; held
# to the registered kinds, so a new class adds its example here.
EXAMPLES = {**{kind: lemma("p", kind=kind) for kind in theorem.KINDS},
            **{kind: definition(LIST, kind=kind) for kind in datatype.KINDS},
            **{kind: SUM_UPTO for kind in define.KINDS},
            **{kind: DLIST for kind in typedef.KINDS},
            **{kind: DL_REV for kind in lift_definition.KINDS},
            **{kind: FSET for kind in quotient_type.KINDS}}


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


def test_the_text_line_is_section_2_s():
    """§2: a period added when `english` ends without `.`, `!` or `?`; the
    class's lead before it; the text through the framework's `cartouche`."""
    assert text_line("The length of a reversed list") == "text ‹The length of a reversed list.›"
    assert [text_line(e) for e in ("Bang!", "Why?", "Done.")] == ["text ‹Bang!›", "text ‹Why?›", "text ‹Done.›"]
    assert text_line("Bang", "Lemma q.") == "text ‹Lemma q. Bang.›"
    assert text_line("‹Quoted› \\<open>here\\<close>") == 'text ‹"Quoted" "here".›'


@pytest.mark.parametrize("shape", ["leaf", "block"])
def test_proof_obligation_enforces_its_abstract_methods(shape):
    """§3: `Proof_Obligation` derives from `Node`, so a class that leaves
    `goal_structure()` or `message()` out fails at its first instantiation,
    on a leaf and on a block whose goal opens on its beginning alike;
    `Theorem` and the block stand-in have both."""
    bases, complete, body = {
        "leaf": ((Proof_Obligation, M.Leaf), theorem.Theorem, {"emit": lambda self, indent, out: indent}),
        "block": ((common.Beginning_Proof_Obligation, tm.Block), Block_Stand_In, {})}[shape]
    without_goal_structure = type("Without_Goal_Structure", (Theory_Member, *bases), {**body, "message": lambda self: ()})
    without_message = type("Without_Message", (Theory_Member, *bases), {**body, "goal_structure": lambda self: ()})
    for cls, missing in ((without_goal_structure, "goal_structure"), (without_message, "message")):
        with pytest.raises(TypeError, match=missing):
            cls(None, None)
    assert issubclass(complete, Proof_Obligation) and complete.__abstractmethods__ == frozenset()


class Stand_In(theorem.Theorem):
    """A second `Proof_Obligation` class, with its own words, callback,
    message and records (§3); the rest `Theorem`'s."""
    evaluation_callback = "TAT.Stand_In.evaluate"
    valid_word, invalid_word = "valid definition", "invalid definition"
    recorded = None                     # what `record_from_evaluation` was given, once called

    def message(self):
        return ("stand_in", self.name)

    def record_from_evaluation(self, what):
        self.recorded = what
        return (IsaTerm.from_agent(f"recorded {what[0]} and {what[1]}"),)


def test_proof_obligation_reads_the_class_s_own_words_callback_message_and_records(monkeypatch):
    """§3: `_eval_opr` calls the class's own `evaluation_callback` with the
    three slots and its `message()`, and reads its answer, the messages and
    what the two steps yielded: the messages make the node an obstacle,
    the class's `record_from_evaluation` not called; none is `Ready`
    carrying what `record_from_evaluation` answers, given the pair; the
    default, `Theorem`'s, records nothing and answers `()`.  The mark's
    first slot is the class's `valid_word` or `invalid_word`."""
    kinds = {**ts.KINDS, "lemma": Stand_In}
    f = Forest_Under_Test(kinds=kinds)
    (s,) = run(locked(f, edit.insert(f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        lemma("p"), lemma("q")]})], kinds)))
    (x,) = s.sub_nodes
    p, q = x.sub_nodes
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        return [["no"], None] if args[3] == q.message() else [[], ["opened", "admitted"]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    run(x.evaluate_to(None, False))
    assert [name for name, _ in calls] == ["TAT.Stand_In.evaluate"] * 2
    assert [args[:3] for _, args in calls] == [
        (n.state.to_msgpack(), n.goal_state.to_msgpack(), n.resulting_state().to_msgpack()) for n in (p, q)]
    assert [args[3] for _, args in calls] == [p.message(), q.message()] == [("stand_in", "p"), ("stand_in", "q")]
    (status,) = p.evaluation_statuses()
    assert isinstance(status, M.Ready) and [m.unicode for m in status.messages] == ["recorded opened and admitted"]
    assert p.recorded == ["opened", "admitted"]
    assert p.mark(M.BRIEFING, 0) == "valid definition, proof not started"
    (status,) = q.evaluation_statuses()
    assert isinstance(status, M.CannotEvaluate) and [m.unicode for m in status.messages] == ["no"]
    assert q.recorded is None
    assert q.mark(M.BRIEFING, 0) == "invalid definition"
    assert "record_from_evaluation" not in vars(theorem.Theorem)
    assert Proof_Obligation.record_from_evaluation(p, [None, None]) == ()


# --- Beginning_Proof_Obligation (§3): the goal on a block's beginning, through a stand-in over test_model's fake block

class Block_Stand_In(Theory_Member, common.Beginning_Proof_Obligation, tm.Block):
    """A `Proof_Obligation` whose goal opens on the beginning of test_model's
    fake block, the shape of `QuotientType` (§3): its own words, callback
    and message; the fake's ending."""
    construct_schema = {**tm.BLOCK_SCHEMA, "properties": {**tm.BLOCK_SCHEMA["properties"], "kind": {"const": "block_stand_in"}}}
    evaluation_callback = "TAT.Block_Stand_In.evaluate"
    valid_word, invalid_word = "valid definition", "invalid definition"

    def __init__(self, parent, state, name):
        super().__init__(parent, state)
        self.name = name

    def goal_structure(self):
        return ("R",)

    def message(self):
        return ("block_stand_in", self.name)


BLOCK_KINDS = {**tm.KINDS, "block_stand_in": Block_Stand_In}


def block_forest(children=1):
    """Theory > [Q > [C1, …]] over the fake block, Q the stand-in."""
    f = tm.OneTreeForest(tm.CONN, kinds=BLOCK_KINDS)
    thy = tm.add(f, tm.Block(f, tm.slot(), "Theory"))
    q = tm.add(thy, Block_Stand_In(thy, tm.slot(), "Q"), "block_stand_in")
    cs = [tm.add(q, tm.T(q, tm.slot(), f"C{i + 1}")) for i in range(children)]
    return f, thy, q, cs


def goal_call(monkeypatch):
    """The fake wire's answer to the stand-in's callback: the goal opened and
    admitted, nothing recorded; every call kept."""
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        _, goal, result, _ = args
        tm.TABLE.values[goal] = "goal"
        tm.TABLE.values[result] = "admitted"
        return [[], [None, None]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    return calls


def test_beginning_proof_obligation_opens_the_goal_on_the_beginning_s_two_slots(monkeypatch):
    """§3: the callback is called with the beginning's input slot,
    `goal_state`, the beginning's resulting slot — the first child's state,
    the slot after all children with no child — and `message()`;
    `_slots_written_by` names `goal_state` for the beginning alone; the
    mark's first slot reads `job_operation_status()`: the valid word on
    `(Ready, NOT_EVALUATED)` and on `(Ready, CannotEvaluate)`, the invalid
    word on `(CannotEvaluate, Ready)`, `not evaluated` before any run.
    `goal_state` lies on the conversation of the node's own `state`."""
    calls = goal_call(monkeypatch)
    f, thy, q, (c1,) = block_forest()
    assert q.goal_state.conversation is q.state.conversation
    assert q.mark(M.BRIEFING, 0) == "not evaluated, proof not started"
    run(q.evaluate_to(None, False))
    [(name, args)] = calls
    assert name == "TAT.Block_Stand_In.evaluate"
    assert args == (q.state.to_msgpack(), q.goal_state.to_msgpack(), c1.state.to_msgpack(), ("block_stand_in", "Q"))
    assert tm.st(q) == (tm.READY, tm.READY)
    assert q._slots_written_by("beginning") == (q.goal_state,) and q._slots_written_by("ending") == ()
    assert q.mark(M.BRIEFING, 0) == "valid definition, proof not started"
    q.evaluation_status_ending = M.NOT_EVALUATED
    assert q.mark(M.BRIEFING, 0) == "valid definition, proof not started"
    q.evaluation_status_ending = M.CannotEvaluate()
    assert q.mark(M.BRIEFING, 0) == "valid definition, proof not started"    # the jobs depend on the beginning alone
    q.evaluation_status_beginning, q.evaluation_status_ending = M.CannotEvaluate(), tm.READY
    assert q.mark(M.BRIEFING, 0) == "invalid definition"
    calls.clear()
    f, thy, q, _ = block_forest(children=0)
    run(q.evaluate_to(None, False))
    [(_, args)] = calls
    assert args[2] == q._state_before_ending.to_msgpack()


def test_the_goal_state_of_a_block_is_held_across_a_child_edit_and_released_with_its_beginning(monkeypatch):
    """§3 "The slot": `goal_state` is released with the beginning's resulting
    slot — an insert before the block —, not with the ending's: a child
    insert leaves it held, `job_operation_status()` `ready`."""
    goal_call(monkeypatch)
    f, thy, q, (c1,) = block_forest()
    run(q.evaluate_to(None, False))
    assert tm.TABLE.values[q.goal_state.name] == "goal"
    run(locked(f, edit.insert(q, 1, [{"kind": "t", "name": "C2"}], BLOCK_KINDS)))
    assert tm.TABLE.values[q.goal_state.name] == "goal" and tm.st(q) == (tm.READY, M.NOT_EVALUATED)
    assert isinstance(q.job_operation_status(), M.Ready)
    run(locked(f, edit.insert(thy, 0, [{"kind": "t", "name": "T0"}], BLOCK_KINDS)))
    assert q.goal_state.name not in tm.TABLE.values and q.goal_state.name in tm.TABLE.deleted
    assert tm.st(q) == (M.NOT_EVALUATED, M.NOT_EVALUATED)


def test_the_loader_refuses_a_bare_proof_obligation_on_a_block_and_beginning_proof_obligation_on_a_leaf(monkeypatch):
    """§3: the loader refuses `Proof_Obligation` bare on a block, `None`
    being no operation of a block, and `Beginning_Proof_Obligation` on a
    leaf (PLUGIN_SYSTEM §5)."""
    monkeypatch.setattr(plugin, "registry", {})

    class Bare(Theory_Member, Proof_Obligation, tm.Block):
        construct_schema = {**tm.BLOCK_SCHEMA, "properties": {**tm.BLOCK_SCHEMA["properties"], "kind": {"const": "bare"}}}
        evaluation_callback = "TAT.Bare.evaluate"
        def goal_structure(self): return ()
        def message(self): return ()

    with pytest.raises(plugin.CannotLoadPlugin, match="`job_operation` is None, not an operation of the class"):
        plugin.TAT_node(Bare)

    class Opening_Lemma(common.Beginning_Proof_Obligation, theorem.Theorem):
        pass

    with pytest.raises(plugin.CannotLoadPlugin, match="`job_operation` is 'beginning', not an operation of the class"):
        plugin.TAT_node(Opening_Lemma)


def test_a_proof_obligation_takes_its_goal_s_hook_from_the_class_that_sets_its_job_operation():
    """§3: the class that sets a registered `Proof_Obligation` class's
    `job_operation` is `Proof_Obligation` or `Beginning_Proof_Obligation`,
    and each evaluation hook that class defines reaches the registered
    class from it — `Theorem` and `Typedef`, the registered ones, and the
    block stand-in; a subclass overriding the hook fails the rule."""
    def takes_its_hook_from_the_class_that_sets_its_job_operation(cls):
        setter = plugin._defined_by(cls, "job_operation")
        return setter in (Proof_Obligation, common.Beginning_Proof_Obligation) and all(
            plugin._defined_by(cls, hook) is setter
            for hook in ("_eval_opr", "_eval_beginning_opr", "_eval_ending_opr") if hook in vars(setter))
    loaded = plugin.load(["isabelle_theory_agent.std"])
    obligations = {cls for cls in loaded.kinds.values() if issubclass(cls, Proof_Obligation)}
    assert obligations == {theorem.Theorem, typedef.Typedef, lift_definition.LiftDefinition, quotient_type.QuotientType}
    assert all(takes_its_hook_from_the_class_that_sets_its_job_operation(cls) for cls in obligations)
    assert takes_its_hook_from_the_class_that_sets_its_job_operation(Block_Stand_In)

    class Overriding(Block_Stand_In):
        async def _eval_beginning_opr(self): return M.READY_CLEAN   # type: ignore[override]

    assert not takes_its_hook_from_the_class_that_sets_its_job_operation(Overriding)


# --- Lifting_Closing (§6): the ending's two hooks together, its place among a class's bases

def test_lifting_closing_defines_the_ending_s_two_hooks_and_comes_after_the_class_that_sets_job_operation():
    """§6; PLUGIN_SYSTEM §5: `Lifting_Closing` defines `_eval_ending_opr` and
    `emit_ending` together, and a class on it writes neither —
    `QuotientType`, which lists it after `Beginning_Proof_Obligation`;
    listed before it, `StdBlock`'s abstract `_eval_beginning_opr` comes
    first and the class cannot be instantiated."""
    assert {"_eval_ending_opr", "emit_ending"} <= set(vars(Lifting_Closing)) and "_eval_beginning_opr" not in vars(Lifting_Closing)
    assert not {"_eval_ending_opr", "emit_ending"} & set(vars(quotient_type.QuotientType))
    assert quotient_type.QuotientType.__mro__.index(common.Beginning_Proof_Obligation) < quotient_type.QuotientType.__mro__.index(Lifting_Closing)
    assert quotient_type.QuotientType.__abstractmethods__ == frozenset()
    body = {k: v for k, v in vars(quotient_type.QuotientType).items() if k not in ("__dict__", "__weakref__")}
    right = type("Right", (Theory_Member, common.Beginning_Proof_Obligation, Lifting_Closing), body)
    wrong = type("Wrong", (Theory_Member, Lifting_Closing, common.Beginning_Proof_Obligation), body)
    assert right.__abstractmethods__ == frozenset() and wrong.__abstractmethods__ == frozenset({"_eval_beginning_opr"})
    with pytest.raises(TypeError, match="_eval_beginning_opr"):
        wrong()


# --- the shared `$defs` (§4): the schema text, the type parameters' check and writer, the mixfix writers

def test_the_shared_defs_are_section_4_s_schema_text():
    """§4: the three definitions, descriptions included, are the section's
    jsonc blocks, pinned here alone; `Datatype`'s `$defs` are the three."""
    blocks = [jsoncomment.JsonComment().loads("\n".join(b)) for b in fenced_blocks(COMMON, "4.") if b[0] == "{"]
    assert blocks == [common.TYPE_PARAMETER_DEFS, common.MIXFIX_DEFS, common.TYPE_MIXFIX_DEFS]


def test_the_type_parameters_check_renders_section_4_s_two_sentences():
    """§4: a name that is not a prime and an Isabelle identifier on its
    `ascii`, and a name bound twice, each the section's sentence; the
    pieces normalised, an empty `sort` no sort."""
    [variable, binds] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field")][0]
    with pytest.raises(InvalidField) as e:
        common.type_parameters_of([{"name": "a"}])
    assert str(e.value) == variable and e.value.field == "type_parameters[0].name"
    with pytest.raises(InvalidField) as e:
        common.type_parameters_of([{"name": "'a"}, {"name": "'a", "sort": "linorder"}])
    assert str(e.value) == binds and e.value.field == "type_parameters[1].name"
    for bad in ("", "'", "'1", "''a", "'a b", "a'", "'a-b"):
        with pytest.raises(InvalidField) as e:
            common.type_parameters_of([{"name": "'b"}, {"name": bad}])
        assert e.value.field == "type_parameters[1].name" and e.value.reason.startswith("must be a type variable"), bad
    parameters = common.type_parameters_of([{"name": " 'a "}, {"name": "'b", "sort": ""},
                                            {"name": "'c", "sort": " {zero,\n linorder} "}, {"name": "'x⇩1"}])
    assert parameters == (Type_Parameter(IsaTerm.from_agent("'a"), None), Type_Parameter(IsaTerm.from_agent("'b"), None),
                          Type_Parameter(IsaTerm.from_agent("'c"), IsaTerm.from_agent("{zero, linorder}")),
                          Type_Parameter(IsaTerm.from_agent("'x⇩1"), None))
    assert [p.image() for p in parameters] == [{"name": "'a"}, {"name": "'b"}, {"name": "'c", "sort": "{zero, linorder}"},
                                               {"name": "'x⇩1"}]


def test_the_unused_type_parameter_check_renders_section_4_s_sentence():
    """§4: a declared parameter whose name occurs as a type-variable token
    in none of the texts — `'a`, not within `'ab`, `'a1`, `'a'`, `'a⇩1` or
    `x'a` — is refused on its path with the section's sentence, the first
    such parameter; a letter symbol is a letter."""
    [sentence] = [line for line in fenced_lines(COMMON, "4.") if line.endswith("which is not used.")]
    of = common.type_parameters_of

    def texts(*ts):
        return [IsaTerm.from_agent(t) for t in ts]
    with pytest.raises(InvalidField) as e:
        common.check_type_parameters_used(of([{"name": "'a"}, {"name": "'b"}]), texts("'a list", "nat"))
    assert str(e.value) == sentence and e.value.field == "type_parameters[1]"
    with pytest.raises(InvalidField) as e:
        common.check_type_parameters_used(of([{"name": "'a"}, {"name": "'b"}]), texts("nat"))
    assert e.value.field == "type_parameters[0]"
    for text in ("'ab", "'a1", "'a'", "'a⇩1", "x'a", "'A", ""):
        with pytest.raises(InvalidField) as e:
            common.check_type_parameters_used(of([{"name": "'a"}]), texts(text))
        assert e.value.field == "type_parameters[0]", text
    for text in ("'a", "'a list", "nat ⇒ 'a", "'a⇒'b", "('a, 'b) t", "'b ⇒ 'a⇩1 ⇒ 'a", "{x :: 'a. x = x}"):
        common.check_type_parameters_used(of([{"name": "'a"}]), texts(text))
    common.check_type_parameters_used(of([{"name": "'α", "sort": "linorder"}, {"name": "'x⇩1"}]), texts("'α ⇒ 'x⇩1"))
    with pytest.raises(InvalidField):
        common.check_type_parameters_used(of([{"name": "'α"}]), texts("'αb"))
    common.check_type_parameters_used(of([]), texts())
    common.check_type_parameters_used(of([]), texts("'a"))          # an undeclared variable is Isabelle's to refuse


def test_type_variables_of_renders_section_4_s_two_sentences_under_its_own_path():
    """§4: the same check over type variables written bare, under
    `type_parameters[i]`, answering `Type_Parameter`s without a sort, the
    names normalised; the stored names read back through it."""
    [variable, binds] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field")][0]
    with pytest.raises(InvalidField) as e:
        common.type_variables_of(["a"])
    assert str(e.value) == variable.replace("type_parameters[0].name", "type_parameters[0]") and e.value.field == "type_parameters[0]"
    with pytest.raises(InvalidField) as e:
        common.type_variables_of(["'a", "'a"])
    assert str(e.value) == binds.replace("type_parameters[1].name", "type_parameters[1]") and e.value.field == "type_parameters[1]"
    for bad in ("", "'", "'1", "''a", "'a b", "a'", "'a-b"):
        with pytest.raises(InvalidField) as e:
            common.type_variables_of(["'b", bad])
        assert e.value.field == "type_parameters[1]" and e.value.reason.startswith("must be a type variable"), bad
    parameters = common.type_variables_of([" 'a ", "'b", "'x⇩1"])
    assert parameters == (Type_Parameter(IsaTerm.from_agent("'a"), None), Type_Parameter(IsaTerm.from_agent("'b"), None),
                          Type_Parameter(IsaTerm.from_agent("'x⇩1"), None))
    assert common.type_variables_of([p.name.unicode for p in parameters]) == parameters and common.type_variables_of([]) == ()


def test_the_function_name_pair_s_check_renders_section_4_s_two_sentences_and_its_writers_fill_the_defaults():
    """§4: each given name an identifier Isabelle reads in a term, the two
    given names, as given, not the same — the later refused —, a name
    equal to its default or beginning like one a given name like any
    other; `function_names` fills a name left out with its prefix before
    the type's name; `morphisms_clause` writes the two through
    `print_name` against the keywords, None when neither was given."""
    [identifier, twice] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field `rep_function_name`")][0]
    of = common.function_names_of
    with pytest.raises(InvalidField) as e:
        of("rep_", "abs_fset")
    assert str(e.value) == identifier and e.value.field == "rep_function_name"
    with pytest.raises(InvalidField) as e:
        of("list_of_fset", "abs_")
    assert str(e.value) == identifier.replace("rep_function_name", "abs_function_name") and e.value.field == "abs_function_name"
    with pytest.raises(InvalidField) as e:
        of("list_of_fset", " list_of_fset ")
    assert str(e.value) == twice and e.value.field == "abs_function_name"
    for bad in ("1x", "x y", "", "rep-", "h\\<nat>", "x_"):
        with pytest.raises(InvalidField) as e:
            of(bad, None)
        assert e.value.field == "rep_function_name", bad
    assert of(None, None) == (None, None)
    rep, abs_ = of(" list_of_fset", "Abs_fset")
    assert (rep, abs_) == (IsaTerm.from_agent("list_of_fset"), IsaTerm.from_agent("Abs_fset"))
    assert of("rep_fset", "abs_fset") == (IsaTerm.from_agent("rep_fset"), IsaTerm.from_agent("abs_fset"))
    prefixes = ("rep_", "abs_")
    assert common.function_names(None, None, "fset", prefixes) == (IsaTerm.from_agent("rep_fset"), IsaTerm.from_agent("abs_fset"))
    assert common.function_names(rep, None, "fset", prefixes) == (rep, IsaTerm.from_agent("abs_fset"))
    assert common.function_names(None, abs_, "fset", ("Rep_", "Abs_")) == (IsaTerm.from_agent("Rep_fset"), abs_)
    assert common.morphisms_clause(None, None, "fset", prefixes, ()) is None
    assert common.morphisms_clause(rep, None, "fset", prefixes, ()) == "morphisms list_of_fset abs_fset"
    assert common.morphisms_clause(None, abs_, "fset", prefixes, frozenset({"rep_fset"})) == 'morphisms "rep_fset" Abs_fset'
    assert common.morphisms_clause(IsaTerm.from_agent("ρ"), abs_, "fset", prefixes, ()) == "morphisms ρ Abs_fset"


def test_type_head_text_writes_section_4_s_examples():
    """§4: the parameters by `type_parameters_text`, the name through
    `print_name` against the keywords, the syntax by `mixfix_text` when
    given."""
    of, head = common.type_variables_of, common.type_head_text
    assert head(of(["'a"]), "fset", None, ()) == "'a fset"
    assert head(of(["'a", "'b"]), "t", common.mixfix_of({"form": "infixr", "symbol": "+", "priority": 10}), ()) == "('a, 'b) t (infixr \"+\" 10)"
    assert head((), "int", None, ()) == "int"
    assert head((), "term", None, frozenset({"term"})) == '"term"'
    assert head(common.type_parameters_of([{"name": "'a", "sort": "zero"}]), "z", None, frozenset({"zero"})) == "('a :: \"zero\") z"
    assert head(of(["'a"]), "fract", common.mixfix_of({"form": "mixfix", "template": "_ ratio", "argument_priorities": [21], "priority": 21}), ()) == "'a fract (\"_ ratio\" [21] 21)"


def test_type_parameters_text_writes_section_4_s_examples():
    """§4: nothing for none, one without a sort bare, otherwise parenthesised
    and comma-separated with a sort after `::` through `print_name` against
    the keyword set given — a keyword quoted, none against no set — in
    `unicode`."""
    of, text = common.type_parameters_of, common.type_parameters_text
    assert text(of([])) == ""
    assert text(of([{"name": "'a"}])) == "'a"
    assert text(of([{"name": "'a", "sort": "linorder"}])) == "('a :: linorder)"
    assert text(of([{"name": "'a", "sort": "linorder"}, {"name": "'b"}])) == "('a :: linorder, 'b)"
    assert text(of([{"name": "'a", "sort": "{zero, linorder}"}])) == "('a :: \"{zero, linorder}\")"
    assert text(of([{"name": "'a"}, {"name": "'b"}])) == "('a, 'b)"
    greek = of([{"name": "'α", "sort": "linorder"}, {"name": "'b"}])
    assert text(greek) == "('α :: linorder, 'b)"
    assert text(greek, frozenset({"linorder"})) == "('α :: \"linorder\", 'b)"
    assert text(of([{"name": "'a", "sort": "linorder"}]), frozenset({"'a"})) == "('a :: linorder)"    # a variable never quoted


def test_mixfix_text_and_mixfix_wire_write_section_4_s_examples():
    """§4: either annotation as Isabelle writes it, in `unicode`, the symbol
    or template a string token, a template's priorities each when given;
    on the wire the same text in `ascii`, None for none; the image the
    construct's shape, read back to the same annotation."""
    of = common.mixfix_of
    cases = [
        ({"form": "infixr", "symbol": "#", "priority": 65}, Infix, '(infixr "#" 65)', '(infixr "#" 65)'),
        ({"form": "infix", "symbol": "+", "priority": 0}, Infix, '(infix "+" 0)', '(infix "+" 0)'),
        ({"form": "infixl", "symbol": "\"", "priority": 1}, Infix, '(infixl "\\"" 1)', '(infixl "\\"" 1)'),
        ({"form": "binder", "symbol": "∀", "priority": 10}, Binder, '(binder "∀" 10)', '(binder "\\<forall>" 10)'),
        ({"form": "mixfix", "template": "⟨_, _⟩"}, Template, '("⟨_, _⟩")', '("\\<langle>_, _\\<rangle>")'),
        ({"form": "mixfix", "template": "_ ! _", "argument_priorities": [100, 101], "priority": 100}, Template,
         '("_ ! _" [100, 101] 100)', '("_ ! _" [100, 101] 100)'),
        ({"form": "mixfix", "template": "_⇩⊥", "argument_priorities": [21]}, Template, '("_⇩⊥" [21])',
         '("_\\<^sub>\\<bottom>" [21])'),
        ({"form": "mixfix", "template": "_!", "priority": 999}, Template, '("_!" 999)', '("_!" 999)'),
        ({"form": "mixfix", "template": "_", "argument_priorities": []}, Template, '("_" [])', '("_" [])'),
        ({"form": "mixfix", "template": "_", "argument_priorities": [0], "priority": 0}, Template, '("_" [0] 0)', '("_" [0] 0)'),
    ]
    for raw, arm, unicode, ascii in cases:
        syntax = of(raw)
        assert isinstance(syntax, arm) and syntax.image() == raw and of(syntax.image()) == syntax, raw
        assert (common.mixfix_text(syntax), common.mixfix_wire(syntax)) == (unicode, ascii), raw
    assert common.mixfix_wire(None) is None
    # the symbol or template normalised for newlines and tabs alone: runs of spaces are layout
    assert of({"form": "mixfix", "template": "⟨_,\n\t_⟩  "}) == Template(IsaTerm.from_agent("⟨_,  _⟩  "))
    assert of({"form": "infix", "symbol": "a\r\nb", "priority": 1}) == Infix("infix", IsaTerm.from_agent("a b"), 1)


# --- TAT_Proof_Obligation.decide (§3), on a raw ML process of the heap the plugin runs on, the theory `Probe` begun on
#     the heap's top theory — the structure's file names AoA's structures —, the framework's ML from source

DECIDE_ML = [str(ROOT / "ML" / "TAT_Framework.ML"), str(ROOT / "ML" / "TAT_Common_Nodes.ML"),
             str(ROOT / "Isabelle_Std" / "ML" / "TAT_Proof_Obligation.ML")]

DECIDE_CASES = r"""
  datatype answer = datatype TAT_Framework.answer;
  val thy0 = Context.the_theory (Context.the_generic_context ());
  fun state name = Toplevel.make_state (SOME (Theory.begin_theory (name, Position.none) [thy0]));
  val (st_0, st_T, st_F) = (state "Input", state "T", state "F");
  fun same (st, st') = Context.eq_thy (Toplevel.theory_of st, Toplevel.theory_of st');
  val runs = Unsynchronized.ref ([] : bool list);
  fun command refuse b st =
    (runs := b :: !runs;
     if not (same (st, st_0)) then Refused ["not the input state"]
     else if refuse b then Refused ["refused"] else Accepted (if b then st_T else st_F));
  fun show (Accepted (st, b)) =
        "Accepted " ^ (if same (st, st_T) then "T" else if same (st, st_F) then "F" else "0") ^ " " ^ Value.print_bool b
    | show (Refused msgs) = "Refused " ^ commas msgs;
  fun case_ label recorded refuse needed =
    (runs := [];
     writeln (label ^ ": " ^ show (TAT_Proof_Obligation.decide {recorded = recorded, command = command refuse, needed = needed} st_0)
       ^ " runs=" ^ commas (map Value.print_bool (rev (! runs)))));
  val _ = case_ "1" (SOME true) (K false) (K (Refused ["needed asked"]));
  val _ = case_ "2" (SOME false) (K false) (K (Refused ["needed asked"]));
  val _ = case_ "3" (SOME true) (K true) (K (Refused ["needed asked"]));
  val _ = case_ "4" NONE (K false) (fn st => Accepted (same (st, st_T)));
  val _ = case_ "5" NONE (K false) (K (Accepted false));
  val _ = case_ "6" NONE (K false) (K (Refused ["needed"]));
  val _ = case_ "7" NONE (K true) (K (Accepted true));
  val _ = case_ "8" NONE not (K (Accepted false));
  val _ = writeln "DECIDE DONE";
"""


async def test_tat_proof_obligation_decide_runs_a_recorded_value_once_and_probes_under_none(std_harness, tmp_path):
    """§3: `decide` with a counting `command`, which accepts the input state
    alone, and a stub `needed`: `SOME b` runs the command once with `b`,
    yielding its state and `b`, `needed` never asked, a refused run the
    refusal after that one run; `NONE` runs `true` on the input state as
    a probe, asks `needed` of the probe's state, then runs the option so
    decided on the input state, yielding that run's state — the probe's
    is not the result — and the option; `needed` refused, or either run
    refused, is the refusal with no run after.  On the heap the plugin
    runs on, the framework's ML and the structure's file evaluated from
    source inside the context of a theory on the heap's top theory, where
    AoA's structures the file names are visible."""
    cases = tmp_path / "decide_cases.ML"
    cases.write_text(DECIDE_CASES)
    files = ", ".join(ml_string(f) for f in [*DECIDE_ML, str(cases)])
    r = await ml_process(std_harness, f"val _ = in_theory thy0 [{files}];",
                         logic="Minilang_AoA", base="Minilang_AoA.Minilang_AoA")
    lines = r.stdout.splitlines()
    assert r.returncode == 0 and "DECIDE DONE" in lines, (r.stdout[-3000:], r.stderr[-3000:])
    assert [line for line in lines if line[:1] in "12345678" and line[1:3] == ": "] == [
        "1: Accepted T true runs=true", "2: Accepted F false runs=false", "3: Refused refused runs=true",
        "4: Accepted T true runs=true, true", "5: Accepted F false runs=true, false", "6: Refused needed runs=true",
        "7: Refused refused runs=true", "8: Refused refused runs=true, false"], lines


# --- the three words of a class that defines (§3), through the stand-in

class Defining_Stand_In(Stand_In):
    """`Stand_In` as a class that defines: its third word."""
    unverified_word = "unverified definition"


class Owing_Nothing_Stand_In(Defining_Stand_In):
    """A class that defines with nothing to prove, as a `Define` with no open
    obligation: `owes_proof()` false."""
    def owes_proof(self):
        return False


def test_proof_mark_reads_the_three_words_of_a_class_that_defines():
    """§3: with `unverified_word`, the line is the valid word alone once the
    proof stands or when the node owes none, the unverified word with the
    proof's word before, `proven` never; without it, `Theorem`'s table;
    `proven`, `unverified` and `proof_mark` read the node alone — its
    words and its `owes_proof()` —, the one computation
    `With_Proof_Obligations.mark` is; `owing_line()` is `Node`'s `None` on
    a class that gives none."""
    from isabelle_theory_agent.jobs import NOT_STARTED, PASSED
    from test_theorem import BAD, PROVED, with_proof
    kinds = {**ts.KINDS, "lemma": Defining_Stand_In, "plain": Stand_In, "free": Owing_Nothing_Stand_In}
    f = Forest_Under_Test(kinds=kinds)
    (s,) = run(locked(f, edit.insert(f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        lemma("p"), lemma("q", kind="plain"), lemma("r", kind="free")]})], kinds)))
    (x,) = s.sub_nodes
    p, q, r = x.sub_nodes
    assert p.mark(M.BRIEFING, 0) == "not evaluated, proof not started" and not common.unverified(p)
    for n in (p, q, r):
        with_proof(n, M.READY_CLEAN, NOT_STARTED)
    assert p.mark(M.BRIEFING, 0) == "unverified definition, proof not started" and common.unverified(p)
    assert r.mark(M.BRIEFING, 0) == "valid definition" and not common.unverified(r)        # owes nothing
    assert q.mark(M.BRIEFING, 0) == "valid definition, proof not started"                  # no third word
    assert common.proof_mark(p) == p.mark(M.BRIEFING, 0) and common.proof_mark(q) == q.mark(M.BRIEFING, 0)
    for n in (p, q):
        with_proof(n, M.READY_CLEAN, PROVED, PASSED)
    assert p.mark(M.BRIEFING, 0) == "valid definition" and common.proven(p) and not common.unverified(p)
    assert q.mark(M.BRIEFING, 0) == "valid definition, proven"
    with_proof(p, M.READY_CLEAN, PROVED, BAD)
    assert p.mark(M.BRIEFING, 0) == "unverified definition, bad proof" and not common.proven(p)
    with_proof(p, M.NOT_EVALUATED, PROVED, BAD)
    assert p.mark(M.BRIEFING, 0) == "not evaluated" and not common.unverified(p)
    assert p.owing_line() is None
    assert Proof_Obligation.unverified_word is None and theorem.Theorem.unverified_word is None
    assert typedef.Typedef.unverified_word == "unverified definition"
    assert common.With_Proof_Obligations.owes_proof(p) and Proof_Obligation.owes_proof(p)      # the default: always
