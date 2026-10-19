"""`LiftingContext` (node_classes/LIFTING_CONTEXT.md): with no Isabelle, the
schema and the descriptions (§2, §3), `gen`'s checks and refusals (§4),
the fields as the node holds, stores and prints them (§1, §2, §8), the
node's name and the framework's `DuplicateName` on it, the beginning's
call and the recorded `opened`, the ending's call (§6), the emitted text
(§5), the id properties (§9); through the std harness, the setups opened
and closed for real with the block's transfer rules stored by the ending
(§6), `recall` (§8), the rendered file (§5), and the refusals (§6, §8).
Run: python -m pytest test/test_lifting_context.py
"""

import io
import json

import jsoncomment
import pytest

import stand_ins
import test_ids
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import text_of
from invariants import assert_store_mirrors
from Isabelle_RPC_Host.unicode import IsaTerm
from isabelle_theory_agent import compile as C, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import GRAMMARS, DuplicateName, InvalidField, InvalidName, RawASTError
from isabelle_theory_agent.jobs import NOT_STARTED, PASSED, Succeeded
from isabelle_theory_agent.std import lifting_context
from isabelle_theory_agent.std.common import Lifting_Closing, NotInsideTheory, Theory_Member
from isabelle_theory_agent.std.lift_definition import LiftDefinition
from isabelle_theory_agent.std.lifting_context import LiftingContext
from isabelle_theory_agent.store import Forest_Store
from ml_process import read_back
from std_forest import KINDS, assert_a_missing_row_is_refused_at_start, forest, insert, inv, refused
from test_descriptions import descriptions
from test_lift_definition import definition as lift
from test_model import locked, run
from test_quotient_type import FEMPTY, definition as quotient
from test_session_theory import Forest_Under_Test, session, theory
from test_theorem import PROVED, lemma, with_proof

table = ts.table                    # the fake state slot table and the fake wire, per test
LC = DOCS / "node_classes" / "LIFTING_CONTEXT.md"

FSET_SIZE, INT_SWAP = (json.loads("\n".join(block)) for block in fenced_blocks(LC, "2.")[:2])     # §2's two constructs
FCARD, FCARD_FEMPTY = FSET_SIZE["children"]
(INT_SWAP_DEFINITION,) = INT_SWAP["children"]
[SENTENCE] = fenced_blocks(LC, "6.")[0]           # §6's one sentence, for `nat`
ROWS = ("name", "types", "opened")                # §1's rows


def block(name="fset_size", types=("fset",), **fields):
    """A construct of `lifting_context`: §2's first example's name and
    types by default, no child."""
    return {"kind": "lifting_context", "name": name, "types": list(types), **fields}


def sentence(name: str) -> str:
    """§6's sentence for `name`."""
    return SENTENCE.replace("nat", name)


# --- the schema and the descriptions (§2, §3) ------------------------------

def test_the_schema_and_the_descriptions_are_the_documents():
    [_, _, schema] = fenced_blocks(LC, "2.")
    assert LiftingContext.construct_schema == jsoncomment.JsonComment().loads("\n".join(schema))
    assert list(lifting_context.KINDS) == ["lifting_context"]
    assert sorted(descriptions(LiftingContext.construct_schema)) == sorted(fenced_lines(LC, "3."))
    assert FSET_SIZE == block(children=[FCARD, FCARD_FEMPTY])
    assert INT_SWAP == block("int_swap", ("int",), children=[INT_SWAP_DEFINITION])
    assert FCARD == lift("fcard", "'a fset ⇒ nat", "λxs. card (set xs)", "The number of elements of a finite set")
    assert FCARD_FEMPTY == {"kind": "lemma", "name": "fcard_fempty",
                            "statement": {"english": "The empty finite set has no element", "conclusion": "fcard fempty = 0"}}
    assert issubclass(LiftingContext, Theory_Member) and issubclass(LiftingContext, M.StdBlock)
    assert not issubclass(LiftingContext, Lifting_Closing)
    assert LiftingContext.construction_job_class is None and LiftingContext.evaluation_job_class is None     # no jobs
    assert {"_eval_beginning_opr", "_eval_ending_opr", "emit_beginning", "emit_ending"} <= set(vars(LiftingContext))
    assert "mark" not in vars(LiftingContext)                                                   # the framework's (§7)
    assert "english" not in (LiftingContext.construct_schema or {})["properties"]                 # no `text` line (§1)


# --- `gen` (§2, §4) ----------------------------------------------------------

def test_gen_keeps_the_fields_normalised_as_isaterms_and_names_the_node():
    f, x = forest(block("fset_size", (" fset\n", "FSet.fset ", "ε"), children=[FCARD, FCARD_FEMPTY]))
    (p,) = x.sub_nodes
    assert isinstance(p, LiftingContext) and p.kind == "lifting_context" and p.name == "fset_size"
    assert f.id_of(p) == "lifting_context_fset_size"
    assert p.types == (IsaTerm.from_agent("fset"), IsaTerm.from_agent("FSet.fset"), IsaTerm.from_agent("ε"))
    assert all(isinstance(t, IsaTerm) for t in p.types) and p.types[2].ascii == "\\<epsilon>"
    assert p.opened is None                                             # recorded by a beginning, none yet (§1)
    assert p._state_before_ending in p._states_inside() and p.sub_nodes[0].state is not p.state
    c, d = p.sub_nodes
    assert isinstance(c, LiftDefinition) and f.id_of(c) == "lift_definition_fcard" and f.id_of(d) == "lemma_fcard_fempty"
    (q,) = insert(f, x, 1, [block("int-swap", ("int",))])                # a hyphen: the framework's grammar (§1)
    assert q.name == "int-swap" and f.id_of(q) == "lifting_context_int-swap" and q.sub_nodes == []
    inv(f)


