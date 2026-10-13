"""`compile.py` (COMPILATION.md §2, §5) on fake node classes and a real
working directory, without Isabelle: which trees are written and why not,
the files' and the ROOT's text, the directory after a compile, the report.
Run: python -m pytest test/test_compile.py
"""

import os
from pathlib import Path

import msgpack
import pytest
from Isabelle_RPC_Host.unicode import IsaTerm, ascii_of_unicode

import stand_ins
import test_model as tm
import test_session_theory as ts
from baselines import DOCS, fenced_blocks
from test_model import locked, run

import isabelle_theory_agent.model as M
from isabelle_theory_agent import compile as C, edit, invariants
from isabelle_theory_agent.exceptions import TAT_StartupError
from isabelle_theory_agent.model import Session
from isabelle_theory_agent.store import Forest_Store

table = ts.table                     # the fake state slot table and the fake wire, per test

SESSION_OF = {"Main": "HOL"}         # the fake Isabelle: the session of a theory outside the forest


class Fake_Theory(ts.Fake_Theory):
    """Records `import_sessions` as the real header's run does: the
    session each import belongs to."""
    async def _eval_beginning_opr(self):
        self.import_sessions = [item.split(".")[0] if "." in item
                                else SESSION_OF.get(item, self.session().name)
                                for item in self.imports]
        return await super()._eval_beginning_opr()


class Willing_Theory(Fake_Theory):
    """A class that widens `can_emit`: it writes whatever its statuses."""
    def can_emit(self): return True


class Lemma(tm.T):
    """A leaf whose failure carries the message of the document's example."""
    async def _eval_opr(self):
        status = await super()._eval_opr()
        if isinstance(status, M.CannotEvaluate):
            return M.CannotEvaluate((IsaTerm.from_isabelle(
                'Type unification failed: Clash of types "nat" and "bool"'),))
        return status


class Silent_Section(tm.Block):
    """A class's own refusal: it runs, and does not emit."""
    def can_emit(self): return False


KINDS = {"session": Session, "theory": Fake_Theory, "willing": Willing_Theory,
         "lemma": Lemma, "section": Silent_Section, "block": tm.Block}

theory, session = ts.theory, ts.session


def lemma(name, fail=False):
    return {"kind": "lemma", "name": name, "fail": fail}


def forest(directory, *sessions, kinds=KINDS):
    """A forest on `directory` as its working directory."""
    directory.mkdir(exist_ok=True)
    log = stand_ins.log()
    f = M.Forest(M.Conversation(tm.CONN, directory, log, stand_ins.ending()),
                 Forest_Store(":memory:", log), kinds)
    insert(f, f, 0, list(sessions), kinds)
    return f


def insert(f, parent, index, raws, kinds=KINDS):
    return run(locked(f, edit.insert(parent, index, raws, kinds)))


def listing(directory):
    return [(str(e.path), e.kind) for e in C.paths(directory)]


def sorting(directory):
    """The forest of COMPILATION.md §2's report: `Sorting`, `Merge` and
    `Late` are the written trees."""
    f = forest(directory, session(
        "Sorting",
        theory("Sorting"),
        theory("Merge", "Sorting", "HOL-Library.Multiset"),
        theory("Sum") | {"children": [lemma("sum_comm", fail=True)]},
        theory("Perm"),
        theory("Uses", "Sum"),
        theory("Odd") | {"children": [{"kind": "section", "name": "Old"}]},
        theory("Early", "Late"),
        theory("Late"),
        description="Sorting, verified.",
        options=[{"name": "quick_and_dirty", "value": "true"}, {"name": "document", "value": "false"}]))
    run(f.evaluate_to(None, True))
    perm = f.sub_nodes[0].sub_nodes[3]
    insert(f, perm, 0, [lemma("perm_length")])              # an edit left unevaluated
    return f


# --- the document's example ---------------------------------------------------

