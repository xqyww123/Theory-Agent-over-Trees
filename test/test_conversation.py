"""The Isabelle-backed cases (ai-artifacts/TEST_HARNESS_PLAN.md §6), each on
a fresh conversation of the run's one `isabelle TAT_mcp`: the framework's
primitives through the test plugin's `TAT_test.*` probes, the Theory node
class end to end, the tools through the MCP client, and what a fresh
conversation forgets.  Run: python -m pytest test/test_conversation.py
"""

import asyncio
import json
import time
from pathlib import Path

import pytest
from Isabelle_RPC_Host import IsabelleError, IsabelleInterrupt

import stand_ins
from baselines import DOCS, fenced_blocks, fenced_lines
from harness import text_of
from isabelle_theory_agent import compile, edit, isabelle_driver, model as M
from isabelle_theory_agent.exceptions import (
    DuplicateTheoryShortName, InvalidField, ReservedTheoryName, TAT_IsabelleError,
    TAT_StartupError)
from isabelle_theory_agent.isabelle_driver import call
from isabelle_theory_agent.model import EMPTY_NODE, NOT_EVALUATED, Isar_State_Slot
from test_model import CANNOT_EVALUATE, READY

# RENDER_BASELINES §3's four fenced lines, in order: the order constraint's
# two (test_forest_walk.py), the loader's refusal — asserted verbatim for
# `TAT_Nowhere.Nope` and derived for every other name — and the placement
# check's form line (test_placement.py).  A fifth line, or a missing one,
# fails here.
_, _, NOT_FOUND, _ = fenced_lines(DOCS / "RENDER_BASELINES.md", "3.")
assert NOT_FOUND.count("`TAT_Nowhere.Nope`") == 1, NOT_FOUND


def not_found(name: str) -> str:
    return NOT_FOUND.replace("TAT_Nowhere.Nope", name)


def errors(recs: list) -> list:
    return [e for _, errs, _ in recs for e in errs]


def texts(rec: list) -> list[str]:
    return [t for _, t in rec[2]]


class Probes:
    """The test plugin's `TAT_test.*` probes (test/Test_TAT_Framework.thy),
    each one round trip through `isabelle_driver.call` — the one door to
    the wire; an exception a probe let escape arrives as `TAT_IsabelleError`.
    `make` stores one of two distinguishable states — `top=True` a toplevel
    state, `top=False` a theory state — and `is_toplevel` reads the stored
    state's discriminator back, so a copy that fabricated a state instead of
    mirroring the source would be caught."""

    def __init__(self, conversation: M.Conversation):
        self.conversation = conversation

    def slot(self) -> Isar_State_Slot:
        return Isar_State_Slot.assign(self.conversation)

    async def make(self, slot: Isar_State_Slot, top: bool) -> None:
        await call(self.conversation, "TAT_test.make", (slot.to_msgpack(), top))

    async def is_toplevel(self, slot: Isar_State_Slot) -> bool:
        return await call(self.conversation, "TAT_test.is_toplevel", slot.to_msgpack())

    async def delete(self, slot: Isar_State_Slot) -> None:
        await call(self.conversation, "TAT_test.delete", slot.to_msgpack())

    async def begin(self, slot: Isar_State_Slot, header_src: str, session: str = "TAT_TEST") -> None:
        await call(self.conversation, "TAT_test.begin", (slot.to_msgpack(), (session, "", header_src)))

    async def begin_fails(self, header_src: str, expect: str, session: str = "TAT_TEST") -> None:
        with pytest.raises(TAT_IsabelleError) as e:
            await self.begin(self.slot(), header_src, session)
        assert expect in str(e.value), str(e.value)

    async def run(self, src: Isar_State_Slot, dst: Isar_State_Slot, text: str) -> list:
        return await call(self.conversation, "TAT_test.run", (src.to_msgpack(), (dst.to_msgpack(), text)))

    async def run_parallel(self, a: Isar_State_Slot, b: Isar_State_Slot, text_a: str, text_b: str):
        return await call(self.conversation, "TAT_test.run_parallel",
                          (a.to_msgpack(), (b.to_msgpack(), (text_a, text_b))))

    async def end(self, slot: Isar_State_Slot) -> None:
        await call(self.conversation, "TAT_test.end", slot.to_msgpack())

    async def operation(self, outcome: str) -> tuple[Isar_State_Slot, list]:
        sl = self.slot()
        return sl, await call(self.conversation, "TAT_test.operation", (sl.to_msgpack(), outcome))

    async def operation_escapes(self, outcome: str, expect: str,
                                cause: type[IsabelleError] = IsabelleError) -> None:
        with pytest.raises(TAT_IsabelleError) as e:
            await self.operation(outcome)
        assert expect in str(e.value), str(e.value)
        assert type(e.value.__cause__) is cause

    async def short_name(self, name: str) -> isabelle_driver.Short_Name_Answer:
        return await isabelle_driver.check_new_theory_short_name(self.conversation, name)

    async def session(self, name: str, parent: str | None = None, options=()
                      ) -> isabelle_driver.Session_Answer:
        return await isabelle_driver.check_session(self.conversation, name, parent, options)

    async def begun(self, header_src: str) -> Isar_State_Slot:
        """A theory begun into a fresh slot."""
        sl = self.slot()
        await self.begin(sl, header_src)
        return sl


@pytest.fixture
def probes(conversation) -> Probes:
    return Probes(conversation.forest.conversation)


# --- the harness itself -------------------------------------------------------

