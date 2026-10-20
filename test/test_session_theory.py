"""`Session`, `Theory` and `Unchained_Node` (node_classes/SESSION_AND_THEORY.md,
the plan's §6) against the fake state slot table: gen's checks and their
approved wording, the unchained container under edits, moves, ids, the
store round trip, and the slot chain of a tree whose header failed.
Running a real header needs Isabelle: test/test_conversation.py.
Run: python -m pytest test/test_session_theory.py
"""

import io
import os
from pathlib import Path

import pytest

import stand_ins
import test_model as tm
from baselines import DOCS, fenced_blocks, fenced_lines
from invariants import assert_invariants, assert_store_mirrors
from test_model import CONN, locked, run

import isabelle_theory_agent.model as M
from isabelle_theory_agent import edit, isabelle_driver
from isabelle_theory_agent.exceptions import (
    BadSessionNodeParent, BadTheoryNodeParent, DuplicateTheoryShortName,
    InvalidField, InvalidName, ReservedSessionName, ReservedTheoryName, TAT_InternalError,
    TAT_StartupError)
from isabelle_theory_agent.model import NOT_EVALUATED, EvaluationResult, Session, Theory
from Isabelle_RPC_Host.unicode import IsaTerm
from test_model import CANNOT_EVALUATE, READY
from isabelle_theory_agent.store import Forest_Store

HEAP = {"List": "HOL.List", "Main": "Main"}   # the fake base heap: short name -> long name
RESERVED = {"FOL"}                # global in the fake Isabelle session layout, loaded nowhere
KNOWN_SESSIONS = {"HOL", "HOL-Library", "Graph_Theory"}   # the sessions the fake layout knows
RESERVED_SESSIONS = {"AUX"}       # what the fake Isabelle refuses as a file or session name, in any spelling
KNOWN_OPTIONS = {"document", "document_tags", "quick_and_dirty", "timeout"}
BOOL_OPTIONS = {"quick_and_dirty"}  # of those, the ones whose value is `true` or `false`


# Three `Theory` fakes against the fake state slot table, each standing for
# one outcome of the real class's two operations (the plan's §6).

class Fake_Theory(Theory):
    """Header and `end` both pass: the beginning writes the first child's
    slot, the ending writes the owned resulting slot and the fake theory
    table, as the real one does through `end_theory`."""
    async def _eval_beginning_opr(self):
        tm.TABLE.values[self._state_after_beginning().name] = f"begin {self.name}"
        self.keywords = frozenset()                          # recorded as the real run records them
        return READY
    async def _eval_ending_opr(self):
        tm.TABLE.values[self._state_after_ending.name] = f"end {self.name}"
        tm.TABLE.theories.add(self.qualified_name())
        return READY

class Failing_Header_Theory(Fake_Theory):
    """The header fails: the beginning writes nothing and answers a
    `CannotEvaluate` with the message, as the real one does on a bad
    import."""
    async def _eval_beginning_opr(self):
        return M.CannotEvaluate((IsaTerm.from_isabelle("No such file: TAT_Nowhere.thy"),))

class Failing_End_Theory(Fake_Theory):
    """`end` fails: the ending writes nothing and answers a `CannotEvaluate`;
    the framework copies the open theory's state through."""
    async def _eval_ending_opr(self):
        return M.CannotEvaluate((IsaTerm.from_isabelle("Bad theory ending"),))


KINDS = {"session": Session, "theory": Theory, "fake_theory": Fake_Theory,
         "failing_header_theory": Failing_Header_Theory,
         "failing_end_theory": Failing_End_Theory,
         "t": tm.T, "block": tm.Block}                       # a theory's children


class Forest_Under_Test(M.Forest):
    def __init__(self, conn=CONN, store=None, kinds=KINDS, imports=()):
        super().__init__(stand_ins.conversation(conn),
                         store if store is not None else Forest_Store(":memory:", stand_ins.log()), kinds, imports)


@pytest.fixture(autouse=True)
def table(monkeypatch, request):
    # An Isabelle-backed case talks to the real wire; the fake would answer
    # `state_exists` and the checks in place of Isabelle (conftest `HARNESSES`).
    if any(name in request.fixturenames for name in ("harness", "std_harness")):
        return
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)
    async def check_new_theory_short_name(conversation, name):
        if name in HEAP:
            return isabelle_driver.Taken(HEAP[name])
        if name in RESERVED:
            return isabelle_driver.Reserved()
        return isabelle_driver.Free()
    monkeypatch.setattr(isabelle_driver, "check_new_theory_short_name",
                        check_new_theory_short_name)
    async def check_session(conversation, name, parent_session, options):
        """The first defect, in `Loader.check_session`'s order."""
        if name.upper() in RESERVED_SESSIONS:
            return isabelle_driver.Name_Reserved()
        if name in KNOWN_SESSIONS:
            return isabelle_driver.Name_Known()
        for i, (option, value) in enumerate(options):
            if option not in KNOWN_OPTIONS:
                return isabelle_driver.Option_Refused(i, f'Unknown option "{option}"')
            if option in BOOL_OPTIONS and value not in ("true", "false"):   # Isabelle's two lines
                return isabelle_driver.Option_Refused(
                    i, f'Malformed value for option "{option}" : bool =\n"{value}"')
        if parent_session is not None and parent_session not in KNOWN_SESSIONS:
            return isabelle_driver.Parent_Unknown()
        return isabelle_driver.Session_Ok()
    monkeypatch.setattr(isabelle_driver, "check_session", check_session)