def test_gen_refuses_as_section_4_says():
    """§4's refusals in its order: the parent first (COMMON §1's
    `NotInsideTheory`, pinned for every class by test_common.py); an
    entry of `types` that is no type's name, §4's first sentence, the
    grammar text the framework's; a repeat, the second; the type names
    before the node's name, which the framework judges after `gen`, and
    an empty `types`, the framework's `must not be empty`; a missing field,
    an `english` or the recorded field authored, by the framework."""
    f, x = forest()
    (s,) = f.sub_nodes
    e = refused(f, s, [block()], NotInsideTheory)
    assert (e.kind, e.parent_id, e.raw_ast_path) == ("lifting_context", "session_Arith", "constructs[0]")
    [identifier, twice] = fenced_blocks(LC, "4.")[0]
    assert identifier.endswith(GRAMMARS["type name"] + ".")
    e = refused(f, x, [block(types=("'a fset",))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + identifier and e.field == "types[0]"
    for name in ("fset_", "", "1st", "x y", "a..b", ".fset", "fset.", "FSet.fset_", "h\\<nat>", "fset-set", "'a"):
        assert refused(f, x, [block(types=("fset", name))], InvalidField).field == "types[1]", name
    e = refused(f, x, [block(types=("fset", " fset "))], InvalidField)
    assert str(e) == "At `constructs[0]`: " + twice and e.field == "types[1]"
    assert refused(f, x, [block(types=("'a", "fset", "fset"))], InvalidField).field == "types[0]"       # §4's order
    for types in (("FSet.fset",), ("x⇩1", "ε", "Probe.l.t", "int")):           # dots, letter symbols, subscripts
        (p,) = insert(f, x, 0, [block(types=types)])
        assert [t.unicode for t in p.types] == list(types)
        run(locked(f, edit.delete(p)))
    # the node's name: the framework's grammar and sentence (MCP_SPECIFICATION §2), judged after `gen`
    e = refused(f, x, [block("fset size")], InvalidName)
    assert (e.name, e.grammar) == ("fset size", "name")
    assert str(e) == "At `constructs[0]`: `fset size` is not a valid name: a name " + GRAMMARS["name"] + "."
    for name in ("1st", "fset_", "fset-", "", "α"):
        assert refused(f, x, [block(name)], InvalidName).grammar == "name"
    assert refused(f, x, [block("fset size", types=("'a",))], InvalidField).field == "types[0]"
    # an empty `types`: the framework's check of the construct (MODULE_STRUCTURE §4.4), RENDER_BASELINES §2's line
    [empty] = [line for line in fenced_lines(DOCS / "RENDER_BASELINES.md", "2.") if line == "The field `types` must not be empty."]
    e = refused(f, x, [block(types=())], InvalidField)
    assert str(e) == "At `constructs[0]`: " + empty and e.field == "types"
    for raw in ({"kind": "lifting_context", "name": "n"},                       # no `types`
                {"kind": "lifting_context", "types": ["fset"]},                 # no `name`
                {**block(), "types": "fset"},                                    # no list
                block(types=(1,)),
                block(english="e"),                                              # no `english` (§2)
                block(opened=["fset"])):                                         # recorded, not authored (§1)
        refused(f, x, [raw], RawASTError)
    assert x.sub_nodes == []
    inv(f)


def test_a_sibling_bearing_the_node_s_id_component_is_the_framework_s_duplicate_name():
    f, x = forest(FSET_SIZE)
    e = refused(f, x, [block(types=("int",))], DuplicateName)
    assert e.id_component == "lifting_context_fset_size" and e.taken_by == "lifting_context_fset_size"
    inv(f)


# --- the store (§1) ---------------------------------------------------------------

def test_the_fields_are_stored_and_a_missing_row_is_refused_at_start(tmp_path):
    path = tmp_path / "TAT.sqlite"
    f, x = forest(FSET_SIZE, block("two", ("dlist", "natural")), block("greek", ("α",)),
                  store=Forest_Store(path, ts.stand_ins.log()))
    p, two, greek = x.sub_nodes
    two.opened = (two.types[1],)                   # as a beginning records it (§6); `fset_size` unrecorded
    greek.opened = greek.types
    with f.store.transaction():
        for n in x.sub_nodes:
            f._store_node(n)

    def fields(n):
        return (n.name, n.types, n.opened)
    before = [fields(n) for n in x.sub_nodes]
    rows = f.store.fields(p.identity)
    assert set(ROWS) <= set(rows)                                                   # the rest the framework's
    assert rows["name"] == "fset_size" and rows["types"] == ["fset"] and rows["opened"] is None
    rows = f.store.fields(two.identity)
    assert rows["types"] == ["dlist", "natural"] and rows["opened"] == ["natural"]
    rows = f.store.fields(greek.identity)
    assert rows["types"] == ["α"] and rows["opened"] == ["α"]                       # the `unicode` spelling
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=KINDS)
    loaded = f2.sub_nodes[0].sub_nodes[0].sub_nodes
    assert [fields(n) for n in loaded] == before and all(isinstance(n, LiftingContext) for n in loaded)
    assert loaded[0].opened is None and loaded[2].opened[0].ascii == "\\<alpha>"
    assert [c.name for c in loaded[0].sub_nodes] == ["fcard", "fcard_fempty"]
    f2.store.close()
    assert_a_missing_row_is_refused_at_start(path, p.identity, ROWS)            # every row, the recorded one too (§1)


# --- the beginning and the recorded `opened`, the ending (§6), the mark (§7) ------

def fake_wire(monkeypatch, beginning):
    """The fake wire for a theory of the plugin's classes: `beginning`
    answers `TAT.LiftingContext.open` from the names sent — the messages
    and the opened names —; a child's callback and the ending's answer
    clean; every call kept."""
    calls = []

    async def call(conversation, name, args):
        calls.append((name, args))
        if name == "TAT.LiftingContext.open":
            return beginning(args[2])
        if name == "TAT.LiftingContext.close":
            return []
        return [[], [False, None]] if name == "TAT.LiftDefinition.evaluate" else [[], [None, None]]
    monkeypatch.setattr(isabelle_driver, "call", call)
    return calls


def test_eval_beginning_opr_sends_the_types_in_ascii_and_records_opened(monkeypatch):
    """§6: `TAT.LiftingContext.open` with the beginning's two slots — the
    input slot and the first child's input, or the slot before the ending
    with no child — and `types` in `ascii`; the names it answers recorded
    as `opened`, the entries themselves, an entry open already left out;
    the sentences an obstacle with `opened` untouched, the children
    `not_evaluated`, the ending `Ready` by the copy; `opened` recorded
    anew by every beginning that goes through (§1); the mark the
    framework's (§7)."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        FSET_SIZE, block("both", ("int", "fset")), block("bad", ("nat",), children=[FCARD]), block("greek", ("α",))]})])
    (x,) = s.sub_nodes
    p, both, bad, greek = x.sub_nodes
    answers = {("nat",): [[SENTENCE], None], ("int", "fset"): [[], ["int"]]}    # `fset` open already: silent (§6)
    calls = fake_wire(monkeypatch, lambda names: answers.get(tuple(names), [[], names]))
    run(x.evaluate_to(None, False))
    mine = [args for name, args in calls if name == "TAT.LiftingContext.open"]
    assert mine == [(p.state.to_msgpack(), p.sub_nodes[0].state.to_msgpack(), ["fset"]),
                    (both.state.to_msgpack(), both._state_before_ending.to_msgpack(), ["int", "fset"]),
                    (bad.state.to_msgpack(), bad.sub_nodes[0].state.to_msgpack(), ["nat"]),
                    (greek.state.to_msgpack(), greek._state_before_ending.to_msgpack(), ["\\<alpha>"])]
    assert p.evaluation_status_beginning == M.READY_CLEAN and p.opened == (IsaTerm.from_agent("fset"),)
    assert both.opened == (IsaTerm.from_agent("int"),) and both.opened[0] is both.types[0]      # the entry itself
    assert greek.opened == greek.types and greek.opened[0].unicode == "α"
    assert isinstance(bad.evaluation_status_beginning, M.CannotEvaluate) and bad.opened is None
    assert [m.unicode for m in bad.evaluation_status_beginning.messages] == [SENTENCE]
    assert all(c._status is M.NOT_EVALUATED for c in bad.sub_nodes) and bad.evaluation_status_ending == M.READY_CLEAN
    assert all(isinstance(c._status, M.Ready) for c in p.sub_nodes) and p.evaluation_status_ending == M.READY_CLEAN
    assert [name for name, _ in calls].count("TAT.LiftingContext.close") == 3          # `bad`'s ending is the copy
    assert (p.mark(M.BRIEFING, 0), both.mark(M.BRIEFING, 0), bad.mark(M.BRIEFING, 0)) == ("incomplete", "complete", "failed")
    assert not p.is_finished() and both.is_finished()
    # recorded anew where `int` is open already too; a refusal leaves the record; two sentences in the entries' order
    answers[("int", "fset")] = [[], []]
    assert run(both._eval_beginning_opr()) == M.READY_CLEAN and both.opened == ()
    answers[("int", "fset")] = [[sentence("int"), sentence("fset")], None]
    status = run(both._eval_beginning_opr())
    assert isinstance(status, M.CannotEvaluate) and [m.unicode for m in status.messages] == [sentence("int"), sentence("fset")]
    assert both.opened == ()
    (fresh,) = insert(f, x, 4, [block("fresh", ("int",))])
    assert fresh.mark(M.BRIEFING, 0) == "not evaluated" and fresh.opened is None


def test_the_ending_calls_close_with_the_slot_after_the_last_child_the_resulting_slot_and_opened(monkeypatch):
    """§6: `TAT.LiftingContext.close` with the ending's two slots — the
    slot after the last child and the block's resulting slot — and
    `opened` in `ascii`, not `types`; no message is `Ready`, messages
    `CannotEvaluate` with them; `emit_ending` writes `end` and the pairs
    of `opened` and returns the indent; with nothing recorded the ending
    does not run."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        FSET_SIZE, block("both", ("int", "fset"))]})])
    (x,) = s.sub_nodes
    p, both = x.sub_nodes
    calls = fake_wire(monkeypatch, lambda names: [[], ["int"] if names == ["int", "fset"] else names])
    run(x.evaluate_to(None, False))
    endings = [args for name, args in calls if name == "TAT.LiftingContext.close"]
    assert endings == [(p._state_before_ending.to_msgpack(), p.resulting_state().to_msgpack(), ["fset"]),
                       (both._state_before_ending.to_msgpack(), both.resulting_state().to_msgpack(), ["int"])]
    assert p.operation_slots("ending") == (p._state_before_ending, p.resulting_state())
    assert p.evaluation_status_ending == M.READY_CLEAN and both.evaluation_status_ending == M.READY_CLEAN

    async def refusing(conversation, name, args):
        return ["Interrupt"] if name == "TAT.LiftingContext.close" else [[], []]
    monkeypatch.setattr(isabelle_driver, "call", refusing)
    status = run(both._eval_ending_opr())
    assert isinstance(status, M.CannotEvaluate) and [m.unicode for m in status.messages] == ["Interrupt"]
    out = io.StringIO()
    assert both.emit_ending(2, out) == 2
    assert out.getvalue() == "\n    end\n    lifting_update int.lifting\n    lifting_forget int.lifting\n"
    (fresh,) = insert(f, x, 2, [block("fresh", ("int",))])
    with pytest.raises(AssertionError):                 # no beginning went through: nothing to close
        run(fresh._eval_ending_opr())


def test_the_recorded_field_reaches_the_store_and_the_mirror_catches_an_emit_ending_off_the_live_status(monkeypatch):
    """§1, §6; COMPILATION §3: a walk's store writes `opened` as the
    beginning recorded it, so a loaded forest emits the same file; an
    `emit_ending` gated on the ending's live status writes `end` and the
    pairs in memory and not once loaded, which `assert_store_mirrors` says
    at once."""
    f = Forest_Under_Test(kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X", kind="fake_theory") | {"children": [
        FSET_SIZE, block("both", ("int", "fset"))]})])
    (x,) = s.sub_nodes
    p, both = x.sub_nodes
    fake_wire(monkeypatch, lambda names: [[], ["int"] if names == ["int", "fset"] else names])
    run(x.evaluate_to(None, False))
    rows = {n.name: f.store.fields(n.identity) for n in (p, both)}
    assert (rows["fset_size"]["opened"], rows["both"]["opened"]) == (["fset"], ["int"])
    assert_store_mirrors(f, KINDS, shape=ts.shape)                           # as shipped: mirrored
    emit_ending = LiftingContext.emit_ending

    def off_the_live_status(self, indent, out):
        return emit_ending(self, indent, out) if isinstance(self.evaluation_status_ending, M.Ready) else indent
    monkeypatch.setattr(LiftingContext, "emit_ending", off_the_live_status)
    with pytest.raises(AssertionError, match="Arith/X.thy: the loaded forest writes another text"):
        assert_store_mirrors(f, KINDS, shape=ts.shape)