async def test_a_fresh_conversation_holds_nothing(conversation):
    """The hand-over: an empty forest on a fresh working directory, a
    connection that answers, and the kind table holding `theory` and
    `session`.  What `TAT.reset` forgets is the reset case's, below."""
    assert list(conversation.forest.sub_nodes) == []
    assert await isabelle_driver.state_exists(conversation.forest.conversation, "nobody") is False
    assert "theory" in conversation.forest.kinds and "session" in conversation.forest.kinds
    # the conversation's log (LOGGING.md §2): under the working directory,
    # the start recorded, the round trip just made recorded with its result
    assert conversation.log.directory.parent == conversation.working_directory / ".tat" / "log"
    assert stand_ins.events("conversation", conversation.log.directory) == [
        "start", "store_opened", "plugins_loaded", "configured", "serving"]
    # the client's files and the scripts, written with the port bound
    # (CLIENT_HOOKS.md): the agent directory beside `.tat/`
    assert (conversation.working_directory / "TAT.agents" / ".mcp.json").is_file()
    assert (conversation.working_directory / ".tat" / "hook.py").is_file()
    told, served, trip = stand_ins.records("round_trip", conversation.log.directory)
    assert told["data"]["name"] == "TAT.log_directory" and "result" not in told["data"]
    assert served["data"]["name"] == "TAT.serving" and "result" not in served["data"]
    assert trip["data"] == {"name": "TAT.state_exists", "arguments": "nobody", "result": False,
                            "duration": trip["data"]["duration"]}
    # the Isabelle side's own file (LOGGING.md §5): every callback it ran,
    # the three above included, once the directory was told
    isabelle = stand_ins.records("isabelle", conversation.log.directory)
    callbacks = [r["data"] for r in isabelle if r["event"] == "callback"]
    assert [c["name"] for c in callbacks][-3:] == ["TAT.log_directory", "TAT.serving", "TAT.state_exists"]
    assert all(c["outcome"] == "returned" and c["duration"] >= 0 for c in callbacks)
    assert all(r["category"] == "isabelle" and "agent" not in r and "call" not in r for r in isabelle)


async def test_restart_serves_the_next_conversation_on_the_same_directory(conversation):
    """`restart()` returns the next conversation's handle; the old handle has
    ended and says so on any access."""
    directory = conversation.working_directory
    t0 = time.monotonic()
    renewed = await conversation.restart()
    print(f"\n[a fresh conversation through restart(): {time.monotonic() - t0:.2f} s]")
    assert renewed.working_directory == directory
    with pytest.raises(RuntimeError, match="use the handle `restart\\(\\)` returned"):
        conversation.forest
    assert await isabelle_driver.state_exists(renewed.forest.conversation, "nobody") is False


# --- state slots (MODULE_STRUCTURE §2.1) ----------------------------------------

async def test_state_slots_through_the_probes(conversation, probes):
    a, b, c = probes.slot(), probes.slot(), probes.slot()

    # a fresh slot holds nothing
    assert not await a.is_initialized()

    # a node-class callback writes it through the env's slot_unpacker,
    # and the stored value comes back distinguishable
    await probes.make(a, False)
    assert await a.is_initialized()
    assert await probes.is_toplevel(a) is False
    await probes.make(b, True)
    assert await probes.is_toplevel(b) is True

    # copy: the target mirrors the source, value included
    await a.copy_to(b)
    assert await b.is_initialized()
    assert await probes.is_toplevel(b) is False

    # get on an empty slot is a bug (EXCEPTIONS.md §1): it escapes the
    # callback unconverted, and arrives as the RPC library's exception
    # under the one door's own
    with pytest.raises(TAT_IsabelleError) as e:
        await probes.is_toplevel(c)
    assert "holds no state" in str(e.value) and isinstance(e.value.__cause__, IsabelleError)

    # copy from an empty slot: the target mirrors the absence
    await c.copy_to(b)
    assert not await b.is_initialized()

    # `put NONE` through the slot handle deletes
    await probes.make(b, True)
    assert await b.is_initialized()
    await probes.delete(b)
    assert not await b.is_initialized()

    # single delete; deleting an absent name is not an error
    await a.delete()
    assert not await a.is_initialized()
    await a.delete()

    # batched delete removes every present name in one round trip
    await probes.make(a, True)
    await probes.make(b, False)
    assert await a.is_initialized() and await b.is_initialized()
    await isabelle_driver.state_delete(conversation.forest.conversation, [a.name, b.name, c.name])
    for s in (a, b, c):
        assert not await s.is_initialized()


# --- the theory pipeline (MODULE_STRUCTURE §2.2-§2.4) ---------------------------

async def test_the_short_name_check_answers_taken_reserved_and_free(probes):
    """The Isabelle half of the short-name check (§2.3): taken by a loaded
    theory, under its long name -- the short name itself for a global one;
    reserved, global in the layout but loaded nowhere; free."""
    assert await probes.short_name("List") == isabelle_driver.Taken("HOL.List")
    assert await probes.short_name("Main") == isabelle_driver.Taken("Main")
    assert await probes.short_name("FOL") == isabelle_driver.Reserved()
    assert await probes.short_name("TAT_Test_A_Fresh_Name") == isabelle_driver.Free()
    # reserved also: what Isabelle refuses as a file name, in any spelling,
    # or as a theory name -- its own predicates, answered by the launcher's
    # Scala function `TAT.reserved_name` (COMPILATION.md §2)
    for name in ("Aux", "aux", "COM1", "ROOT", "ROOTS", "bib"):
        assert await probes.short_name(name) == isabelle_driver.Reserved(), name
    assert await probes.short_name("Draft") == isabelle_driver.Free()    # a session's reserved name