def shape(forest):
    def fields(n):
        if isinstance(n, Session):
            return (n.parent_session, n.options, n.description)
        if isinstance(n, Theory):
            return tuple(n.imports)
        if isinstance(n, tm.Block):
            return (n.fail_beginning, n.fail_ending)
        return getattr(n, "fail", None)      # a leaf of another class: its rows are its own tests'
    return [(n.identity, n.kind, n.name, fields(n),
             len(n.sub_nodes) if isinstance(n, M.NonLeaf_Node) else None)
            for n in forest._all_nodes()]


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, shape=shape)


def theory(name, *imports, kind="theory", **fields):
    return {"kind": kind, "name": name, "imports": list(imports) or ["Main"], **fields}


def session(name, *children, **fields):
    raw = {"kind": "session", "name": name, "parent_session": "HOL", **fields}
    if children:
        raw["children"] = list(children)
    return raw


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws)))


def arith():
    """Sessions > [session_Arith > [theory_X, theory_Y > [t_a]]]."""
    f = Forest_Under_Test()
    (s,) = insert(f, f, 0, [session("Arith", theory("X"), theory("Y", "Arith.X"))])
    x, y = s.sub_nodes
    (a,) = insert(f, y, 0, [{"kind": "t", "name": "a"}])
    return f, s, x, y, a


# --- what a session and its theories are -------------------------------------

def test_a_session_with_its_theories_in_one_call():
    f, s, x, y, a = arith()
    assert (s.name, x.name, y.name) == ("Arith", "X", "Y")            # as the agent wrote them
    assert [n.id_component() for n in (s, x, y, a)] == \
        ["session_Arith", "theory_X", "theory_Y", "t_a"]
    assert (s.parent_session, s.options, s.description) == ("HOL", [], "")
    assert x.imports == ["Main"] and y.imports == ["Arith.X"]
    assert (s.kind, x.kind) == ("session", "theory")
    assert [f.id_of(n) for n in (s, x, y, a)] == ["session_Arith", "theory_X", "theory_Y", "t_a"]
    assert f.resolve("session_Arith.theory_Y.t_a") is a
    assert x.header() == 'theory "X"\n  imports "Main"\nbegin'
    assert not f.is_finished() and s._operations_ready() and not x._operations_ready()
    inv(f)


def test_the_fields_are_kept_and_stored(tmp_path):
    store = Forest_Store(tmp_path / "TAT.sqlite", stand_ins.log())
    f = Forest_Under_Test(store=store)
    (s,) = insert(f, f, 0, [session(
        "Arith", theory("X", "Main", "HOL-Library.Multiset", description="Sums,\nverified."),
        options=[{"name": "document", "value": "pdf"}, {"name": "timeout", "value": "600"}],
        description="Arithmetic")])
    assert s.options == [{"name": "document", "value": "pdf"}, {"name": "timeout", "value": "600"}]
    assert s.description == "Arithmetic" and s.sub_nodes[0].description == "Sums,\nverified."   # as written
    assert s.sub_nodes[0].header() == 'theory "X"\n  imports "Main" "HOL-Library.Multiset"\nbegin'
    before = shape(f)
    store.close()
    f2 = Forest_Under_Test(store=Forest_Store(tmp_path / "TAT.sqlite", stand_ins.log()))
    assert shape(f2) == before
    s2 = f2.sub_nodes[0]
    assert isinstance(s2, Session) and s2.parent is f2
    assert isinstance(s2.sub_nodes[0], Theory) and s2.sub_nodes[0].parent is s2
    assert tm.st(s2.sub_nodes[0]) == (NOT_EVALUATED, NOT_EVALUATED)
    assert (s2.description, s2.sub_nodes[0].description) == ("Arithmetic", "Sums,\nverified.")


def test_a_restart_keeps_the_stored_statuses_of_a_tree_the_walk_does_not_enter(tmp_path):
    """COMPILATION.md §4: a rerun stores what it finds; a tree the walk does
    not enter keeps its stored statuses, messages included."""
    store = Forest_Store(tmp_path / "TAT.sqlite", stand_ins.log())
    f = Forest_Under_Test(store=store)
    (s,) = insert(f, f, 0, [session(
        "S", theory("Good", kind="fake_theory"), theory("BadHeader", kind="failing_header_theory"))])
    good, bad = s.sub_nodes
    run(good.evaluate_to(None, False))
    run(bad.evaluate_to(None, True))
    assert tm.st(good) == (READY, READY)
    assert isinstance(tm.st(bad)[0], M.CannotEvaluate)
    store.close()
    f2 = Forest_Under_Test(store=Forest_Store(tmp_path / "TAT.sqlite", stand_ins.log()))
    good2, bad2 = f2.sub_nodes[0].sub_nodes
    assert good2.last_evaluation_statuses() == (READY, READY)
    beginning = bad2.last_evaluation_statuses()[0]
    assert isinstance(beginning, M.CannotEvaluate)
    assert [m.unicode for m in beginning.messages] == ["No such file: TAT_Nowhere.thy"]
    run(good2.evaluate_to(None, False))                         # reruns Good alone
    assert tm.st(good2) == (READY, READY) and good2.last_evaluation_statuses() == (READY, READY)
    assert tm.st(bad2) == (NOT_EVALUATED, NOT_EVALUATED)   # not entered: instant untouched
    assert bad2.last_evaluation_statuses()[0] == beginning  # and the stored status kept
    inv(f2)