# --- what it prints (§8) -----------------------------------------------------

def test_print_fields_writes_the_command_by_depth():
    f, x = forest(FSET_SIZE, block("two", ("dlist", "natural")))
    p, two = x.sub_nodes
    [one, failed, refused_ending] = fenced_blocks(LC, "8.")

    def fields(node, mode, depth):
        out = io.StringIO()
        node.print_fields(0, out, mode, depth)
        return out.getvalue().splitlines()
    assert [fields(p, M.RECALL, d) for d in range(4)] == [one, one, one, []]
    assert fields(p, M.OUT_FOCUS, 0) == [] and fields(p, M.Relative_Focus(frozenset({p}), 0), 0) == []
    assert fields(two, M.RECALL, 2) == ["context includes dlist.lifting and natural.lifting begin"]
    p.opened = ()                                                       # not printed: recorded (§8)
    x.keywords = frozenset({"fset", "dlist"})                           # the bundle's name bare whatever the keywords
    assert fields(p, M.RECALL, 0) == one and fields(two, M.RECALL, 0)[0].startswith("context includes dlist.lifting")
    x.keywords = None
    me = stand_ins.agent(f.conversation)
    # §8's two renderings whole: the refused beginning, the children not evaluated; the refused ending under a
    # beginning that went through, the children proven
    p.evaluation_status_beginning = M.CannotEvaluate((IsaTerm.from_agent(sentence("fset")),))
    assert f.render(p, M.RECALL, me).splitlines() == failed
    p.evaluation_status_beginning = M.READY_CLEAN
    for c in p.sub_nodes:
        with_proof(c, M.READY_CLEAN, PROVED, PASSED)
    p.evaluation_status_ending = M.CannotEvaluate((IsaTerm.from_agent("Interrupt"),))
    assert f.render(p, M.RECALL, me).splitlines() == refused_ending
    p.evaluation_status_beginning = p.evaluation_status_ending = M.NOT_EVALUATED      # back to a node no walk reached
    for c in p.sub_nodes:
        with_proof(c, M.NOT_EVALUATED, NOT_STARTED)
    p.opened = None
    inv(f)