async def test_the_session_check_answers_the_first_defect(probes):
    """`Session.gen`'s one question (§2.3), in its order: the name
    reserved, the name known to the Isabelle session layout, an option
    refused with Isabelle's message, the parent unknown.  The layout lists
    every session Isabelle knows, in the base heap's ancestry or not."""
    D = isabelle_driver
    assert await probes.session("TAT_Fresh", "HOL") == D.Session_Ok()
    assert await probes.session("TAT_Fresh", "HOL-Library") == D.Session_Ok()
    assert await probes.session("TAT_Fresh", "HOL-Libary") == D.Parent_Unknown()
    assert await probes.session("TAT_Fresh", None) == D.Session_Ok()      # the forest settled the parent
    assert await probes.session("TAT_Fresh", "HOL", [("document", "pdf"), ("timeout", "600"),
                                                     ("quick_and_dirty", "true")]) == D.Session_Ok()
    for name in ("aux", "LPT1", "Draft"):                # a file's reserved name, a session's
        assert await probes.session(name, "HOL") == D.Name_Reserved(), name
    assert await probes.session("HOL-Library", "HOL") == D.Name_Known()
    # the options as Isabelle reads a ROOT (TAT.check_options), its messages
    # verbatim: a value Isabelle/ML would read as a number is refused too
    unknown = await probes.session("TAT_Fresh", "HOL-Libary", [("document", "pdf"), ("documnet", "pdf")])
    assert unknown == D.Option_Refused(1, 'Unknown option "documnet"')
    for value in ("soon", "10min"):
        assert await probes.session("TAT_Fresh", "HOL", [("timeout", value)]) == \
            D.Option_Refused(0, f'Malformed value for option "timeout" : real =\n"{value}"'), value
    # the first defect: the name before the options before the parent
    assert await probes.session("Aux", "Nowhere", [("documnet", "x")]) == D.Name_Reserved()
    assert await probes.session("HOL", "Nowhere", [("documnet", "x")]) == D.Name_Known()


async def test_commands_run_in_order_with_output_routed_to_their_own_records(probes):
    # begin a theory whose one import is in the base heap
    t = await probes.begun("theory TAT_Test_A imports Main begin")
    assert await t.is_initialized()

    # five commands (`lemma` and `by` are separate spans; `datatype` needs a
    # keyword contributed by an imported theory): records in order, the
    # sources a verbatim partition of the text, output routed to exactly its
    # own command, and the proof's result block captured (it prints through
    # the urgent channel)
    recs = await probes.run(t, t, (
        'definition tat_test_x :: nat where "tat_test_x = 41"\n'
        'ML \\<open>writeln "tat-hello"; warning "tat-warn"\\<close>\n'
        'datatype tat_test_t = TatA | TatB\n'
        'lemma tat_test_l: "tat_test_x = 41" by (simp add: tat_test_x_def)'))
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
    recs = await probes.run(t, t, (
        'ML \\<open>Output.information "tat-info"; tracing "tat-trace"; '
        'legacy_feature "tat-legacy"\\<close>'))
    assert len(recs) == 1 and not errors(recs), recs
    assert ["information", "tat-info"] in recs[0][2], recs
    assert ["tracing", "tat-trace"] in recs[0][2], recs
    assert any(k == "legacy" and "tat-legacy" in txt for k, txt in recs[0][2]), recs


async def test_sorry_passes_with_quick_and_dirty_on_and_off(probes):
    """Each run declares the option's value itself (`isabelle TAT_mcp` leaves
    it off).  With it on, `sorry` passes as anywhere; with it off, `sorry` still
    passes: the interactive flag of Toplevel.command_errors is what admits
    it, and that is what the second run pins."""
    t = await probes.begun("theory TAT_Test_A imports Main begin")
    s = probes.slot()
    await t.copy_to(s)
    recs = await probes.run(s, s, (
        'declare [[quick_and_dirty = true]]\n'
        'lemma tat_test_sorry: "False" sorry'))
    assert len(recs) == 3 and not errors(recs), recs
    await t.copy_to(s)
    recs = await probes.run(s, s, (
        'declare [[quick_and_dirty = false]]\n'
        'lemma tat_test_sorry_int: "False" sorry'))
    assert len(recs) == 3 and not errors(recs), recs


async def test_empty_text_passes_the_state_through(probes):
    """Empty, whitespace-only and comment-only text (both comment forms): no
    records, and the state passes through into the target slot unchanged."""
    s = await probes.begun("theory TAT_Test_A imports Main begin")
    for text in ("", "   \n", "(* just a comment *)",
                 "\\<comment> \\<open>a marked comment\\<close>"):
        dst = probes.slot()
        recs = await probes.run(s, dst, text)
        assert recs == [], (text, recs)
        assert await dst.is_initialized()
        assert await probes.is_toplevel(dst) == await probes.is_toplevel(s)
        await dst.delete()


async def test_a_failing_command_stops_the_run_and_deletes_the_target(probes):
    """Its record is the last, the run stops, and the pre-populated target
    slot is really deleted -- the `put NONE` of a stateless outcome."""
    t = await probes.begun("theory TAT_Test_A imports Main begin")
    f = probes.slot()
    await t.copy_to(f)
    assert await f.is_initialized()
    recs = await probes.run(t, f, (
        'lemma tat_test_bad: "(1::nat) = 2" by simp\n'
        'ML \\<open>writeln "not reached"\\<close>'))
    assert len(recs) == 2, recs
    assert recs[1][1], recs
    assert not await f.is_initialized()


async def test_a_failed_fork_fails_the_command_and_a_succeeding_one_keeps_the_state(probes):
    """A failed fork's error lands in the record and the committed state is
    withheld; the succeeding fork is the control."""
    t = await probes.begun("theory TAT_Test_A imports Main begin")
    g = probes.slot()
    await t.copy_to(g)
    recs = await probes.run(t, g, (
        'ML \\<open>ignore (Execution.fork {name = "tat_test_fork", '
        'pos = Position.thread_data (), pri = 0} '
        '(fn () => error "tat-fork-boom"))\\<close>'))
    assert len(recs) == 1, recs
    assert any("tat-fork-boom" in e for e in recs[0][1]), recs
    assert not await g.is_initialized()
    await t.copy_to(g)
    recs = await probes.run(t, g, (
        'ML \\<open>ignore (Execution.fork {name = "tat_test_fork_ok", '
        'pos = Position.thread_data (), pri = 0} (fn () => ()))\\<close>'))
    assert len(recs) == 1 and not errors(recs), recs
    assert await g.is_initialized()


