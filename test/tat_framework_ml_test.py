"""The Python half of test/Test_TAT_Framework.thy.

`TAT_Framework.start' "TAT_test.drive" \\<^theory>` on the ML side calls the
procedure below, which drives the conversation's state slot table and theory
pipeline through the framework's callbacks and the callbacks the test theory
registered.  An assertion failure travels back as the error of the ML call,
so the theory fails to evaluate exactly when the test fails.

`TAT_test.make` stores one of two distinguishable states — `top=True` a
toplevel state, `top=False` a theory state — and `TAT_test.is_toplevel`
reads the stored state's discriminator back, so a copy that fabricated a
state instead of mirroring the source would be caught.

The `TAT_test.*` probes of the framework's primitives are called on the wire
directly, so that an exception escaping one is seen unconverted; only
`TAT_test.operation` goes through `isabelle_driver.call`, since the rule it
pins is EXCEPTIONS.md §1's — an escaping exception is a bug.
"""

import os
from pathlib import Path

from Isabelle_RPC_Host import Connection, IsabelleError, isabelle_remote_procedure

from isabelle_theory_agent import edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import DuplicateTheoryShortName, TAT_IsabelleError
from isabelle_theory_agent.model import READY, CannotEvaluate, Isar_State_Slot, Session, Theory
from isabelle_theory_agent.store import Forest_Store
from routing_forest import Routing_Forest

HERE = os.path.dirname(os.path.abspath(__file__))


