"""What the classes of `Isabelle_Std` share (node_classes/COMMON.md):
the placement check's answers over every class the package registers,
against §1's table (PLUGIN_SYSTEM §2); the `text` line (§2); `Proof_Obligation`'s
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

import io
import re
import jsoncomment
import pytest

import test_model as tm
import test_session_theory as ts
from baselines import DOCS, composed_refusal, fenced_blocks, fenced_lines, table_rows
from isabelle_theory_agent import edit, isabelle_driver, model as M, plugin
from isabelle_theory_agent.exceptions import GRAMMARS, InvalidField
from isabelle_theory_agent.std import (
    common, datatype, define, lift_definition, lifting_context, quotient_type, record, theorem, typedef)
from isabelle_theory_agent.std.common import (
    Binder, Infix, Lifting_Block, Lifting_Closing, Proof_Obligation, Template, Type_Definition, Type_Parameter,
    english_cartouche, lifting_closing_text,
    text_line)
from Isabelle_RPC_Host.unicode import IsaTerm
from ml_process import ROOT, ml_process, ml_string
from test_datatype import LIST, definition
from test_define import SUM_UPTO
from test_lift_definition import DL_REV
from test_lifting_context import FSET_SIZE
from test_model import locked, run
from test_quotient_type import FSET
from test_record import POINT
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import lemma
from test_typedef import DLIST

table = ts.table                    # the fake state slot table and the fake wire, per test
COMMON = DOCS / "node_classes" / "COMMON.md"

# One construct per kind the package registers, valid under a theory; held
# to the registered kinds, so a new class adds its example here.
EXAMPLES = {**{kind: lemma("p", kind=kind) for kind in theorem.KINDS},
            **{kind: definition(LIST, kind=kind) for kind in datatype.KINDS},
            **{kind: POINT for kind in record.KINDS},
            **{kind: SUM_UPTO for kind in define.KINDS},
            **{kind: DLIST for kind in typedef.KINDS},
            **{kind: DL_REV for kind in lift_definition.KINDS},
            **{kind: FSET_SIZE for kind in lifting_context.KINDS},
            **{kind: FSET for kind in quotient_type.KINDS}}


def section_1_table():
    """§1's table, read from the document: a class's name → the names of the
    classes its row's second cell lists, a base's name (`StdBlock`) standing
    for that class and every class deriving from it."""
    declared = {}
    for classes, under in table_rows(COMMON, "1."):
        names = tuple(n.strip("` ") for n in under.split(","))
        declared |= {name.strip("` "): names for name in classes.split(",")}
    return declared


def test_the_placement_check_answers_section_1_s_table():
    """§1: every class the package registers is in the table; for the theory
    and every chain of one or two registered nesting classes the table
    admits, each class's example is built under the chain's last node and
    `_refusal()` asked: None exactly where the table admits the class under
    every node of the chain, otherwise the head naming the outermost node
    whose cell is no, by its full id, then that cell's remedy — `Move it
    out.`, §1's fence, for a type definition under a lifting block; a
    heading under a chain holding a heading is the level rule's
    (test_section_text.py).  A `Typedef` block whose `lifting` is false
    refuses every class, at any depth: a type definition with `Move it
    out.`, every other with §6's sentence.  The headers: the four type
    definitions are `Type_Definition`, the three lifting blocks
    `Lifting_Block`."""
    loaded = plugin.load(["isabelle_theory_agent.std"])
    registered = {kind: cls for kind, cls in loaded.kinds.items() if cls not in M.FRAMEWORK_NODE_CLASSES}
    assert set(registered) == set(EXAMPLES)
    declared = section_1_table()
    by_name = {cls.__name__: cls for cls in registered.values()}
    assert set(by_name) <= set(declared)
    classes = {**by_name, "StdBlock": M.StdBlock}                          # the loaded classes a cell may name
    heading = classes.get("Section")
    [move_it_out] = fenced_lines(COMMON, "1.")
    [lifting_refusal] = fenced_blocks(COMMON, "6.")[0]
    assert move_it_out == common.MOVE_IT_OUT and lifting_refusal == common.LIFTING_REFUSAL
    assert {c for c in by_name.values() if issubclass(c, Type_Definition)} == {datatype.Datatype, typedef.Typedef, record.Record, quotient_type.QuotientType}
    assert {c for c in by_name.values() if issubclass(c, Lifting_Block)} == {typedef.Typedef, quotient_type.QuotientType, lifting_context.LiftingContext}

    def admits(container_cls, cls):
        return any(issubclass(container_cls, classes[name]) for name in declared[cls.__name__] if name in classes)

    def remedy(container_cls, cls):
        if issubclass(container_cls, Lifting_Block) and issubclass(cls, Type_Definition):
            return move_it_out
        raise AssertionError(f"no remedy known for a {cls.__name__} under a {container_cls.__name__}")

    def expected(chain, kind):
        for container in chain:                                           # outermost first
            if not admits(type(container), registered[kind]):
                return composed_refusal(kind, f.full_id(container), remedy(type(container), registered[kind]))
        return None

    nesting = {cls: kind for kind, cls in reversed(registered.items()) if issubclass(cls, M.NonLeaf_Node)}   # one kind per class
    childless = {kind: {k: v for k, v in construct.items() if k != "children"} for kind, construct in EXAMPLES.items()}
    f = Forest_Under_Test(kinds={**ts.KINDS, **registered})
    (s,) = run(locked(f, edit.insert(f, 0, [session("Arith", theory("X"))])))
    (x,) = s.sub_nodes
    pairs = [(k1, k2) for k1 in nesting.values() for k2 in nesting.values() if admits(registered[k1], registered[k2])]
    for kinds in [(), *((k,) for k in nesting.values()), *pairs]:
        nodes, last = [], x
        for kind in kinds:
            (last,) = run(locked(f, edit.insert(last, 0, [childless[kind]])))
            nodes.append(last)
        for kind, construct in childless.items():
            if heading and issubclass(registered[kind], heading) and any(isinstance(n, heading) for n in nodes):
                continue                                                  # the level rule's (test_section_text.py)
            (node,) = run(locked(f, edit.insert(last, 0, [construct])))
            assert node._refusal() == expected(nodes, kind), (kinds, kind)
            run(locked(f, edit.delete(node)))
        if nodes:
            run(locked(f, edit.delete(nodes[0])))
    # a `Typedef` block whose `lifting` is recorded false, and a lifting context inside it
    (fm,) = run(locked(f, edit.insert(x, 0, [childless["typedef"]])))
    fm.lifting = False
    assert fm.refuses_children() is True

    def every_class_refused_under(parent):
        for kind, construct in childless.items():
            (node,) = run(locked(f, edit.insert(parent, 0, [construct])))
            told = move_it_out if issubclass(registered[kind], Type_Definition) else lifting_refusal
            assert node._refusal() == composed_refusal(kind, f.full_id(fm), told), (parent, kind)
            run(locked(f, edit.delete(node)))
    every_class_refused_under(fm)
    (ctx,) = run(locked(f, edit.insert(fm, 0, [childless["lifting_context"]])))        # at depth 2, through a lifting context
    assert ctx._refusal() == composed_refusal("lifting_context", f.full_id(fm), lifting_refusal)
    every_class_refused_under(ctx)
    assert x.sub_nodes == [fm] and fm.sub_nodes == [ctx]


def test_the_text_line_is_section_2_s():
    """§2: a period added when `english` ends without `.`, `!` or `?`; the
    class's lead before it; the text through the framework's `cartouche`."""
    assert text_line("The length of a reversed list") == "text ‹The length of a reversed list.›"
    assert [text_line(e) for e in ("Bang!", "Why?", "Done.")] == ["text ‹Bang!›", "text ‹Why?›", "text ‹Done.›"]
    assert text_line("Bang", "Lemma q.") == "text ‹Lemma q. Bang.›"
    assert text_line("‹Quoted› \\<open>here\\<close>") == 'text ‹"Quoted" "here".›'
    assert english_cartouche("Bang", "Lemma q.") == "‹Lemma q. Bang.›"     # the text alone: an axiom's comment


@pytest.mark.parametrize("shape", ["leaf", "block"])
def test_proof_obligation_enforces_its_abstract_methods(shape):
    """§3: `Proof_Obligation` derives from `Node`, so a class that leaves
    `goal_structure()` or `message()` out fails at its first instantiation,
    on a leaf and on a block whose goal opens on its beginning alike;
    `Theorem` and the block stand-in have both."""
    bases, complete, body = {
        "leaf": ((Proof_Obligation, M.Leaf), theorem.Theorem, {"emit": lambda self, indent, out: indent}),
        "block": ((common.Beginning_Proof_Obligation, tm.Block), Block_Stand_In, {})}[shape]
    without_goal_structure = type("Without_Goal_Structure", bases, {**body, "message": lambda self: ()})
    without_message = type("Without_Message", bases, {**body, "goal_structure": lambda self: ()})
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
        lemma("p"), lemma("q")]})])))
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

class Block_Stand_In(common.Beginning_Proof_Obligation, tm.Block):
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
    run(locked(f, edit.insert(q, 1, [{"kind": "t", "name": "C2"}])))
    assert tm.TABLE.values[q.goal_state.name] == "goal" and tm.st(q) == (tm.READY, M.NOT_EVALUATED)
    assert isinstance(q.job_operation_status(), M.Ready)
    run(locked(f, edit.insert(thy, 0, [{"kind": "t", "name": "T0"}])))
    assert q.goal_state.name not in tm.TABLE.values and q.goal_state.name in tm.TABLE.deleted
    assert tm.st(q) == (M.NOT_EVALUATED, M.NOT_EVALUATED)


def test_the_loader_refuses_a_bare_proof_obligation_on_a_block_and_beginning_proof_obligation_on_a_leaf(monkeypatch):
    """§3: the loader refuses `Proof_Obligation` bare on a block, `None`
    being no operation of a block, and `Beginning_Proof_Obligation` on a
    leaf (PLUGIN_SYSTEM §5)."""
    monkeypatch.setattr(plugin, "registry", {})

    class Bare(Proof_Obligation, tm.Block):
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
    right = type("Right", (common.Beginning_Proof_Obligation, Lifting_Closing), body)
    wrong = type("Wrong", (Lifting_Closing, common.Beginning_Proof_Obligation), body)
    assert right.__abstractmethods__ == frozenset() and wrong.__abstractmethods__ == frozenset({"_eval_beginning_opr"})
    with pytest.raises(TypeError, match="_eval_beginning_opr"):
        wrong()


def test_lifting_closing_text_writes_section_6_s_two_lines_and_the_ending_writes_through_it(monkeypatch):
    """§6: the two commands, `lifting_update` then `lifting_forget`, each
    on its own line, the bundle's name bare; `Lifting_Closing.emit_ending`
    writes one empty line and that text at the block's indent, through
    the one writer — `LiftingContext`'s ending shares it (LIFTING_CONTEXT.md
    §5) — so a stand-in for the writer changes what the ending writes."""
    assert lifting_closing_text("fset") == "lifting_update fset.lifting\nlifting_forget fset.lifting"
    assert lifting_closing_text("term") == "lifting_update term.lifting\nlifting_forget term.lifting"
    kinds = {**ts.KINDS, "quotient_type": quotient_type.QuotientType,
             **{kind: lift_definition.LiftDefinition for kind in lift_definition.KINDS}}
    f = Forest_Under_Test(kinds=kinds)
    (s,) = run(locked(f, edit.insert(f, 0, [session("Arith", theory("X") | {"children": [FSET]})])))
    (p,) = s.sub_nodes[0].sub_nodes
    out = io.StringIO()
    assert p.emit_ending(1, out) == 1 and out.getvalue() == "\n  lifting_update fset.lifting\n  lifting_forget fset.lifting\n"
    monkeypatch.setattr(common, "lifting_closing_text", lambda name: f"closing {name}")
    out = io.StringIO()
    p.emit_ending(0, out)
    assert out.getvalue() == "\nclosing fset\n"


# --- the shared `$defs` (§4): the schema text, the type parameters' check and writer, the mixfix writers

def test_the_shared_defs_are_section_4_s_schema_text():
    """§4: the five definitions, descriptions included, are the section's
    jsonc blocks, pinned here alone; `Datatype`'s `$defs` are the first
    three."""
    blocks = [jsoncomment.JsonComment().loads("\n".join(b)) for b in fenced_blocks(COMMON, "4.") if b[0] == "{"]
    assert blocks == [common.TYPE_PARAMETER_DEFS, common.MIXFIX_DEFS, common.TYPE_MIXFIX_DEFS,
                      common.LOCALE_INSTANCE_DEFS, common.VARIABLE_WITH_SYNTAX_DEFS]


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
    for text in ("'ab", "'a1", "'a'", "'a⇩1", "x'a", "'A", "",
                 "nat ― ‹'a›", "nat ― ‹of ‹'a››", "\\<^cancel>‹'a› nat"):       # inside a cartouche: no part of the type
        with pytest.raises(InvalidField) as e:
            common.check_type_parameters_used(of([{"name": "'a"}]), texts(text))
        assert e.value.field == "type_parameters[0]", text
    with pytest.raises(InvalidField) as e:
        common.check_type_parameters_used(of([{"name": "'a"}, {"name": "'b"}]), texts("'a ― ‹of 'b›"))
    assert e.value.field == "type_parameters[1]"
    for text in ("'a ― ‹a comment› list", "‹x› ⇒ 'a", "‹‹x›› 'a"):         # outside a cartouche, before or after one
        common.check_type_parameters_used(of([{"name": "'a"}]), texts(text))
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
        lemma("p"), lemma("q", kind="plain"), lemma("r", kind="free")]})])))
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


# --- `Lifting_Closing`'s two sentences and its hook (§6)

def test_lifting_closing_s_sentences_are_section_6_s_and_a_base_whose_setup_is_not_made_refuses_children():
    """§6: the refusal sentence, the `children` description and the children
    header, the one home of each, verbatim §6's three blocks, the
    description taken by both classes' schemas, the header `Lifting_Block`'s
    (PRINT.md §2); on the base `is_lifting_setup_made()` is true, so
    `refuses_children()` is false, `cannot_hold` admits a lemma and refuses
    a type definition with §1's remedy, and the ending's two hooks do their
    work — `close` called, the two lines written —; a class on it answering
    false refuses children, `cannot_hold` answering the sentence for a
    lemma and §1's remedy first for a type definition, its ending the copy
    and nothing written, `StdBlock`'s defaults."""
    [refusal, description, header] = fenced_blocks(COMMON, "6.")
    assert [common.LIFTING_REFUSAL] == refusal and [common.LIFTING_CHILDREN_DESCRIPTION] == description
    assert header == [common.LIFTING_CHILDREN_HEADER + ":"]
    for schema in (typedef.Typedef.construct_schema, quotient_type.QuotientType.construct_schema):
        assert schema is not None and schema["properties"]["children"]["description"] == common.LIFTING_CHILDREN_DESCRIPTION
    assert Lifting_Block.children_header(None) == common.LIFTING_CHILDREN_HEADER      # type: ignore[arg-type]  # reads no self
    for cls in (typedef.Typedef, quotient_type.QuotientType, lifting_context.LiftingContext):
        assert cls.children_header is Lifting_Block.children_header                 # one home: no class answers it again

    class Unmade(quotient_type.QuotientType):           # a block on the base whose beginning made no setup
        def is_lifting_setup_made(self):
            return False
    loaded = plugin.load(["isabelle_theory_agent.std"])
    kinds = {**ts.KINDS, **{k: c for k, c in loaded.kinds.items() if c not in M.FRAMEWORK_NODE_CLASSES}, "unmade": Unmade}
    f = Forest_Under_Test(kinds=kinds)
    (s,) = run(locked(f, edit.insert(f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        FSET, {**FSET, "kind": "unmade", "type_name": "gset", "children": []}, lemma("p"), definition(LIST)]})])))
    (x,) = s.sub_nodes
    made, unmade, p, lst = x.sub_nodes
    assert made.is_lifting_setup_made() is True and made.refuses_children() is False
    assert made.cannot_hold(p, 1) is None and made.cannot_hold(lst, 2) == common.MOVE_IT_OUT
    assert unmade.is_lifting_setup_made() is False and unmade.refuses_children() is True
    assert unmade.cannot_hold(p, 1) == common.LIFTING_REFUSAL and unmade.cannot_hold(lst, 1) == common.MOVE_IT_OUT
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        return [] if name == "TAT.Lifting_Closing.close" else [[], [None, None]]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(isabelle_driver, "call", call)
        assert run(made._eval_ending_opr()) == M.READY_CLEAN and run(unmade._eval_ending_opr()) == M.READY_CLEAN
    assert [args[2] for name, args in calls if name == "TAT.Lifting_Closing.close"] == ["fset"]
    assert ("copy", unmade._state_before_ending.name, unmade.resulting_state().name) in tm.TABLE.calls
    out = io.StringIO()
    assert made.emit_ending(1, out) == 1 and out.getvalue() == "\n  lifting_update fset.lifting\n  lifting_forget fset.lifting\n"
    out = io.StringIO()
    assert unmade.emit_ending(1, out) == 1 and out.getvalue() == ""


# --- `dotted_name_of`, `Locale_Instance` and `Variable_With_Syntax` (§4)

def test_dotted_name_of_renders_section_4_s_sentence_under_both_nouns():
    """§4: one sentence, the noun what the name names, the grammar text the
    framework's; each part an identifier not ending with an underscore;
    normalised; a repeat the shared sentence."""
    [locale_sentence, type_sentence] = [b for b in fenced_blocks(COMMON, "4.")
                                        if b[0].startswith("The field `imports[0].locale`")][0]
    assert locale_sentence.endswith(GRAMMARS["fact name"] + ".")
    for text in ("fset", "FSet.fset", "ε", "a.b.c"):
        assert common.dotted_name_of(text, "f", (), "type") == IsaTerm.from_agent(text)
    assert common.dotted_name_of(" fset\n", "f", (), "type") == IsaTerm.from_agent("fset")
    with pytest.raises(InvalidField) as e:
        common.dotted_name_of("semi-group", "imports[0].locale", (), "locale")
    assert str(e.value) == locale_sentence
    for text in ("fset_", "", "1st", "x y", "a..b", ".fset", "fset.", "FSet.fset_", "h\\<nat>", "fset-set", "'a"):
        with pytest.raises(InvalidField) as e:
            common.dotted_name_of(text, "types[0]", (), "type")
        assert str(e.value) == type_sentence, text
    with pytest.raises(InvalidField) as e:
        common.dotted_name_of("fset", "types[1]", (IsaTerm.from_agent("fset"),), "type")
    assert str(e.value) == "The field `types[1]` repeats `fset`."


def test_locale_instance_s_reader_renders_section_4_s_sentences_and_its_writer_writes_its_examples():
    """§4: the locale's name by `dotted_name_of`, the qualifier an
    identifier, each instantiation's name one not ending with an
    underscore, no two the same, under the class's path; the writer's
    four examples; the image and the wire."""
    [locale_sentence, _] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field `imports[0].locale`")][0]
    [qualifier, name] = [b for b in fenced_blocks(COMMON, "4.") if b[0].startswith("The field `imports[0].qualifier`")][0]
    of = common.locale_instance_of
    s = of({"locale": "semigroup", "qualifier": "S", "instantiations": [{"name": "f", "term": "f"}]}, "imports[0]")
    assert s == common.Locale_Instance(IsaTerm.from_agent("semigroup"), IsaTerm.from_agent("S"),
                                       (common.Instantiation(IsaTerm.from_agent("f"), IsaTerm.from_agent("f")),))
    assert common.locale_instance_text(s) == "S: semigroup where f = f"
    p = of({"locale": "padic_integers", "instantiations": [{"name": "Zp", "term": "_"}, {"name": "p", "term": " p\n"}]},
           "imports[1]")
    assert p.qualifier is None and common.locale_instance_text(p) == "padic_integers where Zp = _ and p = p"
    assert common.locale_instance_text(of({"locale": "Group.monoid", "instantiations": []}, "imports[0]")) == "Group.monoid"
    k = of({"locale": "A", "qualifier": "is", "instantiations": [{"name": "open", "term": "m"}]}, "imports[0]")
    assert common.locale_instance_text(k, {"is", "open", "m", "A"}) == '"is": "A" where "open" = "m"'
    assert common.locale_instance_text(k, {"is", "open"}) == '"is": A where "open" = m'
    assert common.locale_instance_text(k) == "is: A where open = m"
    dotted = of({"locale": "Group.monoid", "instantiations": [{"name": "G", "term": "G"}]}, "imports[0]")
    assert common.locale_instance_text(dotted, {"Group.monoid", "monoid"}) == "Group.monoid where G = G"   # one token
    for instance in (s, p, k):
        assert common.Locale_Instance.of_image(instance.image()) == instance
    assert s.image() == {"locale": "semigroup", "qualifier": "S", "instantiations": [{"name": "f", "term": "f"}]}
    assert p.image() == {"locale": "padic_integers", "instantiations": [{"name": "Zp", "term": "_"}, {"name": "p", "term": "p"}]}
    assert s.wire() == ("semigroup", "S", [("f", "f")]) and p.wire() == ("padic_integers", None, [("Zp", "_"), ("p", "p")])
    with pytest.raises(InvalidField) as e:
        of({"locale": "semi-group", "instantiations": []}, "imports[0]")
    assert str(e.value) == locale_sentence
    with pytest.raises(InvalidField) as e:
        of({"locale": "s", "qualifier": "1S", "instantiations": []}, "imports[0]")
    assert str(e.value) == qualifier
    assert of({"locale": "s", "qualifier": "S_", "instantiations": []}, "imports[0]").qualifier == IsaTerm.from_agent("S_")
    with pytest.raises(InvalidField) as e:
        of({"locale": "s", "instantiations": [{"name": "f", "term": "f"}, {"name": "g_", "term": "g"}]}, "imports[0]")
    assert str(e.value) == name
    with pytest.raises(InvalidField) as e:
        of({"locale": "s", "instantiations": [{"name": "f", "term": "f"}, {"name": "f", "term": "g"}]}, "imports[2]")
    assert str(e.value) == "The field `imports[2].instantiations[1].name` repeats `f`."


def test_variable_with_syntax_holds_the_three_annotations_and_fixes_text_writes_section_4_s_example():
    """§4: a `Mixfix`, `NoSyntax` for the authored arm, None for `syntax`
    left out; the image keeps `{"form": "NoSyntax"}` and has no key for
    none; the wire sends None for both; `fixes_text` with `print_name`;
    `mixfix_of` reads the arm `NoSyntax` as none."""
    V = common.Variable_With_Syntax
    f = V.of_image({"name": "f", "type": "'a ⇒ 'a ⇒ 'a", "syntax": {"form": "infixl", "symbol": "⊗", "priority": 70}})
    assert f == V(IsaTerm.from_agent("f"), IsaTerm.from_agent("'a ⇒ 'a ⇒ 'a"), Infix("infixl", IsaTerm.from_agent("⊗"), 70))
    g = V.of_image({"name": "g", "type": "", "syntax": {"form": "NoSyntax"}})
    assert g == V(IsaTerm.from_agent("g"), None, common.NoSyntax())
    h = V.of_image({"name": " h\n"})
    assert h == V(IsaTerm.from_agent("h"), None, None)
    for v in (f, g, h):
        assert V.of_image(v.image()) == v
    assert g.image() == {"name": "g", "syntax": {"form": "NoSyntax"}} and h.image() == {"name": "h"}
    assert f.wire() == ("f", "'a \\<Rightarrow> 'a \\<Rightarrow> 'a", '(infixl "\\<otimes>" 70)')
    assert g.wire() == ("g", None, None) and h.wire() == ("h", None, None)
    assert common.fixes_text([f, g, h], lambda t: M.print_name(t, ())) == 'f :: "\'a ⇒ \'a ⇒ \'a" (infixl "⊗" 70) and g and h'
    assert common.fixes_text([f], IsaTerm.to_unicode) == 'f :: \'a ⇒ \'a ⇒ \'a (infixl "⊗" 70)'
    assert common.fixes_text([h], lambda t: M.print_name(t, {"h"})) == '"h"' and common.fixes_text([], str) == ""
    assert common.mixfix_of({"form": "NoSyntax"}) is None
    for defs, name in ((common.MIXFIX_DEFS, "Mixfix"), (common.TYPE_MIXFIX_DEFS, "TypeMixfix")):
        assert defs[name]["anyOf"][-1]["properties"]["form"]["enum"] == ["NoSyntax"]       # the shared last arm


# --- TAT_Mixfix.arm_of (§4), on a raw ML process of the heap the plugin runs on: the structure's file from source

ARM_FORMS = [                                       # every form of `MIXFIX_DEFS`, priorities given and not, `NoSyntax` too
    {"form": "infixr", "symbol": "#", "priority": 65}, {"form": "infix", "symbol": "+", "priority": 0},
    {"form": "infixl", "symbol": "⊗", "priority": 70}, {"form": "binder", "symbol": "∀", "priority": 10},
    {"form": "mixfix", "template": "⟨_, _⟩"},
    {"form": "mixfix", "template": "_ ! _", "argument_priorities": [100, 101], "priority": 100},
    {"form": "mixfix", "template": "_⇩⊥", "argument_priorities": [21]}, {"form": "mixfix", "template": "_!", "priority": 999},
    {"form": "mixfix", "template": "_", "argument_priorities": [0], "priority": 0}, {"form": "NoSyntax"}]
ARM_NONE = ['(binder "\\<forall>" [5] 10)', "(structure)"]           # the forms `MIXFIX_DEFS` leaves out: none

ARM_CASES = r"""
  val ctxt = Proof_Context.init_global (Context.the_theory (Context.the_generic_context ()));
  fun show NONE = "NONE"
    | show (SOME (form, text, ps, p)) =
        form ^ " " ^ quote text ^ " " ^ (case ps of NONE => "-" | SOME ps => "[" ^ commas (map string_of_int ps) ^ "]")
        ^ " " ^ (case p of NONE => "-" | SOME p => string_of_int p);
  fun arm (i, text) = writeln ("ARM " ^ string_of_int i ^ ": " ^ show (TAT_Mixfix.arm_of (TAT_Mixfix.read ctxt text)));
  val _ = List.app arm [%s];
  val _ = writeln "ARM DONE";
"""


async def test_tat_mixfix_arm_of_is_the_converse_of_read_for_every_form(std_harness, tmp_path):
    """§4: for every form of `MIXFIX_DEFS`, `arm_of` of the annotation
    `read` gives for `mixfix_wire`'s text — none for `NoSyntax`, `NoSyn` —
    is the arm itself, read back by `mixfix_of_wire` — so `mixfix_wire` of
    that arm is the text `read` took, and `read` of it the same annotation
    —; a structure and a binder with a body priority of its own are none."""
    arms = [common.mixfix_of(raw) for raw in ARM_FORMS]
    texts = [common.mixfix_wire(a) for a in arms]

    def option(text):
        return "NONE" if text is None else f"SOME {ml_string(text)}"
    listed = ", ".join(f"({i}, {option(t)})" for i, t in enumerate([*texts, *ARM_NONE]))
    cases = tmp_path / "arm_cases.ML"
    cases.write_text(ARM_CASES % listed)
    files = ", ".join(ml_string(f) for f in [str(ROOT / "Isabelle_Std" / "ML" / "TAT_Mixfix.ML"), str(cases)])
    r = await ml_process(std_harness, f"val _ = in_theory thy0 [{files}];",
                         logic="Minilang_AoA", base="Minilang_AoA.Minilang_AoA")
    lines = r.stdout.splitlines()
    assert r.returncode == 0 and "ARM DONE" in lines, (r.stdout[-3000:], r.stderr[-3000:])
    shown = {int(m[1]): m[2] for m in (re.fullmatch(r"ARM (\d+): (.*)", line) for line in lines) if m}
    pattern = re.compile(r'(\S+) "(.*)" (-|\[[^\]]*\]) (-|\d+)')
    for i, (raw, arm) in enumerate(zip(ARM_FORMS, arms)):
        if shown[i] == "NONE":
            wire = None
        else:
            m = pattern.fullmatch(shown[i])
            assert m is not None, shown[i]
            form, text, ps, p = m.groups()
            wire = (form, text, None if ps == "-" else [int(n) for n in ps[1:-1].split(",") if n.strip()],
                    None if p == "-" else int(p))
        assert common.mixfix_of_wire(wire) == arm, (raw, shown[i])
    assert [shown[len(arms) + i] for i in range(len(ARM_NONE))] == ["NONE", "NONE"]