async def test_end_and_the_theory_table(probes):
    # `end` and the theory table: a second tree's import resolves to the
    # first tree through the conversation's own table (EVALUATOR_DESIGN §2)
    t = await probes.begun("theory TAT_Test_A imports Main begin")
    recs = await probes.run(t, t, 'definition tat_test_x :: nat where "tat_test_x = 41"\nend')
    assert len(recs) == 2 and not errors(recs), recs
    await probes.end(t)
    u = await probes.begun("theory TAT_Test_B imports TAT_Test_A begin")
    recs = await probes.run(u, u, 'lemma "tat_test_x = 41" by (simp add: tat_test_x_def)')
    assert not errors(recs), recs

    # the table holds the tree under its own Isabelle session's name: the
    # same bare name from another Isabelle session is refused under the
    # name Isabelle resolves it to (RENDER_BASELINES §3)
    await probes.begin_fails("theory TAT_Test_X imports TAT_Test_A begin", session="TAT_OTHER",
                             expect=not_found("TAT_OTHER.TAT_Test_A"))

    # re-evaluation overwrites the theory table entry (§2.2), and a fresh
    # importer sees the second generation
    t2 = await probes.begun("theory TAT_Test_A imports Main begin")
    recs = await probes.run(t2, t2, 'definition tat_test_x2 :: nat where "tat_test_x2 = 42"\nend')
    assert not errors(recs), recs
    await probes.end(t2)
    d = await probes.begun("theory TAT_Test_D imports TAT_Test_A begin")
    recs = await probes.run(d, d, 'lemma "tat_test_x2 = 42" by (simp add: tat_test_x2_def)')
    assert not errors(recs), recs

    # a refused `end`, its theory still inside a context: Isabelle's message
    # as data, the keyword markup around the command's name stripped
    n = await probes.begun("theory TAT_Test_N imports Main begin")
    recs = await probes.run(n, n, "context begin")
    assert len(recs) == 1 and not errors(recs), recs
    dst = probes.slot()
    assert await call(probes.conversation, "TAT.Theory.end", (n.to_msgpack(), dst.to_msgpack())) \
        == ['Bad context for command "end"']
    assert not await dst.is_initialized()


async def test_output_is_isolated_between_concurrent_runs(probes):
    """Two run_commands in two futures: each run's messages land in its own
    records only."""
    u = await probes.begun("theory TAT_Test_B imports Main begin")
    pa, pb = probes.slot(), probes.slot()
    await u.copy_to(pa)
    await u.copy_to(pb)
    ra, rb = await probes.run_parallel(pa, pb, (
        'ML \\<open>writeln "iso-a1"\\<close>\n'
        'lemma iso_a: "(2::nat) = 2" by simp\n'
        'ML \\<open>writeln "iso-a2"\\<close>'), (
        'ML \\<open>writeln "iso-b1"\\<close>\n'
        'lemma iso_b: "(3::nat) = 3" by simp\n'
        'ML \\<open>writeln "iso-b2"\\<close>'))
    flat_a = [t for rec in ra for t in texts(rec)]
    flat_b = [t for rec in rb for t in texts(rec)]
    assert any("iso-a1" in t for t in flat_a) and any("iso-a2" in t for t in flat_a), ra
    assert any("iso-b1" in t for t in flat_b) and any("iso-b2" in t for t in flat_b), rb
    assert not any("iso-b" in t for t in flat_a), (ra, rb)
    assert not any("iso-a" in t for t in flat_b), (ra, rb)


# --- the loader (MODULE_STRUCTURE §2.3, EVALUATOR_DESIGN §2) -------------------------

async def test_an_import_in_no_heap_loads_from_source_by_its_session_qualified_name(conversation, probes):
    """TAT_Lib_Helper.thy next to this file, which the Isabelle session
    layout knows through the repository ROOT's `directories "test"`.
    `Thy_Info` is the process's (TEST_HARNESS_PLAN §2): no other case loads
    this theory, and if one did the load arm would silently be skipped, so
    fail loudly instead."""
    helper = "Theory_Agent_over_Trees.TAT_Lib_Helper"
    assert await probes.short_name("TAT_Lib_Helper") == isabelle_driver.Free(), (
        "TAT_Lib_Helper is already loaded: another case imports it")
    v = await probes.begun(f"theory TAT_Test_C imports {helper} begin")
    recs = await probes.run(v, v, 'lemma "tat_lib_y = 1" by (simp add: tat_lib_y_def)')
    assert not errors(recs), recs
    assert await probes.short_name("TAT_Lib_Helper") == isabelle_driver.Taken(helper)
    # the loader's record (LOGGING.md §4), in this conversation's log
    [loaded] = [r["data"] for r in stand_ins.records("isabelle", conversation.log.directory)
                if r["event"] == "theory_loaded"]
    assert loaded["name"] == helper and loaded["duration"] > 0