def test_the_string_token_follows_isabelles_quoting_rule():
    """COMPILATION.md §3, the rule of `Symbol_Pos.quote_string_qq`: a double
    quote and a lone backslash escaped; Isabelle symbols — `\\<and>`,
    `\\<^sub>`, even an unfinished `\\<` — left intact; a non-blank ASCII
    control character as its three-digit code, blanks raw; a carriage
    return read as a newline."""
    assert M.string_token("xs = ys") == '"xs = ys"'
    assert M.string_token('say "hi"') == r'"say \"hi\""'
    assert M.string_token("a \\ b") == r'"a \\ b"'
    assert M.string_token("P \\<and> Q\\<^sub>1 \\<open>t\\<close>") == '"P \\<and> Q\\<^sub>1 \\<open>t\\<close>"'
    assert M.string_token("x\\<") == '"x\\<"'
    assert M.string_token("a\x01b\x1fc") == '"a\\001b\\031c"'
    assert M.string_token("a\tb\nc\x0bd\x0ce ") == '"a\tb\nc\x0bd\x0ce "'
    assert M.string_token("a\r\nb\rc") == '"a\nb\nc"'
    assert M.string_token("λx. x ≠ y") == '"λx. x ≠ y"'


def test_the_theory_name_and_every_import_are_string_tokens():
    """SESSION_AND_THEORY §2: the theory's own name is a string token, as
    every import is, whatever keywords whoever builds the file reads it
    with."""
    f = Forest_Under_Test()
    (s,) = insert(f, f, 0, [session("S", theory("text"), theory("lemma", "HOL-Library.Multiset"))])
    t, l = s.sub_nodes
    assert t.header() == 'theory "text"\n  imports "Main"\nbegin'
    assert l.header() == 'theory "lemma"\n  imports "HOL-Library.Multiset"\nbegin'


def test_import_sessions_and_keywords_are_stored_and_a_missing_row_reads_as_empty_or_none(tmp_path):
    """COMPILATION.md §4, "Storage": the recorded fields ride with the
    node's rows; a database that predates the rows loads `import_sessions`
    empty and `keywords` None, under which `can_emit` refuses whatever the
    stored statuses, and, with the keywords known, refuses a stored status
    that is not `Ready`; `print_name` quotes a keyword and nothing else
    (SESSION_AND_THEORY §2)."""
    store = Forest_Store(tmp_path / "TAT.sqlite", stand_ins.log())
    f = Forest_Under_Test(store=store)
    (s,) = insert(f, f, 0, [session("S", theory("A", kind="fake_theory"),
                            theory("B", kind="fake_theory"))])
    a, b = s.sub_nodes
    assert a.import_sessions == [] and a.keywords is None
    assert (a.file_path(), b.file_path()) == (Path("S/A.thy"), Path("S/B.thy"))
    a.import_sessions = ["HOL", "HOL-Library"]              # what a header's run records
    a.keywords = frozenset({"and", "lemma"})
    assert (a.print_name("and"), a.print_name("lemma"), a.print_name("xs")) == ('"and"', '"lemma"', "xs")
    with store.transaction():
        f._store_node(a)
    store._conn.execute("DELETE FROM fields WHERE node = ? AND field = 'import_sessions'",
                        (b.identity,))                      # `keywords`: a theory never run has no row
    store.close()
    f2 = Forest_Under_Test(store=Forest_Store(tmp_path / "TAT.sqlite", stand_ins.log()))
    a2, b2 = f2.sub_nodes[0].sub_nodes
    assert a2.import_sessions == ["HOL", "HOL-Library"] and a2.keywords == frozenset({"and", "lemma"})
    assert b2.import_sessions == [] and b2.keywords is None
    b2._last_evaluation_statuses = [READY, READY]           # a `Ready` header whose keywords are unrecorded
    assert not b2.can_emit()
    b2.keywords = frozenset()
    assert b2.can_emit()
    b2._last_evaluation_statuses = [READY, NOT_EVALUATED]   # keywords known, the ending not `Ready`
    assert not b2.can_emit()


def test_print_name_writes_a_piece_of_isabelle_text_bare_or_as_a_string_token():
    """SESSION_AND_THEORY §2: bare when its `ascii` spelling is an identifier
    that is not in the keyword set given, Isabelle's string token
    otherwise, written in `unicode`; a `str` is the text's `ascii`, an
    `IsaTerm` carries both; the theory's `print_name` is the rule against
    its `keywords`, none known while they are None."""
    f = Forest_Under_Test()
    (s,) = insert(f, f, 0, [session("S", theory("A", kind="fake_theory"))])
    (a,) = s.sub_nodes
    a.keywords = frozenset({"and", "lemma"})
    for bare in ("xs", "UNIV", "a", "x'", "x_1"):
        assert a.print_name(bare) == M.print_name(bare, a.keywords) == bare
    assert (a.print_name("\\<alpha>"), a.print_name("x\\<^sub>1")) == ("α", "x₁")    # identifiers on `ascii`, written in `unicode`
    for quoted in ("and", "lemma", "'a", "{xs. distinct xs}", "0.5", "0", "List.list"):
        assert a.print_name(quoted) == f'"{quoted}"'
    assert a.print_name("'a \\<Rightarrow> 'b") == '"\'a ⇒ \'b"'
    assert a.print_name(IsaTerm.from_agent("'a ⇒ 'b")) == '"\'a ⇒ \'b"'
    assert a.print_name(IsaTerm.from_agent("x⇩1")) == "x⇩1"
    assert a.print_name(IsaTerm.from_agent("lemma")) == '"lemma"'
    assert M.print_name(IsaTerm.from_agent("lemma")) == "lemma"              # against no keyword: `recall`'s rule
    assert M.print_name("'a") == '"\'a"'
    a.keywords = None
    assert (a.print_name("and"), a.print_name("'a")) == ("and", '"\'a"')