def test_the_report_and_the_root_of_compilation_md_section_2(tmp_path):
    directory = tmp_path / "work"
    f = sorting(directory)
    (directory / "Old").mkdir()
    (directory / "Old" / "Stale.thy").write_text("theory Stale imports Main begin end\n")
    root_example, report_example = fenced_blocks(DOCS / "COMPILATION.md", "2.")

    report = C.compile(f, [])
    assert C.report_lines(report) == report_example
    assert (directory / "ROOT").read_text() == ascii_of_unicode("\n".join(root_example) + "\n")
    assert "\\<open>Sorting, verified.\\<close>" in (directory / "ROOT").read_text()

    by_name = {tree.name: reason for tree, reason in report.trees}
    assert [tree.name for tree, _ in report.trees] == [
        "Sorting", "Merge", "Sum", "Perm", "Uses", "Odd", "Early", "Late"]      # tree order
    assert by_name["Sorting"] is by_name["Merge"] is by_name["Late"] is None
    trees = {t.name: t for t in f.trees()}
    assert by_name["Sum"] == C.Does_Not_Emit(trees["Sum"].sub_nodes[0])
    assert by_name["Perm"] == C.Does_Not_Emit(trees["Perm"].sub_nodes[0])
    assert by_name["Uses"] == C.Import_Not_Written(trees["Sum"])
    assert by_name["Odd"] == C.Does_Not_Emit(trees["Odd"].sub_nodes[0])
    assert by_name["Early"] == C.Order_Constraint(trees["Late"])
    # the directory: the written trees' files, the ROOT, nothing else; a
    # tree imported by an unwritten one is written all the same
    assert listing(directory) == [
        ("ROOT", "file"), ("Sorting/Late.thy", "file"), ("Sorting/Merge.thy", "file"),
        ("Sorting/Sorting.thy", "file"), ("Sorting", "folder")]
    assert (directory / "Sorting" / "Merge.thy").read_text() == (
        'theory Merge\n  imports "Sorting" "HOL-Library.Multiset"\nbegin\nend\n')
    assert report.removed == (C.Entry(C.Path("Old/Stale.thy"), "file"), C.Entry(C.Path("Old"), "folder"))
    # a second compile changes nothing and removes nothing
    again = C.compile(f, [])
    assert again.removed == () and C.report_lines(again) == report_example[:-2]


def test_a_files_text_is_converted_once_and_ends_every_line(tmp_path):
    f = forest(tmp_path / "work", session("S", theory("A") | {"children": [
        lemma("x"), {"kind": "block", "name": "B", "children": [lemma("y")]}]}))
    run(f.evaluate_to(None, False))
    rendering = C.render(f)
    (text,) = rendering.files.values()
    assert list(rendering.files) == [C.Path("S/A.thy")]
    assert text == ('theory A\n  imports "Main"\nbegin\n'
                    'text \\<open>x\\<close>\n'
                    '\n'
                    'section \\<open>B\\<close>\n'
                    'text \\<open>y\\<close>\n'
                    'text \\<open>end of B\\<close>\n'
                    'end\n')
    assert "‹" not in text and ascii_of_unicode(text) == text           # idempotent
    C.compile(f, [])
    assert (tmp_path / "work" / "S" / "A.thy").read_text() == text


def test_the_store_mirror_catches_what_a_compile_could_not_read(tmp_path):
    """COMPILATION.md §3: on a loaded forest every instant status is
    `not_evaluated`, and a field that was not stored is gone; a class whose
    emission reads either answers differently there, and the package's
    helper says so at once — in `can_emit`, in a file's text, in the ROOT,
    in the report."""
    class Refuses_By_An_Instant_Status(Lemma):
        def can_emit(self): return all(isinstance(s, M.Ready) for s in self.evaluation_statuses())
    class Emits_An_Instant_Status(Lemma):
        def emit(self, indent, out):
            out.write(f"text \\<open>{self.name}, finished: {self.is_finished()}\\<close>\n")
            return indent
    class Stores_No_Import_Sessions(Fake_Theory):
        def to_store(self, rows):
            rows.put("name", self.name)
            rows.put("imports", self.imports)
    class Stores_Another_Name(Lemma):
        def to_store(self, rows):
            super().to_store(rows)
            rows.put("name", self.name + "_stored")
    kinds = KINDS | {"refusing": Refuses_By_An_Instant_Status, "emitting": Emits_An_Instant_Status,
                     "forgetful": Stores_No_Import_Sessions, "renamed": Stores_Another_Name}

    sound = sorting(tmp_path / "sound")
    invariants.assert_store_mirrors(sound, KINDS)

    def mirrored(case, tree, message, ignore_error=False):
        f = forest(tmp_path / case, session("S", tree), kinds=kinds)
        run(f.evaluate_to(None, ignore_error))
        with pytest.raises(AssertionError, match=message):
            invariants.assert_store_mirrors(f, kinds)
        return f

    f = mirrored("refusing", theory("A") | {"children": [{"kind": "refusing", "name": "x"}]},
                 "can_emit is True, and False once loaded")
    assert all(n.can_emit() for n in f.trees()[0]._tree_order())       # in memory, it writes
    mirrored("emitting", theory("A") | {"children": [{"kind": "emitting", "name": "x"}]},
             "S/A.thy: the loaded forest writes another text")
    mirrored("forgetful", theory("A", "HOL-Library.Multiset", kind="forgetful"),
             "ROOT: the loaded forest writes another text")
    mirrored("renamed", theory("A") | {"children": [{"kind": "renamed", "name": "x", "fail": True}]},
             "the report: ", ignore_error=True)