@isabelle_remote_procedure("TAT_test.drive")
async def drive(packages: list[str], connection: Connection) -> None:
    # the registrations' python_packages, collected and deduplicated
    # (MODULE_STRUCTURE §2.6): two of them name this module, the rest none
    assert packages == ["tat_framework_ml_test"], packages

    a = Isar_State_Slot.assign(connection)
    b = Isar_State_Slot.assign(connection)
    c = Isar_State_Slot.assign(connection)

    async def make(slot: Isar_State_Slot, top: bool) -> None:
        await connection.callback("TAT_test.make", (slot.to_msgpack(), top))

    async def is_toplevel(slot: Isar_State_Slot) -> bool:
        return await connection.callback("TAT_test.is_toplevel", slot.to_msgpack())

    # a fresh slot holds nothing
    assert not await a.is_initialized()

    # a node-class callback writes it through the env's slot_unpacker,
    # and the stored value comes back distinguishable
    await make(a, False)
    assert await a.is_initialized()
    assert await is_toplevel(a) is False
    await make(b, True)
    assert await is_toplevel(b) is True

    # copy: the target mirrors the source, value included
    await a.copy_to(b)
    assert await b.is_initialized()
    assert await is_toplevel(b) is False

    # get on an empty slot is a bug (EXCEPTIONS.md §1): it escapes the callback
    # unconverted, and this raw probe sees it as the RPC library's exception
    try:
        await is_toplevel(c)
        raise AssertionError("get on an empty slot did not raise")
    except IsabelleError as e:
        assert "holds no state" in str(e), str(e)

    # copy from an empty slot: the target mirrors the absence
    await c.copy_to(b)
    assert not await b.is_initialized()

    # `put NONE` through the slot handle deletes
    await make(b, True)
    assert await b.is_initialized()
    await connection.callback("TAT_test.clear", b.to_msgpack())
    assert not await b.is_initialized()

    # single delete; deleting an absent name is not an error
    await a.delete()
    assert not await a.is_initialized()
    await a.delete()

    # batched delete removes every present name in one round trip
    await make(a, True)
    await make(b, False)
    assert await a.is_initialized() and await b.is_initialized()
    await isabelle_driver.state_delete(connection, [a.name, b.name, c.name])
    for s in (a, b, c):
        assert not await s.is_initialized()

    # --- the theory pipeline (MODULE_STRUCTURE §2.2-§2.4) ---

    def slot() -> Isar_State_Slot:
        return Isar_State_Slot.assign(connection)

    async def begin(sl: Isar_State_Slot, header_src: str) -> None:
        await connection.callback(
            "TAT_test.begin", (sl.to_msgpack(), ("TAT_TEST", HERE, header_src)))

    async def begin_fails(header_src: str, expect: str | None = None) -> None:
        sl = slot()
        try:
            await begin(sl, header_src)
            raise AssertionError(f"begin did not fail: {header_src}")
        except IsabelleError as e:
            if expect is not None:
                assert expect in str(e), str(e)

    async def run(src: Isar_State_Slot, dst: Isar_State_Slot, text: str) -> list:
        return await connection.callback(
            "TAT_test.run", (src.to_msgpack(), (dst.to_msgpack(), text)))

    async def end(sl: Isar_State_Slot) -> None:
        await connection.callback("TAT_test.end", sl.to_msgpack())

    async def short_name_holder(name: str) -> str | None:
        return await isabelle_driver.check_new_theory_short_name(connection, name)

    def errors(recs: list) -> list:
        return [e for _, errs, _ in recs for e in errs]

    def texts(rec: list) -> list[str]:
        return [t for _, t in rec[2]]

    # the base-heap half of the short-name check (§2.3)
    assert await short_name_holder("List") == "HOL.List"
    assert await short_name_holder("TAT_Test_A_Fresh_Name") is None

    # begin a theory whose one import is in the base heap
    t = slot()
    await begin(t, "theory TAT_Test_A imports Main begin")
    assert await t.is_initialized()

    # five commands (`lemma` and `by` are separate spans; `datatype` needs a
    # keyword contributed by an imported theory): records in order, the
    # sources a verbatim partition of the text, output routed to exactly its
    # own command, and the proof's result block captured (it prints through
    # the urgent channel)
    text_a = (
        'definition tat_test_x :: nat where "tat_test_x = 41"\n'
        'ML \\<open>writeln "tat-hello"; warning "tat-warn"\\<close>\n'
        'datatype tat_test_t = TatA | TatB\n'
        'lemma tat_test_l: "tat_test_x = 41" by (simp add: tat_test_x_def)')
    recs = await run(t, t, text_a)
    assert len(recs) == 5, recs
    assert not errors(recs), recs
    # byte-exact sources pin both ends of every slice (the whitespace
    # between commands forms ignored spans, which carry no record)
    assert [rec[0] for rec in recs] == [
        'definition tat_test_x :: nat where "tat_test_x = 41"',
        'ML \\<open>writeln "tat-hello"; warning "tat-warn"\\<close>',
        'datatype tat_test_t = TatA | TatB',
        'lemma tat_test_l: "tat_test_x = 41"',
        'by (simp add: tat_test_x_def)',
    ], recs
    assert ["writeln", "tat-hello"] in recs[1][2], recs[1]
    assert ["warning", "tat-warn"] in recs[1][2], recs[1]
    for rec in recs:
        if rec is not recs[1]:
            assert not any("tat-hello" in t or "tat-warn" in t for t in texts(rec)), recs
    assert any("tat_test_l" in t for t in texts(recs[4])), recs[4]

    # all five output kinds are constructed and routed (a dropped channel
    # would discard the text: this server's fallbacks are no-ops)
    recs = await run(
        t, t,
        'ML \\<open>Output.information "tat-info"; tracing "tat-trace"; '
        'legacy_feature "tat-legacy"\\<close>')
    assert len(recs) == 1 and not errors(recs), recs
    assert ["information", "tat-info"] in recs[0][2], recs
    assert ["tracing", "tat-trace"] in recs[0][2], recs
    assert any(k == "legacy" and "tat-legacy" in txt for k, txt in recs[0][2]), recs

    # `sorry` passes (quick_and_dirty is on in this server, so this alone
    # does not isolate the interactive flag; it still pins that a sorry
    # span runs)
    s = slot()
    await t.copy_to(s)
    recs = await run(s, s, 'lemma tat_test_sorry: "False" sorry')
    assert len(recs) == 2 and not errors(recs), recs

    # with quick_and_dirty off, `sorry` still passes: the interactive flag
    # of Toplevel.command_errors is what admits it
    await t.copy_to(s)
    recs = await run(
        s, s,
        'declare [[quick_and_dirty = false]]\n'
        'lemma tat_test_sorry_int: "False" sorry')
    assert len(recs) == 3 and not errors(recs), recs

    # empty, whitespace-only and comment-only text (both comment forms): no
    # records, and the state passes through into the target slot unchanged
    for text in ("", "   \n", "(* just a comment *)",
                 "\\<comment> \\<open>a marked comment\\<close>"):
        dst = slot()
        recs = await run(s, dst, text)
        assert recs == [], (text, recs)
        assert await dst.is_initialized()
        assert await is_toplevel(dst) == await is_toplevel(s)
        await dst.delete()
    await s.delete()

    # a failing command: its record is the last, the run stops, and the
    # pre-populated target slot is really deleted -- the `put NONE` of a
    # stateless outcome
    f = slot()
    await t.copy_to(f)
    assert await f.is_initialized()
    recs = await run(
        t, f,
        'lemma tat_test_bad: "(1::nat) = 2" by simp\n'
        'ML \\<open>writeln "not reached"\\<close>')
    assert len(recs) == 2, recs
    assert recs[1][1], recs
    assert not await f.is_initialized()

    # a failed fork fails the command: its error lands in the record and
    # the committed state is withheld; a succeeding fork keeps the state
    g = slot()
    await t.copy_to(g)
    recs = await run(
        t, g,
        'ML \\<open>ignore (Execution.fork {name = "tat_test_fork", '
        'pos = Position.thread_data (), pri = 0} '
        '(fn () => error "tat-fork-boom"))\\<close>')
    assert len(recs) == 1, recs
    assert any("tat-fork-boom" in e for e in recs[0][1]), recs
    assert not await g.is_initialized()
    await t.copy_to(g)
    recs = await run(
        t, g,
        'ML \\<open>ignore (Execution.fork {name = "tat_test_fork_ok", '
        'pos = Position.thread_data (), pri = 0} (fn () => ()))\\<close>')
    assert len(recs) == 1 and not errors(recs), recs
    assert await g.is_initialized()
    await g.delete()

    # `end` and the theory table: a second tree's import resolves to the
    # first tree through the conversation's own table (EVALUATOR_DESIGN §2)
    recs = await run(t, t, "end")
    assert len(recs) == 1 and not errors(recs), recs
    await end(t)
    u = slot()
    await begin(u, "theory TAT_Test_B imports TAT_Test_A begin")
    recs = await run(u, u, 'lemma "tat_test_x = 41" by (simp add: tat_test_x_def)')
    assert not errors(recs), recs

    # re-evaluation overwrites the theory table entry (§2.2), and a fresh
    # importer sees the second generation
    t2 = slot()
    await begin(t2, "theory TAT_Test_A imports Main begin")
    recs = await run(
        t2, t2, 'definition tat_test_x2 :: nat where "tat_test_x2 = 42"\nend')
    assert not errors(recs), recs
    await end(t2)
    d = slot()
    await begin(d, "theory TAT_Test_D imports TAT_Test_A begin")
    recs = await run(d, d, 'lemma "tat_test_x2 = 42" by (simp add: tat_test_x2_def)')
    assert not errors(recs), recs

    # output isolation under concurrency: two run_commands in two futures,
    # each run's messages land in its own records only
    pa, pb = slot(), slot()
    await u.copy_to(pa)
    await u.copy_to(pb)
    ra, rb = await connection.callback(
        "TAT_test.run_parallel",
        (pa.to_msgpack(), (pb.to_msgpack(), (
            'ML \\<open>writeln "iso-a1"\\<close>\n'
            'lemma iso_a: "(2::nat) = 2" by simp\n'
            'ML \\<open>writeln "iso-a2"\\<close>',
            'ML \\<open>writeln "iso-b1"\\<close>\n'
            'lemma iso_b: "(3::nat) = 3" by simp\n'
            'ML \\<open>writeln "iso-b2"\\<close>'))))
    flat_a = [t for rec in ra for t in texts(rec)]
    flat_b = [t for rec in rb for t in texts(rec)]
    assert any("iso-a1" in t for t in flat_a) and any("iso-a2" in t for t in flat_a), ra
    assert any("iso-b1" in t for t in flat_b) and any("iso-b2" in t for t in flat_b), rb
    assert not any("iso-b" in t for t in flat_a), (ra, rb)
    assert not any("iso-a" in t for t in flat_b), (ra, rb)

    # an import neither evaluated nor in the heap loads from source --
    # TAT_Lib_Helper.thy next to this file, TAT_Lib_Rel.thy by a
    # slash-relative path under the master_dir.  On a warm server these are
    # already in Thy_Info and the load arm would silently be skipped, so
    # fail loudly instead.
    for name in ("TAT_Lib_Helper", "TAT_Lib_Rel"):
        holder = await short_name_holder(name)
        assert holder is None, (
            f"stale REPL server: {holder} already loaded -- restart the server")
    v = slot()
    await begin(v, 'theory TAT_Test_C imports TAT_Lib_Helper "lib/TAT_Lib_Rel" begin')
    recs = await run(
        v, v,
        'lemma "tat_lib_y = 1" by (simp add: tat_lib_y_def)\n'
        'lemma "tat_lib_rel_z = 2" by (simp add: tat_lib_rel_z_def)')
    assert not errors(recs), recs
    assert await short_name_holder("TAT_Lib_Helper") == "TAT_TEST.TAT_Lib_Helper"

    # a bare import with no file anywhere: the load itself fails, naming
    # the import (Isabelle's own wording)
    await begin_fails("theory TAT_Test_E imports TAT_No_Such_Theory begin",
                      expect="TAT_No_Such_Theory")

    # a qualified import in no known session: refused by name
    # (RENDER_BASELINES wording, asserted verbatim)
    await begin_fails(
        'theory TAT_Test_F imports "TAT_Nowhere.Nope" begin',
        expect="Fail to load `TAT_Nowhere.Nope` because it is not found.")

    # a header the theory initialisation itself rejects (an unknown load
    # command, named in Isabelle's own wording): begin_theory's failure branch
    await begin_fails(
        'theory TAT_Test_G imports Main '
        'keywords "tat_bad" :: thy_load (tat_no_such_load_command) begin',
        expect="tat_no_such_load_command")

    # each span parses against the state it runs in: a command installed by
    # an earlier span parses in a later one
    k = slot()
    await begin(
        k, 'theory TAT_Test_K imports Main keywords "tat_hello" :: thy_decl begin')
    recs = await run(
        k, k,
        'ML \\<open>Outer_Syntax.command \\<^command_keyword>\\<open>tat_hello\\<close> '
        '"test" (Scan.succeed (Toplevel.keep (fn _ => writeln "tat-hello-cmd")))\\<close>\n'
        'tat_hello')
    assert len(recs) == 2 and not errors(recs), recs
    assert ["writeln", "tat-hello-cmd"] in recs[1][2], recs

    # --- an exception escaping a callback is a bug (EXCEPTIONS.md §1) ---

    async def operation(outcome: str) -> tuple[Isar_State_Slot, list]:
        sl = slot()
        msgs = await isabelle_driver.call(
            connection, "TAT_test.operation", (sl.to_msgpack(), outcome))
        return sl, msgs

    async def escapes(outcome: str, expect: str) -> None:
        try:
            await operation(outcome)
            raise AssertionError(f"{outcome}: nothing escaped")
        except TAT_IsabelleError as e:
            assert expect in str(e), str(e)
            assert isinstance(e.__cause__, IsabelleError)

    sl, msgs = await operation("ok")                  # success: the state, no message
    assert msgs == [] and await is_toplevel(sl) is True
    sl, msgs = await operation("error")               # a user-level error: messages, no state
    assert msgs == ["tat-user-error"] and not await sl.is_initialized()
    await escapes("bug", "tat-bug")                   # a framework Bug propagates
    await escapes("nothing", "a state and no message, or messages and no state")
    await escapes("both", "a state and no message, or messages and no state")

    # --- the Theory node class, end to end (SESSION_AND_THEORY §2) ---

    # a forest on an in-memory store, this directory its working directory
    kinds = {"session": Session, "theory": Theory}
    forest = Routing_Forest(M.Conversation(connection, Path(HERE)),
                            Forest_Store(":memory:"), kinds)

    async def insert(parent, index, raws):
        async with forest.lock:
            return await edit.insert(parent, index, raws, kinds)

    def theory(name, *imports):
        return {"kind": "theory", "name": name, "imports": list(imports)}

    (sess,) = await insert(forest, 0, [
        {"kind": "session", "name": "TAT_E2E", "parent_session": "HOL",
         "children": [theory("TAT_E2E_A", "Main")]}])
    (ta,) = sess.sub_nodes
    assert (sess.name, ta.name) == ("TAT_E2E", "TAT_E2E_A")
    assert (forest.id_of(sess), forest.id_of(ta)) == ("session_TAT_E2E", "theory_TAT_E2E_A")

    # the base-heap half of the short-name check, in gen, over the wire
    try:
        await insert(sess, 1, [theory("List", "Main")])
        raise AssertionError("a heap short name was not refused")
    except DuplicateTheoryShortName as e:
        assert (e.short_name, e.holder) == ("List", "HOL.List"), str(e)

    # an empty theory to its end: the header from a fresh toplevel state
    # into the slot before the ending, `end` into the resulting slot the
    # tree owns, and the theory value into the theory table; the input
    # slot stays what nobody wrote
    r = await ta.evaluate_to(False)
    assert r == M.EvaluationResult(None, M.INVALIDATING), r
    assert (ta.evaluation_status_beginning, ta.evaluation_status_ending) == (READY, READY)
    assert ta.beginning_errors == [] and ta.ending_errors == []
    assert ta.is_finished() and sess.is_finished() and forest.is_finished()
    assert not await ta.state.is_initialized()
    assert await is_toplevel(ta._state_before_ending) is False    # the theory, open
    assert ta.resulting_state() is ta._state_after_ending
    assert await is_toplevel(ta._state_after_ending) is True      # after `end`
    assert await short_name_holder("TAT_E2E_A") is None           # the table, not Thy_Info

    # a second tree importing the first by its bare name: resolved through
    # the conversation's theory table, under the session's name
    (tb,) = await insert(sess, 1, [theory("TAT_E2E_B", "TAT_E2E_A")])
    r = await tb.evaluate_to(False)
    assert r == M.EvaluationResult(None, M.INVALIDATING), r
    assert tb.is_finished() and tb.beginning_errors == []

    # a header that fails -- an import found nowhere -- is the node's own
    # stop at its beginning, with the message; the ending is the framework's
    # copy-through of an input that holds nothing, so the owned resulting
    # slot stays empty under a `ready` ending (the plan's §6)
    (tc,) = await insert(sess, 2, [theory("TAT_E2E_C", "TAT_E2E_Nowhere")])
    r = await tc.evaluate_to(False)
    assert r == M.EvaluationResult(None, M.INVALIDATING), r   # its successors are not blocked
    assert tc.evaluation_status_beginning == CannotEvaluate(None)
    assert any("TAT_E2E_Nowhere" in m for m in tc.beginning_errors), tc.beginning_errors
    assert tc.evaluation_status_ending is READY and not tc.is_finished()
    for sl in (tc.state, tc._state_before_ending, tc._state_after_ending):
        assert not await sl.is_initialized()

    # deleting a tree releases what its operations wrote, in one round trip
    async with forest.lock:
        await edit.delete(ta)
    assert sess.sub_nodes == [tb, tc]
    assert not await ta._state_before_ending.is_initialized()
    assert not await ta._state_after_ending.is_initialized()