class Real_Theories:
    """A forest of the real `Theory` on a working directory of its own, the
    class's two callbacks faked, both passing; `refused` is a tree whose
    beginning cannot make its `Session`'s folder."""
    def __init__(self, tmp_path, monkeypatch, *sessions):
        self.calls = []
        async def call(conversation, name, args):
            self.calls.append((name, args))
            return ([], ["HOL"], ["and", "lemma"]) if name == "TAT.Theory.begin" else []
        monkeypatch.setattr(isabelle_driver, "call", call)
        self.directory = tmp_path / "work"
        self.directory.mkdir()
        log = stand_ins.log()
        self.forest = M.Forest(M.Conversation(CONN, self.directory, log, stand_ins.ending()),
                               Forest_Store(":memory:", log), KINDS)
        self.sessions = insert(self.forest, self.forest, 0, list(sessions))

    def refused(self, s, sentence):
        """COMPILATION.md §7's sentence ends the conversation — a
        `TAT_StartupError`, no `TAT_Error`, so the walk passes it on as it
        is — and nothing ran: no round trip, the statuses and the
        database's rows as they were."""
        (tree,) = s.sub_nodes
        store = self.forest.store
        calls, rows = len(self.calls), {n: store.fields(n) for n in store.nodes()}
        with pytest.raises(M.CannotUseWorkingDirectory) as e:
            run(tree.evaluate_to(None, False))
        assert isinstance(e.value, TAT_StartupError)
        assert str(e.value) == (sentence.replace("<working directory>", str(self.directory))
                                .replace("<Session name>", s.name))
        assert tm.st(tree) == (NOT_EVALUATED, NOT_EVALUATED) and len(self.calls) == calls
        assert {n: store.fields(n) for n in store.nodes()} == rows


def test_a_theorys_beginning_makes_its_sessions_folder_or_ends_the_conversation(tmp_path, monkeypatch):
    """MODULE_STRUCTURE §4.1: before its header runs, a `Theory` makes its
    `Session`'s folder when that is absent; a path that holds anything but
    a directory ends the conversation."""
    case = Real_Theories(tmp_path, monkeypatch, session("Arith", theory("X")),
                         session("Taken", theory("T")), session("Linked", theory("L")))
    arith, taken, linked = case.sessions
    (x,) = arith.sub_nodes
    assert not (case.directory / "Arith").exists()            # creating the session makes nothing
    run(x.evaluate_to(None, False))
    assert (case.directory / "Arith").is_dir() and tm.st(x) == (READY, READY)
    name, (_, (_, master_dir, _)) = case.calls[0]
    assert (name, master_dir) == ("TAT.Theory.begin", str(case.directory / "Arith"))
    assert x.import_sessions == ["HOL"] and x.keywords == frozenset({"and", "lemma"})   # what the run answered

    _, _, (a_link, not_a_directory, _) = fenced_blocks(DOCS / "COMPILATION.md", "7.")
    (case.directory / "Taken").write_text("a file")
    (case.directory / "Linked").symlink_to(case.directory / "Arith")
    case.refused(linked, a_link)
    case.refused(taken, not_a_directory)


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes anywhere")
def test_a_session_folder_the_system_will_not_make_ends_the_conversation(tmp_path, monkeypatch):
    case = Real_Theories(tmp_path, monkeypatch, session("Late", theory("N")))
    _, _, (_, _, cannot_be_made) = fenced_blocks(DOCS / "COMPILATION.md", "7.")
    os.chmod(case.directory, 0o500)
    try:
        case.refused(case.sessions[0],
                     cannot_be_made.replace("<the system's message>", "Permission denied"))
    finally:
        os.chmod(case.directory, 0o700)


# --- what a tree writes (COMPILATION.md §3) ----------------------------------