# --- which trees, and why not --------------------------------------------------

def test_an_import_cycle_writes_no_member(tmp_path):
    """A tree reached again while its own decision is being made lies on
    an import cycle and is not written, whatever its nodes answer; the
    chain of reasons ends at the member that breaks the order
    constraint."""
    f = forest(tmp_path / "work", session(
        "S", theory("A", "B", kind="willing"), theory("B", "A", kind="willing"),
        theory("C", "B", kind="willing"), theory("Self", "Self", kind="willing"),
        theory("Free", kind="willing")))
    a, b, c, itself, free = f.trees()
    report = C.compile(f, [])
    assert dict(report.trees) == {a: C.Order_Constraint(b), b: C.Import_Not_Written(a),
                                  c: C.Import_Not_Written(b), itself: C.Order_Constraint(itself),
                                  free: None}
    assert C.report_lines(report) == [
        "S/A.thy not written: it imports S.B, which is placed after it",
        "S/B.thy not written: it imports S.A, which is not written",
        "S/C.thy not written: it imports S.B, which is not written",
        "S/Self.thy not written: it imports itself",
        "S/Free.thy written",
        "ROOT written"]


def test_the_reasons_in_their_order(tmp_path):
    """COMPILATION.md §2's four reasons, first that holds: an unwritten
    import placed before; a stored failure, or a class's refusal; the
    order constraint; a node not evaluated."""
    f = forest(tmp_path / "work", session(
        "S",
        theory("Bad") | {"children": [lemma("broken", fail=True)]},
        theory("Both", "Bad", "After") | {"children": [lemma("late")]},
        theory("Quiet") | {"children": [{"kind": "section", "name": "Old"}]},
        theory("Failing_Importer", "Quiet") | {"children": [lemma("broken1", fail=True)]},
        theory("Failed", "After") | {"children": [lemma("broken2", fail=True), lemma("unreached")]},
        theory("Refusing", "After") | {"children": [{"kind": "section", "name": "Older"}]},
        theory("Ordered", "After"),
        theory("After")))
    bad, both, quiet, failing_importer, failed, refusing, ordered, after = f.trees()
    run(f.evaluate_to(None, True))
    # `Failed` and `Refusing` ran before a move put `After` behind them:
    # what they stored keeps its line
    run(locked(f, edit.move(after, f.sub_nodes[0], 0)))
    run(f.evaluate_to(None, True))
    run(locked(f, edit.move(after, f.sub_nodes[0], 7)))
    reasons = dict(C.render(f).trees)
    assert reasons[bad] == C.Does_Not_Emit(bad.sub_nodes[0])
    assert reasons[both] == C.Import_Not_Written(bad)                   # 1, before its own state
    assert reasons[failing_importer] == C.Import_Not_Written(quiet)     # 1, before its stored failure
    assert reasons[failed] == C.Does_Not_Emit(failed.sub_nodes[0])      # 2, before the order constraint
    assert reasons[refusing] == C.Does_Not_Emit(refusing.sub_nodes[0])  # 2 is a class's refusal too
    assert reasons[ordered] is None            # evaluated before the move: written, the import after it too
    assert reasons[after] is None
    # an order violation on a tree never evaluated: 3, before 4
    (fresh,) = insert(f, f.sub_nodes[0], 3, [theory("Fresh", "After") | {"children": [lemma("z")]}])
    assert dict(C.render(f).trees)[fresh] == C.Order_Constraint(after)
    # the same tree placed last: 4, at the first node not evaluated — its
    # `Theory` node, met at its beginning, before its children
    run(locked(f, edit.move(fresh, f.sub_nodes[0], 8)))
    assert dict(C.render(f).trees)[fresh] == C.Does_Not_Emit(fresh)