async def test_an_import_found_nowhere_is_refused_under_the_name_isabelle_resolved(probes):
    """RENDER_BASELINES §3's sentence: a bare name, taken as the header's
    own session's; a qualified name in no Isabelle session (the document's
    own example, verbatim); a global theory written session-qualified, which
    Isabelle would load a second time under that name (EVALUATOR_DESIGN §7);
    a path, which nothing loads by."""
    await probes.begin_fails("theory TAT_Test_E imports TAT_No_Such_Theory begin",
                             expect=not_found("TAT_TEST.TAT_No_Such_Theory"))
    await probes.begin_fails('theory TAT_Test_F imports "TAT_Nowhere.Nope" begin',
                             expect=NOT_FOUND)
    await probes.begin_fails('theory TAT_Test_M imports "HOL.Main" begin',
                             expect=not_found("HOL.Main"))
    await probes.begin_fails('theory TAT_Test_H imports "lib/TAT_Lib_Rel" begin',
                             expect=not_found("TAT_TEST.TAT_Lib_Rel"))


async def test_a_header_isabelle_itself_rejects_fails_the_beginning(probes):
    """An unknown load command, named in Isabelle's own wording:
    begin_theory's failure branch."""
    await probes.begin_fails(
        'theory TAT_Test_G imports Main keywords "tat_bad" :: thy_load (tat_no_such_load_command) begin',
        expect="tat_no_such_load_command")


async def test_each_span_parses_against_the_state_it_runs_in(probes):
    """A command installed by an earlier span parses in a later one."""
    k = await probes.begun('theory TAT_Test_K imports Main keywords "tat_hello" :: thy_decl begin')
    recs = await probes.run(k, k, (
        'ML \\<open>Outer_Syntax.command \\<^command_keyword>\\<open>tat_hello\\<close> '
        '"test" (Scan.succeed (Toplevel.keep (fn _ => writeln "tat-hello-cmd")))\\<close>\n'
        'tat_hello'))
    assert len(recs) == 2 and not errors(recs), recs
    assert ["writeln", "tat-hello-cmd"] in recs[1][2], recs


# --- an exception escaping a callback is a bug (EXCEPTIONS.md §1) ----------------

async def test_an_exception_escaping_a_callback_is_a_bug(conversation, probes):
    sl, msgs = await probes.operation("ok")             # success: the state, no message
    assert msgs == [] and await probes.is_toplevel(sl) is True
    sl, msgs = await probes.operation("error")          # a user-level error: messages, no state
    assert msgs == ["tat-user-error"] and not await sl.is_initialized()
    sl, msgs = await probes.operation("position")       # an error with a position: its text, markup stripped
    assert msgs == ["tat-pos (line 1)"] and not await sl.is_initialized()
    sl, msgs = await probes.operation("refused")        # a refusal: its messages in order, no state
    assert msgs == ["tat-refused-1", "tat-refused-2"] and not await sl.is_initialized()
    await probes.operation_escapes("bug", "tat-bug")                     # a framework Bug propagates
    await probes.operation_escapes("nothing", "a refusal with no message")
    await probes.operation_escapes("silent", "a refusal with no message")   # an exception rendering to no message
    # The records (LOGGING.md §4): on the Isabelle side the wrapper's
    # `callback` for every run, `raised` for the three that escaped, and
    # `bug` for each Bug -- the explicit one and the two `operation` raises;
    # on the Python side the round trip's error.
    isabelle = stand_ins.records("isabelle", conversation.log.directory)
    outcomes = [r["data"]["outcome"] for r in isabelle
                if r["event"] == "callback" and r["data"]["name"] == "TAT_test.operation"]
    assert outcomes == ["returned"] * 4 + ["raised"] * 3
    bugs = [r for r in isabelle if r["event"] == "bug"]
    assert [(r["level"], r["data"]["callback"]) for r in bugs] == [("error", "TAT_test.operation")] * 3
    assert bugs[0]["data"]["message"] == "tat-bug"
    trips = [r["data"] for r in stand_ins.records("round_trip", conversation.log.directory)
             if r["data"]["name"] == "TAT_test.operation"]
    assert "tat-bug" in trips[4]["error"] and "result" in trips[0]


async def test_a_proper_interrupt_is_the_operations_refusal_and_a_breakdown_escapes(conversation, probes):
    """MODULE_STRUCTURE §2.5: a proper interrupt under the operation -- raised
    under the run, or inside a transition `apply_transition` runs -- is the
    refusal `Interrupt`; a breakdown escapes the callback, answered by the RPC
    library as `IsabelleInterrupt` and raised here as `TAT_IsabelleError` (the
    conversation goes on only because the probe is `Swallow`); a breakdown
    inside a `Par_Exn` escapes whole, answered as its messages."""
    for outcome in ("interrupt", "transition_interrupt"):
        sl, msgs = await probes.operation(outcome)
        assert msgs == ["Interrupt"] and not await sl.is_initialized(), (outcome, msgs)
    await probes.operation_escapes("breakdown", "Interrupt", IsabelleInterrupt)
    assert (await probes.operation("ok"))[1] == []      # the round trip after it still answered
    await probes.operation_escapes("transition_breakdown", "Interrupt", IsabelleInterrupt)
    assert (await probes.operation("ok"))[1] == []
    await probes.operation_escapes("breakdown_wrapped", "Interrupt_Breakdown")
    isabelle = stand_ins.records("isabelle", conversation.log.directory)
    outcomes = [r["data"]["outcome"] for r in isabelle
                if r["event"] == "callback" and r["data"]["name"] == "TAT_test.operation"]
    assert outcomes == ["returned", "returned", "interrupted", "returned", "interrupted", "returned", "raised"]
    assert [r for r in isabelle if r["event"] == "bug"] == []