def test_a_tree_emits_its_header_its_nodes_and_its_end(tmp_path):
    """The `Theory` root emits the header its beginning runs, its nodes
    their text in tree order with one empty line between siblings, and
    `end`, every line whole.  `can_emit` reads the stored statuses, so a
    loaded tree, every instant status `not_evaluated`, answers as before
    the restart; a `Session` emits no Isar."""
    import io
    def text(tree):
        out = io.StringIO()
        assert tree.emit(0, out) == 0
        return out.getvalue()
    path = tmp_path / "TAT.sqlite"
    f = Forest_Under_Test(store=Forest_Store(path, stand_ins.log()))
    (s,) = insert(f, f, 0, [session("Arith", theory("Y", "Main", "HOL-Library.Multiset", kind="fake_theory"))])
    (y,) = s.sub_nodes
    insert(f, y, 0, [{"kind": "t", "name": "a"},
                     {"kind": "block", "name": "S", "children": [{"kind": "t", "name": "b"},
                                                                 {"kind": "t", "name": "c"}]},
                     {"kind": "t", "name": "d"}])
    written = text(y)
    assert written == ('theory "Y"\n  imports "Main" "HOL-Library.Multiset"\nbegin\n'
                       'text ‹a›\n'
                       '\n'
                       'section ‹S›\n'
                       'text ‹b›\n'
                       '\n'
                       'text ‹c›\n'
                       'text ‹end of S›\n'
                       '\n'
                       'text ‹d›\n'
                       'end\n')
    assert written.startswith(y.header() + "\n")           # the header the evaluation runs
    assert not any(n.can_emit() for n in y._tree_order())
    run(y.evaluate_to(None, False))
    assert all(n.can_emit() for n in y._tree_order())
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, stand_ins.log()))
    y2 = f2.sub_nodes[0].sub_nodes[0]
    assert not y2.is_finished() and all(n.can_emit() for n in y2._tree_order())
    assert text(y2) == written
    with pytest.raises(TAT_InternalError, match="emits no Isar"):
        f2.sub_nodes[0].emit(0, io.StringIO())


# --- the unchained container -------------------------------------------------

def test_children_are_not_chained():
    f, s, x, y, a = arith()
    # a tree owns its resulting slot; the container names none, before or after its children
    assert x.resulting_state() is x._state_after_ending and x._state_after_ending is not x.state
    for container, child in ((s, x), (f, s)):
        with pytest.raises(TAT_InternalError):
            container._resulting_state_of_child(child)
        with pytest.raises(TAT_InternalError):
            container._resulting_state_of_all_children()
    with pytest.raises(TAT_InternalError):
        s.resulting_state()
    # inside the tree the chain is the ordinary one
    assert a.resulting_state() is y._state_before_ending
    assert s._states_inside() == [s.state, x.state, x._state_before_ending, x._state_after_ending,
                                  y.state, a.state, y._state_before_ending, y._state_after_ending]
    # no operation of its own: nothing written, nothing owed, nothing to take or carry
    assert s._resulting_status() is NOT_EVALUATED and s._operations_ready()
    assert not s._predecessor_wrote(1) and s._source_before(1) is None
    # no edit around it copies a state: every call so far was a delete of what left
    assert all(c[0] == "delete" for c in tm.TABLE.calls), tm.TABLE.calls


def test_a_walk_never_reaches_a_session():
    f, s, x, y, a = arith()
    with pytest.raises(TAT_InternalError, match="reached a Session"):
        run(s._evaluate(M.Evaluation(None, False), M.Evaluating()))


def test_the_owned_slot_under_each_outcome_of_a_tree():
    """The plan's §6, the release invariant of a tree's owned resulting
    slot: held after a successful `end`; held after a failed `end`, whose
    copy-through copies the open theory's state; empty after a failed
    header, whose copy-through copies an input nobody wrote — the ending
    `ready` all the same (ARCHITECTURE §3.2).  Its input slot is never
    held."""
    f = Forest_Under_Test()
    (s,) = insert(f, f, 0, [session(
        "Arith", theory("Good", kind="fake_theory"),
        theory("BadEnd", kind="failing_end_theory"),
        theory("BadHeader", kind="failing_header_theory"))])
    good, bad_end, bad_header = s.sub_nodes
    (a,) = insert(f, good, 0, [{"kind": "t", "name": "a"}])
    values = tm.TABLE.values

    r = run(good.evaluate_to(None, False))
    assert r == EvaluationResult(None, None)
    assert tm.st(good) == (READY, READY) and good.is_finished()
    assert values[a.state.name] == "begin Good" and a.consumed == "begin Good"
    assert values[good._state_after_ending.name] == "end Good"
    inv(f)

    r = run(bad_end.evaluate_to(None, False))
    assert r.stopped_at is bad_end                           # a stop at the ending
    assert tm.st(bad_end)[0] is READY and isinstance(tm.st(bad_end)[1], M.CannotEvaluate)
    assert tm.st(bad_end)[1].messages
    assert values[bad_end._state_after_ending.name] == "begin BadEnd"   # copied through
    inv(f)

    r = run(bad_header.evaluate_to(None, False))
    assert r == EvaluationResult(None, None)                  # not a stop for its successors
    assert isinstance(tm.st(bad_header)[0], M.CannotEvaluate) and tm.st(bad_header)[1] is READY
    assert tm.st(bad_header)[0].messages and not bad_header.is_finished()
    assert bad_header._state_after_ending.name not in values
    inv(f)

    for tree in (good, bad_end, bad_header):
        assert tree.state.name not in values                 # nobody writes a tree's input
    # invalidating a tree releases what it wrote; deleting one, its whole slot set
    tm.invalidate(good)
    assert tm.st(good) == (NOT_EVALUATED, NOT_EVALUATED) and tm.st(a) is NOT_EVALUATED
    assert a.state.name not in values and good._state_after_ending.name not in values
    inv(f)
    for tree in (bad_end, bad_header):
        run(locked(f, edit.delete(tree)))
        inv(f)
    assert s.sub_nodes == [good]