def test_which_tree_a_reason_names(tmp_path):
    """COMPILATION.md §2: rule 1 names the first unwritten import placed
    before the tree, in the order of its `imports`; rule 3 the first
    misplaced import that is not written, else the first."""
    f = forest(tmp_path / "work", session(
        "S",
        theory("P") | {"children": [lemma("p", fail=True)]},
        theory("Q") | {"children": [lemma("q", fail=True)]},
        theory("Importer", "Q", "P"),
        theory("Early", "W1", "U"),
        theory("Earlier", "W2", "W1"),
        theory("W1"), theory("W2"),
        theory("U") | {"children": [lemma("u", fail=True)]}))
    p, q, importer, early, earlier, w1, w2, u = f.trees()
    run(f.evaluate_to(None, True))
    report = C.Compile_Report(C.render(f).trees, ())
    reasons = dict(report.trees)
    assert reasons[w1] is reasons[w2] is None
    assert reasons[importer] == C.Import_Not_Written(q)         # the first of its `imports`, not of the trees
    assert reasons[early] == C.Order_Constraint(u)              # the first that is not written
    assert reasons[earlier] == C.Order_Constraint(w2)           # all written: the first of its `imports`
    assert C.report_lines(report)[4:9] == [
        "S/Importer.thy not written: it imports S.Q, which is not written",
        "S/Early.thy not written: it imports S.U, which is placed after it",
        "S/Earlier.thy not written: it imports S.W2, which is placed after it",
        "S/W1.thy written", "S/W2.thy written"]


def test_a_nesting_node_is_met_at_its_beginning_when_that_did_not_pass(tmp_path):
    """The scan runs in the walk's order of operations: a nesting node
    whose beginning failed is named before its children, which never ran;
    one that passed is met at its ending, after them."""
    f = forest(tmp_path / "work", session(
        "S",
        theory("Opening") | {"children": [
            {"kind": "block", "name": "B", "fail": True, "children": [lemma("inside")]}]},
        theory("Closing") | {"children": [
            {"kind": "block", "name": "E", "children": [lemma("inner", fail=True)]}]}))
    opening, closing = f.trees()
    run(f.evaluate_to(None, True))
    reasons = dict(C.render(f).trees)
    assert reasons[opening] == C.Does_Not_Emit(opening.sub_nodes[0])    # the block, not `inside`
    assert reasons[closing] == C.Does_Not_Emit(closing.sub_nodes[0].sub_nodes[0])
    assert C.report_lines(C.Compile_Report(C.render(f).trees, ()))[0] == \
        "S/Opening.thy not written: block_B failed"


# --- the ROOT -------------------------------------------------------------------

def test_the_roots_clauses_and_quoting(tmp_path):
    f = forest(
        tmp_path / "work",
        session("HOL-Extras", theory("A", "Main", "HOL-Library.Multiset", "HOL-Algebra.Group",
                                     "HOL-Library.FSet"),
                theory("Own", "A"),
                theory("Failing", "ZF.ZF") | {"children": [lemma("broken", fail=True)]},
                theory("Unrun", "FOL.FOL"),
                description='A ‹quoted› word \\<open>and\\<close> a second line\nhere',
                options=[{"name": "document", "value": '"pdf"'},
                         {"name": "document_tags", "value": 'a"b\\c'}]),
        session("Bare"),
        session("Uses", theory("B", "HOL-Extras.A"), parent_session="HOL-Library"))
    extras, bare, uses = f.sub_nodes
    a, own, failing, unrun = extras.sub_nodes
    run(own.evaluate_to(None, False))
    run(failing.evaluate_to(None, True))
    run(uses.evaluate_to(None, False))
    # as they arrive: neither sorted nor each once, the parent and the session itself among them
    assert a.import_sessions == ["HOL", "HOL-Library", "HOL-Algebra", "HOL-Library"]
    assert (own.import_sessions, failing.import_sessions, unrun.import_sessions) == \
        (["HOL-Extras"], ["ZF"], [])
    C.compile(f, [])
    assert (tmp_path / "work" / "ROOT").read_text() == ascii_of_unicode(
        'session "HOL-Extras" in "HOL-Extras" = "HOL" +\n'
        '  description ‹A "quoted" word "and" a second line\nhere›\n'
        '  options ["document" = "pdf", "document_tags" = "a\\"b\\\\c"]\n'
        '  sessions\n'                       # of the written trees: sorted, each once, less the
        '    "HOL-Algebra"\n'                # parent and the session itself
        '    "HOL-Library"\n'
        '  theories\n'
        '    "A"\n'
        '    "Own"\n'
        '\n'
        'session "Bare" in "Bare" = "HOL" +\n'     # no description, no options, no tree: the entry stays
        '\n'
        'session "Uses" in "Uses" = "HOL-Library" +\n'
        '  sessions\n'
        '    "HOL-Extras"\n'
        '  theories\n'
        '    "B"\n')
    assert (tmp_path / "work" / "Bare").is_dir()             # and so does its folder, which compile makes