# --- emission (§5) ------------------------------------------------------------

def test_the_emitted_text_is_section_5_s():
    [one, two] = fenced_blocks(LC, "5.")
    f, x = forest(FSET_SIZE, block("two", ("dlist", "natural")))
    p, pair = x.sub_nodes
    x.keywords = frozenset()                                 # recorded by a header run, which emission presupposes

    def emitted(node, indent=1) -> list[str]:
        """In `unicode` (§5); the file's `\\<name>` form is the compile's conversion (COMPILATION §2)."""
        out = io.StringIO()
        assert node.emit(indent, out) == indent
        assert "\\<" not in out.getvalue()                                 # nothing written in `ascii`
        return out.getvalue().splitlines()

    def expected(*unicode_lines: str, indent=1) -> list[str]:
        return ["  " * indent + line if line else "" for line in unicode_lines]
    fcard, fcard_fempty = p.sub_nodes
    fcard.with_code_dt = False                                      # as §5's example records it: no `(code_dt)`
    for c in p.sub_nodes:
        with_proof(c, M.READY_CLEAN, PROVED, PASSED)
    for node in (p, pair):
        with pytest.raises(AssertionError):                         # nothing recorded: never written (`can_emit`; §5)
            emitted(node)
    p.opened = p.types
    assert emitted(p) == expected(*one)
    assert emitted(p, 2) == expected(*one, indent=2)                  # the children at the block's indent
    pair.opened = pair.types
    assert emitted(pair) == expected(*two)
    pair.opened = (pair.types[1],)                                  # `dlist` open already: in the `includes`, no pair
    assert emitted(pair) == expected(*two[:3], *two[5:])
    pair.opened = ()
    assert emitted(pair) == expected(*two[:3])
    # a type named after a keyword of the theory: the bundle's name bare (COMMON §6); a qualified name
    (t,) = insert(f, x, 2, [block("kw", ("term", "FSet.fset"))])
    t.opened = t.types
    x.keywords = frozenset({"term", "fset", "FSet"})
    assert emitted(t) == expected("context includes term.lifting and FSet.fset.lifting begin", "", "end",
                                  "lifting_update term.lifting", "lifting_forget term.lifting",
                                  "lifting_update FSet.fset.lifting", "lifting_forget FSet.fset.lifting")
    with_proof(fcard_fempty, M.READY_CLEAN, PROVED, None)              # not proven: `sorry`
    assert emitted(p)[8] == "    sorry"