def test_delete_and_amend_in_the_session_layer():
    f, s, x, y, a = arith()
    tm.TABLE.calls.clear()
    run(locked(f, edit.delete(x)))
    assert s.sub_nodes == [y] and x.parent is None
    assert [c[0] for c in tm.TABLE.calls] == ["delete"]        # x's three slots, no copy
    assert set(tm.TABLE.calls[0][1]) == {x.state.name, x._state_before_ending.name,
                                         x._state_after_ending.name}
    inv(f)
    # amending the session: its theories are inherited, nothing is copied
    tm.TABLE.calls.clear()
    (s2,) = run(locked(f, edit.amend(s, [session("Arith2", description="renamed")])))
    assert f.sub_nodes == [s2] and s2.sub_nodes == [y] and y.parent is s2
    assert (s2.name, s2.description, s2.identity) == ("Arith2", "renamed", s.identity)
    assert f.id_of(a) == "t_a" and f.resolve("session_Arith2.theory_Y.t_a") is a
    assert not [c for c in tm.TABLE.calls if c[0] == "copy"]
    inv(f)


# --- moves ------------------------------------------------------------------

def test_moving_between_sessions_and_the_parent_gates():
    f, s, x, y, a = arith()
    (s2,) = insert(f, f, 1, [session("Algebra")])
    tm.TABLE.calls.clear()
    run(locked(f, edit.move(x, s2, 0)))
    assert s.sub_nodes == [y] and s2.sub_nodes == [x] and x.parent is s2
    assert not [c for c in tm.TABLE.calls if c[0] == "copy"]
    inv(f)
    run(locked(f, edit.move(s2, f, 0)))                        # reordering sessions
    assert f.sub_nodes == [s2, s]
    with pytest.raises(BadTheoryNodeParent) as e:
        run(locked(f, edit.move(x, f, 0)))
    assert (e.value.kind, e.value.parent_id) == ("theory", "Sessions")
    with pytest.raises(BadTheoryNodeParent) as e:
        run(locked(f, edit.move(x, y, 0)))
    assert e.value.parent_id == "theory_Y"
    with pytest.raises(BadSessionNodeParent) as e:
        run(locked(f, edit.move(s2, s, 0)))
    assert (e.value.kind, e.value.parent_id) == ("session", "session_Arith")
    assert f.sub_nodes == [s2, s] and s2.sub_nodes == [x]      # nothing moved
    inv(f)


# --- gen's checks ------------------------------------------------------------

def test_where_a_session_and_a_theory_may_live():
    f, s, x, y, a = arith()
    with pytest.raises(BadSessionNodeParent) as e:
        insert(f, x, 0, [session("Inner")])
    assert (e.value.kind, e.value.parent_id) == ("session", "theory_X")
    assert e.value.raw_ast_path == "constructs[0]"
    with pytest.raises(BadTheoryNodeParent) as e:
        insert(f, f, 0, [theory("Z")])
    assert e.value.parent_id == "Sessions"
    with pytest.raises(BadTheoryNodeParent) as e:
        insert(f, x, 0, [theory("Z")])
    assert e.value.parent_id == "theory_X"
    # a parent still under construction in the same call: its full id
    with pytest.raises(BadSessionNodeParent) as e:
        insert(f, f, 1, [session("Outer", session("Inner"))])
    assert e.value.parent_id == "session_Outer"
    assert e.value.raw_ast_path == "constructs[0].children[0]"
    assert f.sub_nodes == [s] and x.sub_nodes == []
    inv(f)


def test_names():
    f, s, x, y, a = arith()
    # a theory's short name takes the theory-name grammar, judged by the
    # class as the agent spelt it, with the theory-name rendering: no
    # hyphen, no dot, no prime; a trailing underscore is legal there and is
    # the framework's grammar to refuse, with the rendering that names that
    # rule
    for bad in ("Foo-Bar", "A.B", "1x", "", "x y", "P'_2"):
        with pytest.raises(InvalidName) as e:
            insert(f, s, 0, [theory(bad)])
        assert (e.value.name, e.value.grammar) == (bad, "theory name")
    with pytest.raises(InvalidName) as e:
        insert(f, s, 0, [theory("x_")])
    assert (e.value.name, e.value.grammar) == ("x_", "name")
    # a session's name takes the session-name grammar, judged by the class
    # first — strictly narrower than the framework's, whose rendering can
    # therefore never fire for a session: interior hyphens, no prime
    for bad in ("Ch 2", "x-", "-x", "Ch.2", "S'"):
        with pytest.raises(InvalidName) as e:
            insert(f, f, 0, [session(bad)])
        assert (e.value.name, e.value.grammar) == (bad, "session name")
    (lib,) = insert(f, f, 0, [session("My-Library")])
    assert lib.name == "My-Library" and f.id_of(lib) == "session_My-Library"
    # a name Isabelle reserves as a file or session name, asked of Isabelle;
    # and `ROOT` in any spelling, TAT's own rule: the folder would be the
    # ROOT file's path
    for bad in ("Aux", "ROOT", "Root"):
        with pytest.raises(ReservedSessionName) as e:
            insert(f, f, 0, [session(bad)])
        assert e.value.name == bad and e.value.raw_ast_path == "constructs[0]"
    (sessions,) = insert(f, f, 0, [session("Sessions")])       # no name is reserved
    assert f.id_of(sessions) == "session_Sessions" and f.resolve("Sessions") is f
    (p,) = insert(f, y, 0, [{"kind": "t", "name": "p'"}])      # every other node keeps the prime
    assert p.id_component() == "t_p'"
    inv(f)