def test_the_empty_forest_compiles_to_a_root_with_no_entry(tmp_path):
    f = forest(tmp_path / "work")
    report = C.compile(f, [])
    assert listing(tmp_path / "work") == [("ROOT", "file")]
    assert (tmp_path / "work" / "ROOT").read_text() == "" and C.report_lines(report) == ["ROOT written"]


# --- the directory ----------------------------------------------------------------

def test_the_path_listing(tmp_path):
    directory = tmp_path / "work"
    for folder in ("a/b", ".git/objects", "c/.cache", "empty"):
        (directory / folder).mkdir(parents=True)
    for file in ("a/b/x.thy", "a/y", ".git/z.thy", "c/.cache/w", ".hidden", "top.thy"):
        (directory / file).write_text("")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "o.thy").write_text("")
    (directory / "a" / "link").symlink_to(outside)
    (directory / "dangling.thy").symlink_to(tmp_path / "nowhere")
    assert listing(directory) == [
        (".hidden", "file"),                         # a file may begin with a dot; a folder is skipped
        ("a/b/x.thy", "file"), ("a/b", "folder"),    # a folder after what it holds
        ("a/link", "link"),                          # yielded, not entered
        ("a/y", "file"), ("a", "folder"),
        ("c", "folder"),                             # its dot-folder neither yielded nor entered
        ("dangling.thy", "link"), ("empty", "folder"), ("top.thy", "file")]


def test_the_directory_after_a_compile(tmp_path):
    """Every `.thy` under the working directory and the ROOT are TAT's;
    nothing a compile does enters a dot-folder or follows a link; the
    empty folders compile did not make go, a `Session`'s stays."""
    directory, outside = tmp_path / "work", tmp_path / "outside"
    f = forest(directory, session("S", theory("A")), session("Empty"))
    run(f.evaluate_to(None, False))
    outside.mkdir()
    (outside / "kept.thy").write_text("outside")
    # `notes/S`: a folder is a `Session`'s by what it is, not by its last name
    for folder in ("S/deep/er", ".git", "notes/S", "hollow/inner", "keeps/.dot"):
        (directory / folder).mkdir(parents=True)
    for file in ("S/deep/er/old.thy", ".git/config.thy", "notes/readme.txt", "S/A.proof-store",
                 "stray.thy", "keeps/.dot/x.thy"):
        (directory / file).write_text("stale")
    (directory / "ROOT").write_text("stale")
    (directory / "linked").symlink_to(outside)
    (directory / "link.thy").symlink_to(outside / "kept.thy")
    report = C.compile(f, [])
    assert listing(directory) == [
        ("Empty", "folder"), ("ROOT", "file"),
        ("S/A.proof-store", "file"), ("S/A.thy", "file"), ("S", "folder"),
        ("keeps", "folder"),                         # not empty: it holds a dot-folder
        ("linked", "link"), ("notes/readme.txt", "file"), ("notes", "folder")]
    assert (directory / ".git" / "config.thy").read_text() == "stale"
    assert (directory / "keeps" / ".dot" / "x.thy").read_text() == "stale"
    assert (outside / "kept.thy").read_text() == "outside"          # the link went, not its target
    assert [str(e.path) for e in report.removed] == [
        "S/deep/er/old.thy", "S/deep/er", "S/deep", "hollow/inner", "hollow", "link.thy", "notes/S",
        "stray.thy"]
    assert C.report_lines(report)[-8:] == [
        "removed S/deep/er/old.thy", "removed S/deep/er/", "removed S/deep/", "removed hollow/inner/",
        "removed hollow/", "removed link.thy", "removed notes/S/", "removed stray.thy"]