async def test_a_log_the_isabelle_side_cannot_write_stops_nothing(conversation, probes):
    """LOGGING.md §5: the Isabelle side drops a record it cannot write and
    reports nothing; here its file is replaced by a directory."""
    path = conversation.log.directory / "isabelle.jsonl"
    path.unlink()
    path.mkdir()
    sl, msgs = await probes.operation("ok")
    assert msgs == [] and await probes.is_toplevel(sl) is True
    with pytest.raises(TAT_IsabelleError):
        await probes.operation("bug")
    assert path.is_dir() and list(path.iterdir()) == []
    # the Python side's own records are untouched
    assert stand_ins.events("round_trip", conversation.log.directory)[-2:] == ["round_trip"] * 2


async def test_the_launcher_prints_the_log_path_and_follows_warnings(harness, conversation):
    """LOGGING.md §7: the launcher learned the directory from the Isabelle
    side and printed it; a `warning` record appended to any file of the
    directory is printed as it is written, a line that is not JSON skipped."""
    directory = conversation.log.directory
    record = {"ts": "2026-10-01T07:24:05.039123Z", "category": "agent", "event": "note",
              "level": "warning", "data": {"message": "The transcript moved."}}
    (directory / "agent.jsonl").write_text("not json\n" + json.dumps(record) + "\n")
    expected = [f"Log: {directory}", "### The transcript moved. (agent.jsonl, 07:24:05.039123Z)"]
    deadline = time.monotonic() + 10
    while not all(line in harness.child_output() for line in expected):
        assert time.monotonic() < deadline, harness.child_output()
        await asyncio.sleep(0.2)


# --- the Theory node class, end to end (SESSION_AND_THEORY §2) -------------------

def theory(name, *imports):
    return {"kind": "theory", "name": name, "imports": list(imports)}


async def test_the_theory_node_class_end_to_end(conversation, probes, monkeypatch):
    forest = conversation.forest

    # every theory_delete round trip recorded on its way to the wire
    theory_deletes: list[list[str]] = []
    real_theory_delete = isabelle_driver.theory_delete

    async def recording_theory_delete(conversation, names):
        theory_deletes.append(list(names))
        await real_theory_delete(conversation, names)
    monkeypatch.setattr(isabelle_driver, "theory_delete", recording_theory_delete)

    async def insert(parent, index, raws):
        async with forest.lock:
            return await edit.insert(parent, index, raws)

    (sess,) = await insert(forest, 0, [
        {"kind": "session", "name": "TAT_E2E", "parent_session": "HOL",
         "children": [theory("TAT_E2E_A", "Main", "HOL.List", "HOL-Library.Phantom_Type")]}])
    (ta,) = sess.sub_nodes
    assert (sess.name, ta.name) == ("TAT_E2E", "TAT_E2E_A")
    assert (forest.id_of(sess), forest.id_of(ta)) == ("session_TAT_E2E", "theory_TAT_E2E_A")

    # the Isabelle half of the short-name check, in gen, over the wire:
    # taken by a loaded theory, by a loaded global theory, reserved
    for name, holder in (("List", "HOL.List"), ("Main", "Main")):
        with pytest.raises(DuplicateTheoryShortName) as e:
            await insert(sess, 1, [theory(name, "Main")])
        assert (e.value.short_name, e.value.holder) == (name, holder), str(e.value)
    with pytest.raises(ReservedTheoryName) as e:
        await insert(sess, 1, [theory("FOL", "Main")])
    assert e.value.name == "FOL", str(e.value)
    # the Isabelle half of `parent_session`'s check, in gen, over the wire
    with pytest.raises(InvalidField) as e:
        await insert(forest, 1, [{"kind": "session", "name": "TAT_E2E_B",
                                  "parent_session": "HOL-Libary"}])
    assert e.value.reason == "must name an existing session; `HOL-Libary` is not one", str(e.value)

    # an empty theory to its end: the header from a fresh toplevel state
    # into the slot before the ending, `end` into the resulting slot the
    # tree owns, and the theory value into the theory table; the input
    # slot stays what nobody wrote
    r = await ta.evaluate_to(None, False)
    assert r == M.EvaluationResult(None, None), r
    assert (ta.evaluation_status_beginning, ta.evaluation_status_ending) == (READY, READY)
    assert ta.evaluation_status_beginning == READY and ta.evaluation_status_ending == READY
    assert ta.is_finished() and sess.is_finished() and forest.is_finished()
    assert not await ta.state.is_initialized()
    assert await probes.is_toplevel(ta._state_before_ending) is False    # the theory, open
    assert ta.resulting_state() is ta._state_after_ending
    assert await probes.is_toplevel(ta._state_after_ending) is True      # after `end`
    assert await probes.short_name("TAT_E2E_A") == isabelle_driver.Free()   # the table, not Thy_Info
    # the header's run made the session's folder, and recorded the session
    # of each import as Isabelle answers it (COMPILATION.md §2): a global
    # theory's, a qualified name's in the parent session and in another
    assert (forest.conversation.working_directory / "TAT_E2E").is_dir()
    assert ta.file_path() == Path("TAT_E2E/TAT_E2E_A.thy")
    assert ta.import_sessions == ["HOL", "HOL", "HOL-Library"]
    # and the keyword table's identifier-shaped words, minor and major
    assert ta.keywords is not None and {"and", "where", "lemma"} <= ta.keywords and "::" not in ta.keywords

    # a second tree importing the first by its bare name: resolved through
    # the conversation's theory table, under the session's name
    (tb,) = await insert(sess, 1, [theory("TAT_E2E_B", "TAT_E2E_A")])
    r = await tb.evaluate_to(None, False)
    assert r == M.EvaluationResult(None, None), r
    assert tb.is_finished() and tb.evaluation_status_beginning == READY
    assert tb.import_sessions == ["TAT_E2E"]                   # a tree of the forest: its `Session`

    # a header that fails -- an import found nowhere, refused under the
    # name Isabelle resolved it to (RENDER_BASELINES §3, the whole
    # sentence) -- makes the node an obstacle at its beginning, with the
    # message; the ending is the framework's copy-through of an input that
    # holds nothing, so the owned resulting slot stays empty under a
    # `ready` ending
    (tc,) = await insert(sess, 2, [theory("TAT_E2E_C", "TAT_E2E_Nowhere")])
    r = await tc.evaluate_to(None, False)
    assert r == M.EvaluationResult(None, None), r   # its successors are not blocked
    beginning = tc.evaluation_status_beginning
    assert isinstance(beginning, M.CannotEvaluate)
    assert any(not_found("TAT_E2E.TAT_E2E_Nowhere") in m.unicode for m in beginning.messages), \
        beginning.messages
    assert tc.evaluation_status_ending is READY and not tc.is_finished()
    assert tc.import_sessions == [] and tc.keywords is None    # recorded only when the header passes
    for sl in (tc.state, tc._state_before_ending, tc._state_after_ending):
        assert not await sl.is_initialized()
    assert theory_deletes == [], theory_deletes                # nothing has vanished so far

    # deleting a tree releases what its operations wrote, in one round
    # trip; its importer is `not_evaluated` whole (ARCHITECTURE §3.4) and
    # the tree's name is gone from the theory table in one theory_delete
    # round trip, so the importer's next header fails under the name
    # Isabelle resolves the import to -- `Loader.resolve` never hands it
    # the value of a tree that no longer exists
    async with forest.lock:
        await edit.delete(ta)
    assert sess.sub_nodes == [tb, tc]
    assert not await ta._state_before_ending.is_initialized()
    assert not await ta._state_after_ending.is_initialized()
    assert (tb.evaluation_status_beginning, tb.evaluation_status_ending) == \
        (NOT_EVALUATED, NOT_EVALUATED)
    assert not await tb._state_after_ending.is_initialized()
    assert theory_deletes == [["TAT_E2E.TAT_E2E_A"]], theory_deletes
    r = await tb.evaluate_to(None, False)
    assert r == M.EvaluationResult(None, None), r
    beginning = tb.evaluation_status_beginning
    assert isinstance(beginning, M.CannotEvaluate)
    assert any(not_found("TAT_E2E.TAT_E2E_A") in m.unicode for m in beginning.messages), \
        beginning.messages

    # deleting the session whole: one theory_delete round trip carrying
    # every name that vanished -- TAT_E2E_B's, which the table held, and
    # TAT_E2E_C's, which it never held
    async with forest.lock:
        await edit.delete(sess)
    assert forest.sub_nodes == []
    assert theory_deletes == [["TAT_E2E.TAT_E2E_A"], ["TAT_E2E.TAT_E2E_B", "TAT_E2E.TAT_E2E_C"]], \
        theory_deletes