def test_a_theory_short_name_is_unique_everywhere():
    f, s, x, y, a = arith()
    (s2,) = insert(f, f, 1, [session("Algebra")])
    with pytest.raises(DuplicateTheoryShortName) as e:       # the base heap
        insert(f, s2, 0, [theory("List")])
    assert (e.value.short_name, e.value.holder) == ("List", "HOL.List")
    with pytest.raises(DuplicateTheoryShortName) as e:       # a loaded global: taken, by itself
        insert(f, s2, 0, [theory("Main")])
    assert (e.value.short_name, e.value.holder) == ("Main", "Main")
    with pytest.raises(ReservedTheoryName) as e:             # global in the layout, loaded nowhere
        insert(f, s2, 0, [theory("FOL")])
    assert e.value.name == "FOL"
    with pytest.raises(DuplicateTheoryShortName) as e:       # another session's tree
        insert(f, s2, 0, [theory("X")])
    assert (e.value.short_name, e.value.holder) == ("X", "theory_X")
    with pytest.raises(DuplicateTheoryShortName) as e:       # the same call, across sessions
        insert(f, f, 2, [session("More", theory("Q")), session("Yet", theory("Q"))])
    assert e.value.holder == "constructs[0].children[0]"
    assert e.value.raw_ast_path == "constructs[1].children[0]"
    # without regard to case: Isabelle refuses two theory files whose names
    # differ only in case — against the forest, and within the call
    with pytest.raises(DuplicateTheoryShortName) as e:
        insert(f, s2, 0, [theory("x")])
    assert (e.value.short_name, e.value.holder) == ("x", "theory_X")
    with pytest.raises(DuplicateTheoryShortName) as e:
        insert(f, f, 2, [session("More", theory("Queue")), session("Yet", theory("QUEUE"))])
    assert (e.value.short_name, e.value.holder) == ("QUEUE", "constructs[0].children[0]")
    # an amend may keep the short name: the node it replaces is leaving
    (x2,) = run(locked(f, edit.amend(x, [theory("X", "Main", "HOL.Rat", description="renamed")])))
    assert x2.imports == ["Main", "HOL.Rat"] and x2.identity == x.identity and x2.description == "renamed"
    assert s.sub_nodes == [x2, y]
    inv(f)


# The approved renderings of the two classes' InvalidField reasons
# (SESSION_AND_THEORY.md §3), each asserted verbatim and each covered.
REASONS = set(fenced_lines(DOCS / "node_classes" / "SESSION_AND_THEORY.md", "3."))
COVERED = set()


def test_the_field_checks():
    f, s, x, y, a = arith()
    def refused(parent, raw, field, reason):
        with pytest.raises(InvalidField) as e:
            insert(f, parent, 0, [raw])
        assert (e.value.field, e.value.reason) == (field, reason)
        e.value.raw_ast_path = None                # the cause line alone
        rendering = str(e.value)
        if rendering in REASONS:
            COVERED.add(rendering)
    empty, not_a_name = ("must not be empty",
                         "must be a theory name without quotes; a path is not allowed")
    refused(s, theory("Z") | {"imports": []}, "imports", empty)
    refused(s, theory("Z", "Main", ""), "imports[1]", empty)   # judged empty before its shape
    # an item is `<short name>` or `<session>.<short name>`, each half in
    # the session-name grammar: no quotes, no path, no `.thy`, no third
    # half, no prime in either half; the AFP's hyphenated names pass, and
    # the header quotes every item
    for item in ('"lib/Rel"', "lib/Rel", "Main.thy", "A.B.C", "S'.Foo", "S.Foo'", "-x"):
        refused(s, theory("Z", "Main", item), "imports[1]", not_a_name)
    (z,) = insert(f, s, 0, [theory("Z", "Main", "Launchbury.AList-Utils")])
    assert z.header() == 'theory "Z"\n  imports "Main" "Launchbury.AList-Utils"\nbegin'
    run(locked(f, edit.delete(z)))
    refused(f, session("S") | {"parent_session": ""}, "parent_session", empty)
    refused(f, session("S", parent_session="HOL-Libary"), "parent_session",
            "must name an existing session; `HOL-Libary` is not one")
    refused(f, session("S", parent_session="S"), "parent_session",
            "must not name the session itself")
    refused(f, session("S", parent_session="X"), "parent_session",
            "must name an existing session; `X` is not one")     # X is a theory, not a session
    refused(f, session("S", parent_session="S", options=[{"name": "", "value": "x"}]),
            "options[0].name", empty)                             # the parent is judged last
    refused(f, session("S", options=[{"name": "", "value": "x"}]), "options[0].name", empty)
    refused(f, session("S", options=[{"name": "document", "value": ""}]), "options[0].value",
            empty)
    refused(f, session("S", options=[{"name": "document", "value": "pdf"},
                                     {"name": "document", "value": "false"}]),
            "options[1].name", "sets the option `document` a second time")
    # what only Isabelle can say, the first defect of its one answer: the
    # name known to the session layout, an option refused, the parent last
    refused(f, session("Graph_Theory", parent_session="Nowhere",
                       options=[{"name": "documnet", "value": "pdf"}]),
            "name", "must not be the name of an existing Isabelle session; `Graph_Theory` is one")
    refused(f, session("S", parent_session="Nowhere",
                       options=[{"name": "document", "value": "pdf"},
                                {"name": "documnet", "value": "pdf"}]),
            "options[1]", 'is not accepted by Isabelle: Unknown option "documnet"')
    # a parent naming the session itself is judged after Isabelle's answer
    refused(f, session("S", parent_session="S", options=[{"name": "documnet", "value": "pdf"}]),
            "options[0]", 'is not accepted by Isabelle: Unknown option "documnet"')
    # a name Isabelle reserves is judged in that answer too, after the checks that cost none
    refused(f, session("Aux") | {"parent_session": ""}, "parent_session", empty)
    # a value supplied in quotes is read without them, as the ROOT writes
    # it; the lines of Isabelle's message are joined by single spaces
    refused(f, session("S", options=[{"name": "quick_and_dirty", "value": '"yes"'}]),
            "options[0]",
            'is not accepted by Isabelle: Malformed value for option "quick_and_dirty" : bool = "yes"')
    (quoted,) = insert(f, f, 1, [session("S", options=[{"name": "quick_and_dirty",
                                                        "value": '"true"'}])])
    assert quoted.options == [{"name": "quick_and_dirty", "value": '"true"'}]    # stored as supplied
    run(locked(f, edit.delete(quoted)))
    assert f.sub_nodes == [s] and s.sub_nodes == [x, y]
    assert COVERED == REASONS
    inv(f)