def test_a_removed_name_that_is_not_utf_8_is_spelled_so_that_the_report_travels(tmp_path):
    """A name the file system holds that is not valid UTF-8 arrives with a
    lone surrogate; its line carries the escape the log writes (LOGGING.md
    §5), and the RPC host can pack the answer."""
    directory = tmp_path / "work"
    f = forest(directory)
    os.mkdir(os.fsencode(directory) + b"/Old-caf\xe9")
    lines = C.report_lines(C.compile(f, []))
    assert lines == ["ROOT written", "removed Old-caf\\udce9/"]
    msgpack.packb((True, lines))


def test_what_is_refused_before_anything_is_removed(tmp_path):
    """COMPILATION.md §2, §5: a `Session` folder's path holding anything
    but a directory, and a folder at a path the compile will create — a
    tree's file, the ROOT, the ROOT's sibling — each with §7's sentence,
    the directory as the previous compile left it."""
    _, (a_link, not_a_directory, a_folder), _ = fenced_blocks(DOCS / "COMPILATION.md", "7.")
    def link(p): p.symlink_to(tmp_path)
    def file(p): p.write_text("a file")
    def folder(p): p.mkdir(parents=True)
    for case, make, path, sentence in (
            ("link", link, "Taken", a_link),
            ("file", file, "Taken", not_a_directory),
            ("tree", folder, "Good/A.thy", a_folder),
            ("root", folder, "ROOT", a_folder),
            ("sibling", folder, "ROOT.new.thy", a_folder)):
        directory = tmp_path / case
        f = forest(directory, session("Good", theory("A")), session("Taken"))
        run(f.evaluate_to(None, False))
        if path != "ROOT":
            (directory / "ROOT").write_text("the previous compile's")
        (directory / "stray.thy").write_text("stale")
        make(directory / path)
        before = listing(directory)
        with pytest.raises(TAT_StartupError) as e:
            C.compile(f, [])
        assert str(e.value) == (sentence.replace("<working directory>", str(directory))
                                .replace("<Session name>", "Taken").replace("<path>", path))
        assert listing(directory) == before                 # the directory as the previous compile left it
        if path != "ROOT":
            assert (directory / "ROOT").read_text() == "the previous compile's"


def test_making_a_session_folder(tmp_path):
    """The function the compile and a theory's beginning share: it makes
    the folder when absent, and answers the reason when it cannot."""
    directory = tmp_path / "work"
    directory.mkdir()
    assert M.make_session_folder(directory, Path("S")) is None and (directory / "S").is_dir()
    assert M.make_session_folder(directory, Path("S")) is None      # a directory already
    (directory / "File").write_text("")
    (directory / "Link").symlink_to(directory / "S")
    assert M.make_session_folder(directory, Path("File")) == \
        "File/ is not a directory; a session's folder must be a directory or absent"
    assert M.make_session_folder(directory, Path("Link")) == \
        "Link/ is a symbolic link; a session's folder must be a directory or absent"


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes anywhere")
def test_a_session_folder_the_system_will_not_make(tmp_path):
    directory = tmp_path / "work"
    directory.mkdir(mode=0o500)
    try:
        assert M.make_session_folder(directory, Path("New")) == \
            "New/ cannot be made: Permission denied"
    finally:
        os.chmod(directory, 0o700)


def test_the_root_goes_through_a_sibling_the_next_compile_removes(tmp_path, monkeypatch):
    """COMPILATION.md §5: the ROOT is written to a temporary sibling with
    the `.thy` suffix, created afresh, and moved into place — so a compile
    that fails at any point before the move leaves no ROOT, and what it
    left of the sibling goes with the next compile's `.thy` removal."""
    directory = tmp_path / "work"
    f = forest(directory, session("S", theory("A")))
    run(f.evaluate_to(None, False))

    def killed(src, dst):
        raise KeyboardInterrupt("killed before the move")
    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", killed)
        with pytest.raises(KeyboardInterrupt):
            C.compile(f, [])
    assert not (directory / "ROOT").exists()
    assert ("ROOT.new.thy", "file") in listing(directory)           # whole, and not the ROOT
    report = C.compile(f, [])
    assert C.report_lines(report) == ["S/A.thy written", "ROOT written", "removed ROOT.new.thy"]

    create = C._create
    def cut_off(path, text):
        if path.name.startswith("ROOT"):
            create(path, text[:9])
            raise KeyboardInterrupt("killed in the middle of the ROOT's text")
        create(path, text)
    with monkeypatch.context() as patch:
        patch.setattr(C, "_create", cut_off)
        with pytest.raises(KeyboardInterrupt):
            C.compile(f, [])
    assert not (directory / "ROOT").exists()            # Isabelle would read a ROOT cut off as whole

    target = tmp_path / "target"
    target.write_text("untouched")
    def plants_a_link(forest):
        (directory / "ROOT.new.thy").symlink_to(target)
    with pytest.raises(FileExistsError):
        C.compile(f, [plants_a_link])
    assert target.read_text() == "untouched" and not (directory / "ROOT").exists()