async def test_a_theory_named_with_a_keyword_evaluates_compiles_and_builds_as_one_header(conversation):
    """SESSION_AND_THEORY §2: a theory named `lemmas`, a command of Pure,
    writes `theory "lemmas"` in its own header, which evaluation accepts
    and the compile writes to the file; and the file's header stays one
    command span under the keyword table a build reads it with — the
    evaluated theory's — which a bare `lemmas` would cut in two."""
    forest = conversation.forest
    async with forest.lock:
        (sess,) = await edit.insert(forest, 0, [
            {"kind": "session", "name": "TAT_E2E_W", "parent_session": "HOL",
             "children": [theory("lemmas", "Main")]}])
    (t,) = sess.sub_nodes
    assert t.header() == 'theory "lemmas"\n  imports "Main"\nbegin'
    r = await t.evaluate_to(None, False)
    assert r == M.EvaluationResult(None, None) and t.is_finished(), r
    assert t.evaluation_status_beginning == READY and t.keywords is not None and "lemmas" in t.keywords
    compile.compile(forest, ())
    text = (conversation.working_directory / "TAT_E2E_W" / "lemmas.thy").read_text()
    assert text == 'theory "lemmas"\n  imports "Main"\nbegin\nend\n'
    spans = await call(conversation.forest.conversation, "TAT_test.spans",
                       (t._state_before_ending.to_msgpack(), text))
    assert spans[0] == t.header(), spans
    bare = await call(conversation.forest.conversation, "TAT_test.spans",
                      (t._state_before_ending.to_msgpack(), text.replace('"lemmas"', "lemmas")))
    assert bare[0] == "theory", bare


async def test_a_session_folder_that_cannot_be_made_stops_the_header_before_it_runs(conversation):
    """MODULE_STRUCTURE §4.1: a `Theory`'s beginning makes its `Session`'s
    folder, and one that cannot be made — a file, a symbolic link at its
    path — raises a `TAT_StartupError` with COMPILATION.md §7's sentence,
    which ends a conversation at the tool boundary, before anything runs:
    nothing of the tree is written, in Isabelle or in the database."""
    forest = conversation.forest
    async with forest.lock:
        blocked, linked = await edit.insert(forest, 0, [
            {"kind": "session", "name": "TAT_E2E_Blocked", "parent_session": "HOL",
             "children": [theory("TAT_E2E_D", "Main")]},
            {"kind": "session", "name": "TAT_E2E_Linked", "parent_session": "HOL",
             "children": [theory("TAT_E2E_L", "Main")]}])
    directory = forest.conversation.working_directory
    (directory / "TAT_E2E_Blocked").write_text("not a directory")
    (directory / "TAT_E2E_Linked").symlink_to(directory)
    _, _, (a_link, not_a_directory, _) = fenced_blocks(DOCS / "COMPILATION.md", "7.")
    store = forest.store
    rows = {node: store.fields(node) for node in store.nodes()}
    for session, sentence in ((blocked, not_a_directory), (linked, a_link)):
        (tree,) = session.sub_nodes
        with pytest.raises(M.CannotUseWorkingDirectory) as refused:
            await tree.evaluate_to(None, False)
        assert isinstance(refused.value, TAT_StartupError)
        assert str(refused.value) == (sentence.replace("<working directory>", str(directory))
                                      .replace("<Session name>", session.name))
        assert (tree.evaluation_status_beginning, tree.last_evaluation_statuses()) == \
            (NOT_EVALUATED, (NOT_EVALUATED, NOT_EVALUATED))
        assert not await tree._state_after_beginning().is_initialized()
    assert {node: store.fields(node) for node in store.nodes()} == rows