def test_the_two_spellings_are_kept_apart(monkeypatch):
    """§2, §5, §6, §8: an entry whose `unicode` and `ascii` differ is
    stored, printed and emitted in `unicode` and sent to Isabelle in
    `ascii`, and recorded as authored from the names the wire answers."""
    f, x = forest(block("greek", ("α", "β⇩1")))
    (p,) = x.sub_nodes
    x.keywords = frozenset()
    assert [t.ascii for t in p.types] == ["\\<alpha>", "\\<beta>\\<^sub>1"]
    rows = {}
    p.to_store(type("Rows", (), {"put": lambda self, k, v: rows.__setitem__(k, v)})())
    assert rows["types"] == ["α", "β⇩1"] and rows["opened"] is None
    calls = fake_wire(monkeypatch, lambda names: [[], names])
    assert run(p._eval_beginning_opr()) == M.READY_CLEAN
    assert calls[-1][1][2] == ["\\<alpha>", "\\<beta>\\<^sub>1"]              # sent in `ascii`
    assert [t.unicode for t in p.opened] == ["α", "β⇩1"]                      # recorded as authored
    assert run(p._eval_ending_opr()) == M.READY_CLEAN
    assert calls[-1][1][2] == ["\\<alpha>", "\\<beta>\\<^sub>1"]
    out = io.StringIO()
    p.print_fields(0, out, M.RECALL, 1)
    assert out.getvalue() == "context includes α.lifting and β⇩1.lifting begin\n"
    out = io.StringIO()
    p.emit(0, out)
    assert out.getvalue() == ("context includes α.lifting and β⇩1.lifting begin\n\nend\n"
                              "lifting_update α.lifting\nlifting_forget α.lifting\n"
                              "lifting_update β⇩1.lifting\nlifting_forget β⇩1.lifting\n")


# --- the id properties (§9), on test_ids.py's precedent -------------------------

def test_section_9_s_id_properties():
    """§9: the component is omissible in both directions with drop priority
    1 — after `Section`'s, before `Theory`'s —, a child's id printed as
    short as the forest allows and accepted with or without it; the
    node's own component never dropped from its own id."""
    assert (LiftingContext.output_omissible, LiftingContext.input_omissible, LiftingContext.drop_priority) == (True, True, 1)
    f, x = forest(FSET_SIZE, lift("fcard", "'a fset ⇒ nat", "λxs. card (set xs)", "Another size"))
    p, other = x.sub_nodes
    fcard, fcard_fempty = p.sub_nodes
    assert f.id_of(p) == "lifting_context_fset_size" and f.id_of(fcard_fempty) == "lemma_fcard_fempty"
    for form in ("lemma_fcard_fempty", "lifting_context_fset_size.lemma_fcard_fempty", "theory_X.lemma_fcard_fempty",
                 "session_Arith.theory_X.lifting_context_fset_size.lemma_fcard_fempty"):
        assert f.resolve(form) is fcard_fempty
    assert f.resolve("lifting_context_fset_size") is p and f.resolve("theory_X.lifting_context_fset_size") is p
    # the other `fcard` directly under the theory: the block's component tells the inner one apart, and the other
    # prints its full id, each shorter form of it being a form of the inner's (test_ids.py's exact-match rule)
    assert f.id_of(fcard) == "lifting_context_fset_size.lift_definition_fcard"
    assert f.id_of(other) == "session_Arith.theory_X.lift_definition_fcard" and f.resolve(f.id_of(other)) is other
    run(locked(f, edit.delete(other)))
    # before `Theory`'s: a second `fcard` in another theory — `theory_X.…` kept, the block's component dropped first
    (s,) = f.sub_nodes
    (y,) = insert(f, s, 1, [theory("Y") | {"children": [FSET_SIZE]}])
    assert f.id_of(fcard) == "theory_X.lift_definition_fcard"
    assert f.id_of(y.sub_nodes[0].sub_nodes[0]) == "theory_Y.lift_definition_fcard"
    run(locked(f, edit.delete(y)))
    # after `Section`'s: test_ids.py's `Sec` inside the block holding a `fsize`, another `fsize` directly under the
    # theory — the section dropped, the block kept
    sec = test_ids.mk_block(test_ids.Sec, p, "B")
    (inner,) = run(locked(f, edit.insert(sec, 0, [lift("fsize", "'a fset ⇒ nat", "λxs. card (set xs)", "The size")],
                                         {**KINDS, "section": test_ids.Sec})))
    (outer,) = insert(f, x, 1, [lift("fsize", "'a fset ⇒ nat", "λxs. card (set xs)", "The size")])
    assert f.id_of(inner) == "lifting_context_fset_size.lift_definition_fsize"
    assert f.resolve("section_B.lift_definition_fsize") is inner
    assert f.id_of(outer) == "session_Arith.theory_X.lift_definition_fsize" and f.id_of(fcard) == "lift_definition_fcard"