def test_session_names_are_compared_without_regard_to_case():
    """SESSION_AND_THEORY §1: a session named like one of the forest, or
    like an earlier construct of the call, but for case, is refused as the
    id component's conflict is."""
    from isabelle_theory_agent.exceptions import DuplicateName
    f, s, x, y, a = arith()                                    # session_Arith
    with pytest.raises(DuplicateName) as e:
        insert(f, f, 1, [session("ARITH")])
    assert (e.value.id_component, e.value.taken_by) == ("session_ARITH", "session_Arith")
    with pytest.raises(DuplicateName) as e:
        insert(f, f, 1, [session("P"), session("p")])
    assert (e.value.id_component, e.value.taken_by, e.value.raw_ast_path) == \
        ("session_p", "constructs[0]", "constructs[1]")
    assert f.sub_nodes == [s]
    # an amend may keep the name, in any case
    (arith2,) = run(locked(f, edit.amend(s, [session("ARITH")])))
    assert f.sub_nodes == [arith2] and arith2.name == "ARITH"
    inv(f)


def test_a_parent_session_is_one_the_call_keeps_or_adds_before_or_one_the_layout_knows():
    f, s, x, y, a = arith()                                    # session_Arith, under HOL
    (lib,) = insert(f, f, 1, [session("Lib", parent_session="HOL-Library")])   # the layout
    (app,) = insert(f, f, 2, [session("App", parent_session="Arith")])         # the forest
    assert (lib.parent_session, app.parent_session) == ("HOL-Library", "Arith")
    # a session of the same call counts once built: before this one, not after
    p, q = insert(f, f, 3, [session("P"), session("Q", parent_session="P")])
    assert q.parent_session == "P"
    with pytest.raises(InvalidField) as e:
        insert(f, f, 5, [session("R", parent_session="T"), session("T")])
    assert (e.value.field, e.value.raw_ast_path) == ("parent_session", "constructs[0]")
    assert f.sub_nodes == [s, lib, app, p, q]
    # an amend: the node it replaces is leaving, for every construct of the
    # batch; a kept name is back for the constructs after the first
    with pytest.raises(InvalidField) as e:
        run(locked(f, edit.amend(app, [session("App2", parent_session="App")])))
    assert e.value.reason == "must name an existing session; `App` is not one"
    with pytest.raises(InvalidField) as e:
        run(locked(f, edit.amend(app, [session("App2", parent_session="Lib"),
                                       session("B", parent_session="App")])))
    assert e.value.raw_ast_path == "constructs[1]"
    app2, b = run(locked(f, edit.amend(app, [session("App", parent_session="Lib"),
                                             session("B", parent_session="App")])))
    assert (app2.parent_session, b.parent_session) == ("Lib", "App")
    assert app2.identity == app.identity
    assert f.sub_nodes == [s, lib, app2, b, p, q]
    inv(f)


def test_the_header_adds_the_imports_the_plugins_declare_where_no_forest_theory_is_imported():
    """SESSION_AND_THEORY §2, PLUGIN_SYSTEM §1: after the agent's imports,
    on a theory none of whose imports resolves to a theory of the forest,
    the declared theories; a theory importing a forest theory receives
    them through it; `recall`'s line shows the agent's alone."""
    f = Forest_Under_Test(imports=("Minilang_AoA.Minilang_AoA",))
    (s,) = insert(f, f, 0, [session("S", theory("A", "Main", "HOL-Library.Multiset"), theory("B", "S.A"),
                                    theory("C", "Minilang_AoA.Minilang_AoA"))])
    a, b, c = s.sub_nodes
    assert a.header() == 'theory "A"\n  imports "Main" "HOL-Library.Multiset" "Minilang_AoA.Minilang_AoA"\nbegin'
    assert b.header() == 'theory "B"\n  imports "S.A"\nbegin'
    assert c.header() == 'theory "C"\n  imports "Minilang_AoA.Minilang_AoA"\nbegin'      # written once
    out = io.StringIO()
    a.print_fields(0, out, M.RECALL, 0)
    assert out.getvalue() == "imports: Main HOL-Library.Multiset\n"
    assert Forest_Under_Test().imports == () and f.imports == ("Minilang_AoA.Minilang_AoA",)