# --- the tools, and the next conversation on the same working directory ------------

async def test_the_tools_evaluate_a_tree_and_the_next_conversation_restores_it(conversation):
    """FIRST_END_TO_END_RUN_PLAN §7 step 5's test: through the MCP client,
    one `edit` call builds a session holding one theory and evaluates it;
    then the next conversation on the same working directory starts from
    the database, `not_evaluated` throughout (ARCHITECTURE §9), and
    evaluates it again."""
    async with conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [{"kind": "session", "name": "TAT_E2E", "parent_session": "HOL",
                            "children": [theory("TAT_E2E_A", "Main",
                                                "HOL-Library.Phantom_Type")]}]})
    text = text_of(result)
    assert not result.isError, text
    assert text.startswith("Done: append Sessions.\n"), text
    assert "- theory_TAT_E2E_A (complete)" in text, text

    renewed = await conversation.restart()
    (sess,) = renewed.forest.sub_nodes
    (ta,) = sess.sub_nodes
    assert (sess.name, ta.name) == ("TAT_E2E", "TAT_E2E_A")
    assert not sess.is_finished()
    assert (ta.evaluation_status_beginning, ta.evaluation_status_ending) == \
        (NOT_EVALUATED, NOT_EVALUATED)
    # what the run before the restart stored: the statuses, and the session of each import
    assert ta.last_evaluation_statuses() == (READY, READY)
    assert ta.import_sessions == ["HOL", "HOL-Library"]
    assert ta.keywords is not None and "lemma" in ta.keywords
    r = await ta.evaluate_to(None, False)
    assert r.stopped_at is None, r
    assert (ta.evaluation_status_beginning, ta.evaluation_status_ending) == (READY, READY)


async def test_recall_through_the_wire(conversation):
    """RECALL.md §3 through the MCP client: a call with no arguments at
    all reads the briefing — every node one line, no field, no message;
    `Sessions` as the id reads the root in `Recall` — the lone session at
    depth 1, its theories at depth 2, where a failed header's message
    shows once per run and the `edit`'s quickview has shown it; a `recall`
    of the failed theory, at depth 0, shows the block whole (PRINT.md §3,
    §4, §6)."""
    async with conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [{"kind": "session", "name": "TAT_RECALL", "parent_session": "HOL",
                            "children": [theory("TAT_RECALL_A", "Main"),
                                         theory("TAT_RECALL_B", "TAT_Nowhere.Nope")]}]})
        text = text_of(result)
        assert not result.isError and text.count("Error:") == 1, text
        briefing = await session.call_tool("recall")
        empty = lambda node_id: "  " + EMPTY_NODE.format(id=node_id)   # noqa: E731  # PRINT.md §2
        assert not briefing.isError and text_of(briefing).splitlines() == [
            "session_TAT_RECALL (incomplete)","- theory_TAT_RECALL_A (complete)", empty("theory_TAT_RECALL_A"),
            "- theory_TAT_RECALL_B (failed)", empty("theory_TAT_RECALL_B")], text_of(briefing)
        sessions = await session.call_tool("recall", {"node_id": "Sessions"})
        assert not sessions.isError and text_of(sessions).splitlines() == [   # the children headers (PRINT.md §2)
            "session_TAT_RECALL (incomplete)", "parent_session: HOL", "theories:",
            "  - theory_TAT_RECALL_A (complete)", "    imports: Main", "    declarations:", "    " + empty("theory_TAT_RECALL_A"),
            "  - theory_TAT_RECALL_B (failed)", "    imports: TAT_Nowhere.Nope", "    declarations:", "    " + empty("theory_TAT_RECALL_B")
            ], text_of(sessions)
        failed = await session.call_tool("recall", {"node_id": "theory_TAT_RECALL_B"})
        assert not failed.isError and text_of(failed).splitlines() == [
            "- theory_TAT_RECALL_B (failed)", "  imports: TAT_Nowhere.Nope",
            "  Error:", "    " + NOT_FOUND, "  declarations:", "  " + empty("theory_TAT_RECALL_B")], text_of(failed)


async def test_a_fresh_conversation_forgets_the_previous_ones_state(conversation, probes):
    """`TAT.reset` (TEST_HARNESS_PLAN §2): the previous conversation's slot
    names — its own, kept across the restart; a fresh conversation's slots
    are fresh names whether or not the reset ran — answer `state_exists`
    false, and its theory table no longer answers the previous tree's
    import."""
    t = await probes.begun("theory TAT_Test_A imports Main begin")
    recs = await probes.run(t, t, "end")
    assert len(recs) == 1 and not errors(recs), recs
    await probes.end(t)
    u = await probes.begun("theory TAT_Test_B imports TAT_Test_A begin")
    names = [t.name, u.name]
    for name in names:
        assert await isabelle_driver.state_exists(conversation.forest.conversation, name) is True

    renewed = await conversation.restart()
    fresh = Probes(renewed.forest.conversation)
    for name in names:
        assert await isabelle_driver.state_exists(renewed.forest.conversation, name) is False
    await fresh.begin_fails("theory TAT_Test_B imports TAT_Test_A begin",
                            expect=not_found("TAT_TEST.TAT_Test_A"))