# --- the evaluation, in the plugin's run of the harness (§5, §6, §8) ------------

def size_as_integer(name, english):
    return lift(name, "'a fset ⇒ int", "λxs. (card (set xs), 0)", english)


# A theory of §2's `fset` (QUOTIENT_TYPE.md) holding `fcard`, a block opening `fset` inside it — open already:
# left alone —, a `lift_definition` after that block still accepted, and a block opening `int` and `fset` there;
# then §2's first construct with `fempty` in place of `fcard`, whose lemma needs `fcard`'s rule from the bundle;
# a second block on `fset`, whose lemma needs `fempty`'s rule, stored by the first's ending; two types at once;
# one block nested in another, the inner naming the outer's type too — open already in the outer's context alone
FSET_BLOCK = quotient(rep_function_name="list_of_fset", abs_function_name="fset_of_list", children=[
    FCARD,
    block("in_fset"),
    lift("fsingle", "'a ⇒ 'a fset", "λx. [x]", "The singleton finite set"),
    block("in_int_fset", ("int", "fset"), children=[size_as_integer("fi", "The number of elements as an integer")])])
FSET_SIZE_FEMPTY = block(children=[FEMPTY, FCARD_FEMPTY])
AGAIN = block("fset_again", children=[
    lemma("fcard_fempty_again", "fcard fempty = 0", "The same, from the stored rules", for_any=(), premises=())])
BOTH = block("both", ("fset", "int"), children=[size_as_integer("fi2", "The number of elements as an integer, again")])
NESTED = block("outer", children=[block("inner", ("int", "fset"), children=[size_as_integer("fi3", "And once more")])])
# HOL's `int`: a library type's pointer; a second block on it proving by `transfer`; its qualified name
INT_AGAIN = block("int_again", ("int",), children=[
    lemma("int_swap_swap", "int_swap (int_swap z) = z", "Swapping twice is the identity",
          for_any=({"name": "z", "type": "int"},), premises=())])
INT_QUALIFIED = block("int_qualified", ("Int.int",), children=[
    lemma("int_swap_zero", "int_swap 0 = 0", "Zero swapped is zero", for_any=(), premises=())])
# the forest's type by its qualified name, in a theory of its own
FQ = quotient("fq", rep_function_name="list_of_fq", abs_function_name="fq_of_list",
              children=[lift("fqcard", "'a fq ⇒ nat", "λxs. card (set xs)", "The number of elements")])
QUALIFIED = block("qualified", ("TAT_Std_LQ.fq",), children=[
    lift("fqempty", "'a fq", "[]", "The empty one"),
    lemma("fqcard_fqempty", "fqcard fqempty = 0", "The empty one has no element", for_any=(), premises=())])
# after a block, the setup closed again: a `lift_definition` refused (LIFT_DEFINITION.md §6), in a theory of its own
FS = quotient("fs", children=[lift("fscard", "'a fs ⇒ nat", "λxs. card (set xs)", "The number of elements")])
FS_OPEN = block("fs_open", ("fs",), children=[lift("fsempty", "'a fs", "[]", "The empty one")])
FS_AFTER = lift("fssize", "'a fs ⇒ nat", "λxs. card (set xs)", "The size, after the block")