def test_every_file_is_created_afresh(tmp_path):
    """A compile writes through nothing: a path that still holds something
    when a file is created — here one a hook planted — is a refusal, and
    the compile ends without a ROOT, which Isabelle refuses."""
    directory = tmp_path / "work"
    f = forest(directory, session("S", theory("A")))
    run(f.evaluate_to(None, False))
    C.compile(f, [])
    def plants_a_folder(forest):
        (directory / "S" / "A.thy").unlink()
        (directory / "S" / "A.thy").mkdir()
    with pytest.raises(FileExistsError):
        C.compile(f, [plants_a_folder, lambda forest: C._create(directory / "S" / "A.thy", "")])
    assert not (directory / "ROOT").exists()
    (directory / "S" / "A.thy").rmdir()
    target = tmp_path / "target"
    target.write_text("untouched")
    (directory / "planted").symlink_to(target)
    with pytest.raises(FileExistsError):
        C._create(directory / "planted", "written through")
    assert target.read_text() == "untouched"


def test_a_hook_runs_after_the_files_and_before_the_empty_folders_and_the_root(tmp_path):
    directory = tmp_path / "work"
    f = forest(directory, session("S", theory("A")))
    run(f.evaluate_to(None, False))
    (directory / "hollow").mkdir()
    (directory / "S").mkdir()
    (directory / "S" / "Gone.proof-store").write_text("of a theory that is gone")
    seen = []
    def first(forest):
        seen.append(("first", forest is f, (directory / "S" / "A.thy").exists(),
                     (directory / "ROOT").exists(), (directory / "hollow").exists()))
        (directory / "S" / "A.proof-store.lock").write_text("")
        (directory / "S" / "Gone.proof-store").unlink()
    def second(forest):
        seen.append(("second", (directory / "S" / "A.proof-store.lock").exists()))
        (directory / "S" / "A.proof-store.lock").unlink()
    report = C.compile(f, [first, second])
    assert seen == [("first", True, True, False, True), ("second", True)]     # in the order given
    assert listing(directory) == [("ROOT", "file"), ("S/A.thy", "file"), ("S", "folder")]
    # `removed` is read off the directory: what a hook removed is in it, unasked
    assert report.removed == (C.Entry(Path("S/Gone.proof-store"), "file"),
                              C.Entry(Path("hollow"), "folder"))
    assert C.report_lines(report)[-2:] == ["removed S/Gone.proof-store", "removed hollow/"]
    def broken(forest):
        raise ZeroDivisionError("the plugin's bug")
    with pytest.raises(ZeroDivisionError):
        C.compile(f, [broken])
    assert not (directory / "ROOT").exists()                # the compile did not complete


def test_a_theorys_description_is_a_text_block_before_the_header(tmp_path):
    """SESSION_AND_THEORY §2: a non-empty `description` is emitted as a
    `text ‹…›` block before the `theory` line, as written and with no
    period added, `‹`, `›`, `\\<open>` and `\\<close>` in it replaced by
    `"`; nothing for an empty one."""
    f = forest(tmp_path / "work", session("S", theory("A") | {
        "description": 'A ‹quoted› word \\<open>and\\<close> a second line\nhere',
        "children": [lemma("x")]}, theory("B")))
    run(f.evaluate_to(None, False))
    files = C.render(f).files
    assert files[C.Path("S/A.thy")] == (
        'text \\<open>A "quoted" word "and" a second line\nhere\\<close>\n'
        'theory A\n  imports "Main"\nbegin\n'
        'text \\<open>x\\<close>\n'
        'end\n')
    assert files[C.Path("S/B.thy")].startswith("theory B\n")