@pytest.mark.isabelle(deadline=900)
async def test_a_block_opens_setups_again_and_its_ending_stores_the_rules_and_closes_them(std_conversation, std_harness,
                                                                                           tmp_path):
    """§6 through `TAT.LiftingContext.open` and `.close`, four theories:
    every block `Ready` at both ends with `opened` as §6 says — the entry
    open already left out, silently —, the `lift_definition` after such a
    block still accepted, the one after a block that closed the setup
    refused with LIFT_DEFINITION.md §6's sentence; `recall` as §8 shows;
    the files rendered as §5 shows and the first read back whole by
    Isabelle; then the proofs for real under `checks: "blocking"`: each
    lemma by `transfer` needs a rule the bundle holds — `fcard`'s, stored
    by the `quotient_type` block's ending (step 17's two `close` mutants),
    `fempty`'s, stored by a block's ending —, every check `PASSED`.  Last,
    the callbacks alone: the beginning's answer `[[], names]` on the wire,
    a refusal's `[[…], nil]`;
    `end` refused at theory level, where a block's ending leaves the state;
    `TAT.Lifting_Closing.close` on a name no bundle bears, Isabelle's own
    message."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                ts.theory("TAT_Std_LC") | {"children": [FSET_BLOCK, FSET_SIZE_FEMPTY, AGAIN, BOTH, NESTED]},
                ts.theory("TAT_Std_LI") | {"children": [INT_SWAP, INT_AGAIN, INT_QUALIFIED]},
                ts.theory("TAT_Std_LQ") | {"children": [FQ, QUALIFIED]},
                ts.theory("TAT_Std_LA") | {"children": [FS, FS_OPEN, FS_AFTER]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 1, text
        (s,) = forest.sub_nodes
        lc, li, lq, la = s.sub_nodes
        fset, fset_size, again, both, outer = lc.sub_nodes
        fcard, in_fset, fsingle, in_int_fset = fset.sub_nodes
        (inner,) = outer.sub_nodes
        int_swap, int_again, int_qualified = li.sub_nodes
        _, qualified = lq.sub_nodes
        _, fs_open, after = la.sub_nodes
        opened = {fset_size: ["fset"], in_fset: [], in_int_fset: ["int"], again: ["fset"], both: ["fset", "int"],
                  outer: ["fset"], inner: ["int"], int_swap: ["int"], int_again: ["int"],
                  int_qualified: ["Int.int"], qualified: ["TAT_Std_LQ.fq"], fs_open: ["fs"]}
        for node, names in opened.items():
            assert isinstance(node, LiftingContext), node.name
            assert node.evaluation_status_beginning == M.READY_CLEAN, (node.name, node.evaluation_status_beginning)
            assert node.evaluation_status_ending == M.READY_CLEAN, (node.name, node.evaluation_status_ending)
            assert node.opened is not None and [t.unicode for t in node.opened] == names, node.name
            assert await node.operation_slots("beginning")[1].is_initialized() and await node.resulting_state().is_initialized()
        for node in (fcard, fsingle, *in_int_fset.sub_nodes, *fset_size.sub_nodes, *again.sub_nodes, *both.sub_nodes,
                     *inner.sub_nodes, *int_swap.sub_nodes, *int_again.sub_nodes, *int_qualified.sub_nodes,
                     *qualified.sub_nodes, *fs_open.sub_nodes):
            assert node._status == M.READY_CLEAN, (node.name, node._status)
        [_, _, _, sentences, _] = fenced_blocks(DOCS / "node_classes" / "LIFT_DEFINITION.md", "6.")
        assert isinstance(after._status, M.CannotEvaluate)
        assert [m.unicode for m in after._status.messages] == [sentences[1].replace("fset", "fs")]
        # `recall` (§8): the command under the node's line, the children after it; the empty block's line
        recalled = await session.call_tool("recall", {"node_id": "lifting_context_fset_size"})
        lines = text_of(recalled).splitlines()
        assert not recalled.isError and "Error:" not in text_of(recalled), text_of(recalled)
        assert lines[:3] == ["- lifting_context_fset_size (incomplete)", "  context includes fset.lifting begin",
                             "  - lift_definition_fempty (unverified definition, proof not started)"], lines
        recalled = await session.call_tool("recall", {"node_id": "lifting_context_in_fset"})
        assert text_of(recalled).splitlines() == [
            "- lifting_context_in_fset (complete)", "  context includes fset.lifting begin",
            "  " + M.EMPTY_NODE.format(id="lifting_context_in_fset")], text_of(recalled)
        # the files rendered as §5 shows: the pairs for `opened` alone, `in_fset` with none, the bundles joined by
        # ` and `, the qualified names bare; the theory with the obstacle not written
        rendered = C.render(forest)
        file = rendered.files[C.Path("TAT_Suite/TAT_Std_LC.thy")]
        assert file.startswith('theory "TAT_Std_LC"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n') and file.endswith("end\n")
        assert "context includes fset.lifting begin\n\nend\n\n" in file                          # `in_fset`: no pair
        assert "context includes int.lifting and fset.lifting begin\n" in file
        assert ("end\nlifting_update int.lifting\nlifting_forget int.lifting\n\n"
                "lifting_update fset.lifting\n") in file           # `in_int_fset`: `int` alone, then the type's own ending
        assert file.count("lifting_update fset.lifting\nlifting_forget fset.lifting\n") == 5    # `fset`'s own ending, four blocks
        assert "context includes fset.lifting and int.lifting begin\n" in file
        assert ("end\nlifting_update fset.lifting\nlifting_forget fset.lifting\n"
                "lifting_update int.lifting\nlifting_forget int.lifting\n") in file                 # `both`
        assert "context includes fset.lifting begin\n\ncontext includes int.lifting and fset.lifting begin\n" in file   # `outer`, `inner`
        assert "context includes Int.int.lifting begin\n" in rendered.files[C.Path("TAT_Suite/TAT_Std_LI.thy")]
        assert "\nlifting_update Int.int.lifting\nlifting_forget Int.int.lifting\n" in rendered.files[C.Path("TAT_Suite/TAT_Std_LI.thy")]
        assert "context includes TAT_Std_LQ.fq.lifting begin\n" in rendered.files[C.Path("TAT_Suite/TAT_Std_LQ.thy")]
        assert C.Path("TAT_Suite/TAT_Std_LA.thy") not in rendered.files
        # the first file read back whole by Isabelle under what it imports, with `sorry` everywhere
        await read_back(std_harness, file, tmp_path)
        # the proofs for real (COMMON §3): each lemma's by `transfer` on the rules the bundles hold
        proofs = {fset_size.sub_nodes[1]: "(transfer, simp)", again.sub_nodes[0]: "(transfer, simp)",
                  qualified.sub_nodes[1]: "(transfer, simp)",
                  int_again.sub_nodes[0]: "(transfer, auto simp add: intrel_def)",
                  int_qualified.sub_nodes[0]: "(transfer, simp add: intrel_def)"}
        for node, proof in proofs.items():
            node.job().outcome = Succeeded({"text": proof, "thread_cpu": 2000, "wall": 2000})
        for node in (fset_size, int_again, qualified):
            await tm._invalidate(node)
        for theory_id in ("theory_TAT_Std_LC", "theory_TAT_Std_LI", "theory_TAT_Std_LQ"):
            result = await session.call_tool("evaluate_to", {"node_id": theory_id, "checks": "blocking"})
            assert not result.isError, text_of(result)
        for node in proofs:
            assert node.check_outcome() is PASSED and node.mark(M.BRIEFING, 0) == "valid statement, proven", node.name
        assert [t.unicode for t in fset_size.opened] == ["fset"]                    # the same record after the re-run (§1)
        # the callbacks alone (§6), on slots beside the tree's
        resulting = M.Isar_State_Slot.assign(forest.conversation)
        messages, names = await isabelle_driver.call(
            forest.conversation, "TAT.LiftingContext.open",
            (fset_size.state.to_msgpack(), resulting.to_msgpack(), ["fset", "int"]))
        assert (messages, names) == ([], ["fset", "int"]) and await resulting.is_initialized()
        messages, names = await isabelle_driver.call(
            forest.conversation, "TAT.LiftingContext.open",
            (fcard.resulting_state().to_msgpack(), resulting.to_msgpack(), ["fset", "int", "nat"]))
        assert (messages, names) == ([sentence("nat")], None)
        resulting = M.Isar_State_Slot.assign(forest.conversation)
        messages = await isabelle_driver.call(
            forest.conversation, "TAT.LiftingContext.close",
            (int_swap.resulting_state().to_msgpack(), resulting.to_msgpack(), []))
        assert len(messages) == 1 and messages[0].startswith("Bad context for command"), messages
        assert not await resulting.is_initialized()
        messages = await isabelle_driver.call(
            forest.conversation, "TAT.Lifting_Closing.close",
            (int_swap.resulting_state().to_msgpack(), resulting.to_msgpack(), "nosuch"))
        assert messages == ['Undefined bundle: "nosuch.lifting"'] and not await resulting.is_initialized()


@pytest.mark.isabelle(deadline=600)
async def test_refused_openings_are_obstacles(std_conversation):
    """§6, §8, one theory per obstacle: §2's first construct where no
    `fset` is defined, `recall` as §8's first rendering shows; `nat`, a
    type with no Lifting setup, and a name no type bears, the sentence;
    `nat` with the forest's type after its block, the sentence for `nat`
    alone; three entries with two refused, two sentences in the entries'
    order; a name with a letter symbol, shown as authored; each an
    obstacle with `opened` untouched, the children `not_evaluated`, the
    ending `Ready` by the copy; no such theory written."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite",
                ts.theory("TAT_Std_LR") | {"children": [FSET_SIZE]},
                ts.theory("TAT_Std_LN") | {"children": [block("nat_block", ("nat",))]},
                ts.theory("TAT_Std_LS") | {"children": [block("nosuch_block", ("nosuch",))]},
                ts.theory("TAT_Std_LT") | {"children": [quotient("fs3"), block("after3", ("nat", "fs3"))]},
                ts.theory("TAT_Std_LU") | {"children": [quotient("fs4"), block("after4", ("nosuch", "fs4", "nat"))]},
                ts.theory("TAT_Std_LG") | {"children": [block("greek", ("α",))]})]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 7, text       # one block per message: `after4` has two
        (s,) = forest.sub_nodes
        (fset_size,), (nat_block,), (nosuch_block,), (_, after3), (_, after4), (greek,) = (t.sub_nodes for t in s.sub_nodes)
        refused_names = {fset_size: ["fset"], nat_block: ["nat"], nosuch_block: ["nosuch"], after3: ["nat"],
                         after4: ["nosuch", "nat"], greek: ["α"]}
        for node, names in refused_names.items():
            assert isinstance(node.evaluation_status_beginning, M.CannotEvaluate), node.name
            assert [m.unicode for m in node.evaluation_status_beginning.messages] == [sentence(n) for n in names], node.name
            assert node.opened is None and node.evaluation_status_ending == M.READY_CLEAN, node.name
            assert all(c._status is M.NOT_EVALUATED for c in node.sub_nodes)
            assert not await node.operation_slots("beginning")[1].is_initialized()
            assert await node.resulting_state().is_initialized()                        # the copy
        assert greek.evaluation_status_beginning.messages[0].ascii == sentence("\\<alpha>")   # Isabelle's spelling on the wire
        [_, failed, _] = fenced_blocks(LC, "8.")
        recalled = await session.call_tool("recall", {"node_id": "lifting_context_fset_size"})
        assert not recalled.isError and text_of(recalled).splitlines() == failed, text_of(recalled)
    rendered = C.render(forest)
    assert not any(C.Path(f"TAT_Suite/TAT_Std_L{t}.thy") in rendered.files for t in "RNSTUG")
