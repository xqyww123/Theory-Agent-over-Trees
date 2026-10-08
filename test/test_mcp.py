"""The tools of `mcp.py` (TOOL_SCHEMAS.md, MODULE_STRUCTURE §4.6) on
`test_model`'s fake classes and `test_jobs`'s job classes: the advertised
schemas and descriptions against the documents; the three forest-changing
tools — where each action and position puts or takes a node, the
`evaluate` flag, the `Done` line and the quickview that follow — and
`recall`; the construct tools (CONSTRUCT_INTERACTION §5) — the nodes of a
call, what `construct` and `cancel_construct` start, cancel and say, the
four conditions `check_construct` returns on and its clamps, `answer`'s
refusals — and every refusal's class, fields and lines (RENDER_BASELINES
§1, §2); a malformed call's lines are read from TOOL_SCHEMAS §4 and
RECALL.md §3.  The call check itself, on a schema of every shape it
reads, is `test_plugin`'s.  Nothing here crosses the wire.
Run: python -m pytest test/test_mcp.py
"""

import asyncio
import typing

import jsoncomment
import pytest

import test_jobs
import test_model as tm
from baselines import DOCS, fenced_blocks, fenced_lines, stated
from test_jobs import Check, Checked, Lemma, Proof, asking, report, until
from test_model import T, add, slot

from Isabelle_RPC_Host.unicode import IsaTerm

import isabelle_theory_agent.model as M
from isabelle_theory_agent import jobs, mcp, plugin
from isabelle_theory_agent.jobs import NOT_STARTED, RUNNING, Agent, Message, Succeeded
from isabelle_theory_agent.exceptions import (
    AmbiguousId, BadAnswer, ConstructNotSupported, ConstructOwnedByAnother, HoldsNoChildren, InvalidField,
    MissingField, MoveBesideItself, MoveIntoOwnSubtree, NodeNotFound, NoQuestionPending, ProtectedNode,
    RawASTError, TAT_Error, TAT_InternalError, UnexpectedField)
from isabelle_theory_agent.mcp_server import With_Trailer
from isabelle_theory_agent.model import NOT_EVALUATED
from test_model import CANNOT_EVALUATE, READY


class Block(tm.Block):                  # omissible like a `Theory`, so the tests' ids stay short
    output_omissible = input_omissible = True


class Search(Proof):                    # a second construction job class, for the completed descriptions
    @classmethod
    def title(cls, plural=False):
        return "counterexample searches" if plural else "counterexample search"


class Searched(T):
    construction_job_class = Search


class Only_Checked(T):                  # an evaluation job class and no construction job class
    evaluation_job_class = Check


class Search_Check(Check):              # a second evaluation job class, for the counts and the descriptions
    @classmethod
    def title(cls, plural=False):
        return "counterexample searches" if plural else "counterexample search"


class Searched_Checked(Lemma):
    evaluation_job_class = Search_Check


KINDS = {"t": T, "block": Block}
JOB_KINDS = {**KINDS, "lemma": Lemma, "checked": Checked}
EDIT_SCHEMA = mcp._schema("edit")       # the envelope, its `$defs` empty: the check reads no construct
TOOL_SCHEMAS = DOCS / "TOOL_SCHEMAS.md"
RECALL = DOCS / "RECALL.md"
CI = DOCS / "CONSTRUCT_INTERACTION.md"
RB = DOCS / "RENDER_BASELINES.md"


@pytest.fixture(autouse=True)
def table(monkeypatch):
    tm.TABLE.clear()
    tm.TABLE.install(monkeypatch)
    yield from test_jobs.isolated(monkeypatch)


def loaded(kinds) -> plugin.Loaded:
    """`Loaded` as `load` builds it for `kinds`: the job classes they name,
    and `auto_construct` on `edit` when one is a construction job class
    (TOOL_SCHEMAS §1) — on the envelope, its `$defs` left empty."""
    classes = list(kinds.values())
    constructions = plugin._job_classes(classes, lambda cls: cls.construction_job_class)
    schema = EDIT_SCHEMA if not constructions else {
        **EDIT_SCHEMA, "properties": {**EDIT_SCHEMA["properties"], "auto_construct": plugin.AUTO_CONSTRUCT_PROPERTY}}
    return plugin.Loaded(kinds, schema, (), constructions,
                         plugin._job_classes(classes, lambda cls: cls.evaluation_job_class))


def forest(kinds=KINDS) -> tm.OneTreeForest:
    """An empty forest whose ending knows it, as the start's does."""
    f = tm.OneTreeForest(tm.CONN, kinds=kinds)
    f.conversation.ending.forest = f
    return f


def build(kinds=KINDS):
    """Theory > [Section > [a, b], c]; the tools over it, by name — the
    construct tools among them when `kinds` names job classes."""
    f = forest(kinds)
    thy = add(f, Block(f, slot(), "Theory", slot()))
    sec = add(thy, Block(thy, slot(), "Section", slot()))
    a = add(sec, T(sec, slot(), "a")); b = add(sec, T(sec, slot(), "b"))
    c = add(thy, T(thy, slot(), "c"))
    tools = {t.name: t for t in mcp.tools(f, loaded(kinds))}
    return f, thy, sec, a, b, c, tools


def agent() -> Agent:
    """The caller, fresh for every call: no case here reads a seen set."""
    return Agent("main", True)


def body(result) -> str:
    """A body's text, with or without the trailer it asks for."""
    return result.text if isinstance(result, With_Trailer) else result


def call(tool, **arguments) -> list[str]:
    """The body's lines, for a fresh caller."""
    return body(asyncio.run(tool.run(agent(), arguments))).splitlines()


_E = typing.TypeVar("_E", bound=TAT_Error)


def refused(tool, cls: type[_E], **arguments) -> tuple[_E, list[str]]:
    """A refusal: the exception, to assert by its class and fields, and
    the lines it renders — the first the entry's own (RENDER_BASELINES §1)."""
    with pytest.raises(cls) as e:
        asyncio.run(tool.run(agent(), arguments))
    return e.value, str(e.value).splitlines()


def t(name, **fields):
    return {"kind": "t", "name": name, **fields}


def block(name, *children):
    return {"kind": "block", "name": name, **({"children": list(children)} if children else {})}


def names(parent):
    return [n.name for n in parent.sub_nodes]


# --- what the server is given ------------------------------------------------

def test_the_tools_their_descriptions_and_schemas_as_the_documents_state_them():
    """TOOL_SCHEMAS §1–§3, §5 and RECALL.md §3, with the two job classes of
    test_jobs loaded — titled as `Theorem`'s, so the descriptions completed
    at start read as CONSTRUCT_INTERACTION §5's `Theorem` examples."""
    f, *_, _ = build(JOB_KINDS)
    ld = loaded(JOB_KINDS)
    tools = {t.name: t for t in mcp.tools(f, ld)}
    assert list(tools) == ["edit", "move", "delete", "recall", "evaluate_to",
                           "construct", "cancel_construct", "check_construct", "answer"]
    assert [tools[n].description for n in ("edit", "move", "delete", "recall")] == \
        stated(TOOL_SCHEMAS, "Tool description") + stated(RECALL, "Tool description")
    assert [tools[n].description for n in ("evaluate_to", "construct", "cancel_construct", "check_construct",
                                           "answer")] == [
        "Evaluate Isabelle theory constructs up to a node. Already evaluated constructs are skipped.",
        "Start the construction jobs of nodes, such as proof constructions.",
        "Cancel the running construction jobs of nodes.",
        "Wait until any proof construction or all proof checks have finished, or a message arrives. Returns at"
        " once when nothing is running. To ensure all jobs have finished, call it repeatedly.",
        "Answer the question a construction job asked you"]
    assert [t.read_only for t in tools.values()] == [False, False, False, True, False, False, False, True, False]
    parse = jsoncomment.JsonComment().loads
    [edit], [move], [delete] = (fenced_blocks(TOOL_SCHEMAS, s) for s in ("1.", "2.", "3."))
    evaluate_to, construct, cancel_construct, check_construct, answer = fenced_blocks(TOOL_SCHEMAS, "5.")
    recall, _ = fenced_blocks(RECALL, "3.")
    assert ld.edit_schema == parse("\n".join(edit))        # the envelope `Loaded.edit_schema` fills
    assert tools["edit"].input_schema is ld.edit_schema    # `Loaded.edit_schema`, as given
    evaluate_to = [line.replace("{titles}", "proof checks") for line in evaluate_to]   # completed at start
    for name, block in (("move", move), ("delete", delete), ("recall", recall), ("evaluate_to", evaluate_to),
                        ("construct", construct), ("cancel_construct", cancel_construct),
                        ("check_construct", check_construct), ("answer", answer)):
        assert tools[name].input_schema == parse("\n".join(block)), name
    # `tools` validates what it advertises (`plugin.validate_call_schema`), naming the tool.
    broken = {**EDIT_SCHEMA, "properties": {**EDIT_SCHEMA["properties"], "extra": {"type": "null"}}}
    with pytest.raises(TAT_InternalError, match=r"edit\.extra: not of one JSON type"):
        mcp.tools(f, plugin.Loaded(KINDS, broken))


def test_the_construct_tools_exist_by_the_job_classes_loaded():
    """CONSTRUCT_INTERACTION §3.1, §5: `construct`, `cancel_construct` and
    `answer` only with a construction job class, `check_construct` with a
    job class of either kind, `edit`'s `auto_construct` with a construction
    job class; the two completed descriptions with one and with several
    titles, `check_construct`'s in its three forms."""
    tail = (" finished, or a message arrives. Returns at once when nothing is running. To ensure all jobs"
            " have finished, call it repeatedly.")
    *_, tools = build()
    assert list(tools) == ["edit", "move", "delete", "recall", "evaluate_to"]
    assert "auto_construct" not in tools["edit"].input_schema["properties"]
    assert "checks" not in tools["evaluate_to"].input_schema["properties"]
    *_, tools = build({**KINDS, "checked": Only_Checked})
    assert list(tools)[5:] == ["check_construct"]
    assert "auto_construct" not in tools["edit"].input_schema["properties"]
    assert tools["check_construct"].description == "Wait until all proof checks have" + tail
    assert tools["evaluate_to"].input_schema["properties"]["checks"]["description"].startswith(
        'Whether to run the proof checks of the nodes: "no" runs none;')
    *_, tools = build({**KINDS, "lemma": Lemma})
    assert list(tools)[5:] == ["construct", "cancel_construct", "check_construct", "answer"]
    assert tools["edit"].input_schema["properties"]["auto_construct"] is plugin.AUTO_CONSTRUCT_PROPERTY
    assert tools["check_construct"].description == "Wait until any proof construction has" + tail
    assert "checks" not in tools["evaluate_to"].input_schema["properties"]
    *_, tools = build({**KINDS, "lemma": Lemma, "searched": Searched})
    assert tools["check_construct"].description == (
        "Wait until any counterexample search or proof construction has" + tail)
    *_, tools = build({**JOB_KINDS, "searched": Searched, "searched_checked": Searched_Checked})
    assert tools["evaluate_to"].input_schema["properties"]["checks"]["description"].startswith(
        'Whether to run the counterexample searches and proof checks of the nodes: "no" runs none;')
    *_, tools = build({**JOB_KINDS, "searched": Searched})
    assert tools["construct"].description == (
        "Start the construction jobs of nodes, such as counterexample searches and proof constructions.")
    assert tools["check_construct"].description == (
        "Wait until any counterexample search or proof construction or all proof checks have" + tail)
    *_, tools = build(THEORIES)                             # two classes of one title: the title once
    assert tools["construct"].description == (
        "Start the construction jobs of nodes, such as counterexample searches and proof constructions.")


def test_recall_s_description_and_schema_are_recall_md_s():
    """RECALL.md §3, on its own: the case above stops at `edit`'s schema
    until that tool's later arguments exist."""
    *_, tools = build()
    recall, _ = fenced_blocks(RECALL, "3.")
    assert [tools["recall"].description] == stated(RECALL, "Tool description")
    assert tools["recall"].input_schema == jsoncomment.JsonComment().loads("\n".join(recall))


def test_a_tool_renders_for_the_agent_that_called_it():
    """PRINT.md §4, §5: a tool's rendering is for the calling agent — the
    message its quickview showed that agent is not in its next quickview,
    and is in another agent's."""
    class Loud(T):
        async def _eval_opr(self):
            return M.CannotEvaluate((IsaTerm.from_agent("it broke"),))

    kinds = {**KINDS, "loud": Loud}
    f = tm.OneTreeForest(tm.CONN, kinds=kinds)
    add(f, Block(f, slot(), "Theory", slot()))
    edit = {t.name: t for t in mcp.tools(f, plugin.Loaded(kinds, EDIT_SCHEMA))}["edit"]
    one, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)

    def append(caller, construct, evaluate) -> str:
        return body(asyncio.run(edit.run(caller, dict(action="append", target_id="block_Theory",
                                                      constructs=[construct], evaluate=evaluate))))
    assert "it broke" in append(one, {"kind": "loud", "name": "x"}, True)
    assert "it broke" not in append(one, t("y"), False)        # shown to this agent already
    assert "it broke" in append(other, t("z"), False)


def entries(block: list[str]) -> list[str]:
    """A fenced block of notices as its entries: a header's list items are
    its own lines (CONSTRUCT_INTERACTION §5's forms)."""
    out: list[str] = []
    for line in block:
        if line.startswith("  - "):
            out[-1] += "\n" + line
        else:
            out.append(line)
    return out


def test_the_success_lines_of_render_baselines_section_6():
    """RENDER_BASELINES §6's three blocks: the `Done` lines; `evaluate_to`'s
    two opening lines; the eight forms of `construct`'s and
    `cancel_construct`'s lines over theory_X > [P, Q, R] and theory_Y >
    [S], each the text above the quickview, and `Automatically started …`
    before the trailer of a call whose walk started a construction
    (CONSTRUCT_INTERACTION §5, whose block the last eight are)."""
    kinds = {"theory": Block, "section": Block, "lemma": Lemma, "definition": T}
    done, evaluation, construction = fenced_blocks(RB, "6.")
    f = forest(kinds)
    x = add(f, Block(f, slot(), "X", slot()), "theory")
    add(x, Block(x, slot(), "Basics", slot()), "section")
    add(x, Lemma(x, slot(), "P"), "lemma")
    add(f, Block(f, slot(), "Sorting", slot()), "theory")
    tools = {t.name: t for t in mcp.tools(f, loaded(kinds))}
    assert done == [
        call(tools["edit"], action="append", target_id="theory_X",
             constructs=[{"kind": "lemma", "name": "Q"}], evaluate=False)[0],
        call(tools["edit"], action="insert_after", target_id="theory_X.lemma_P",
             constructs=[{"kind": "definition", "name": "f", "fail": True}], evaluate=True)[0],
        call(tools["move"], source_id="theory_Sorting",
             location={"position": "after", "node_id": "theory_X.section_Basics"}, evaluate=False)[0],
        call(tools["delete"], node_id="theory_X.section_Basics")[0],
    ]
    assert evaluation == ["Evaluation reached theory_X.", "Evaluation stopped at definition_f."]

    add(x, Lemma(x, slot(), "R"), "lemma")
    y = add(f, Block(f, slot(), "Y", slot()), "theory")
    add(y, Lemma(y, slot(), "S"), "lemma")
    automatic, *forms = entries(construction)
    assert automatic.startswith("Automatically started the proof construction on `theory_X.lemma_A`")
    assert construction[1:] == fenced_blocks(CI, "5.")[2]
    expected = dict(zip(["one", "three", "four", "none", "cancel_one", "cancel_three", "cancel_four",
                         "cancel_none"], forms))
    said: dict[str, str] = {}

    async def notice(key: str, tool: str, caller: Agent, *ids: str) -> None:
        """The text above the quickview, as many lines as the block's entry."""
        text = await tools[tool].run(caller, {"node_ids": list(ids)})
        assert isinstance(text, str)
        said[key] = "\n".join(text.splitlines()[:len(expected[key].splitlines())])

    async def scenario():                   # one loop: the runs outlive the calls
        me, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)
        await notice("one", "construct", me, "theory_X.lemma_P")
        await notice("cancel_one", "cancel_construct", me, "theory_X.lemma_P")
        await notice("three", "construct", me, "theory_X.lemma_P", "theory_X.lemma_Q", "theory_X.lemma_R")
        await notice("cancel_three", "cancel_construct", me,
                     "theory_X.lemma_P", "theory_X.lemma_Q", "theory_X.lemma_R")
        await notice("four", "construct", me, "theory_X", "theory_Y")
        await notice("cancel_four", "cancel_construct", me, "theory_X", "theory_Y")
        await tools["construct"].run(other, {"node_ids": ["theory_X.lemma_P"]})
        await notice("none", "construct", me, "theory_X.lemma_P")              # running already: skipped
        await notice("cancel_none", "cancel_construct", me, "theory_X.lemma_P")  # another agent's run: skipped
        assert said == expected
        assert f.resolve("theory_X.lemma_P").job().owner is other
        # `evaluate_to`: definition_f, an obstacle, is the stop again; passed under `ignore_error`,
        # the walk reaches lemma_A, whose automatic construction is on
        await tools["edit"].run(me, dict(action="append", target_id="theory_X", evaluate=False,
                                         auto_construct=True, constructs=[{"kind": "lemma", "name": "A"}]))
        result = await tools["evaluate_to"].run(me, {"node_id": "theory_X"})
        assert body(result).splitlines()[0] == evaluation[1] and result.trailer() == ""
        result = await tools["evaluate_to"].run(me, {"node_id": "theory_X", "ignore_error": True})
        assert body(result).splitlines()[0] == evaluation[0] and result.trailer() == automatic
        assert f.resolve("theory_X.lemma_A").job().owner is me
        await settled(f)
    tm.run(scenario())


def test_evaluate_to_s_result_the_background_line_and_blocking():
    """MCP_SPECIFICATION §4, CONSTRUCT_INTERACTION §5: the opening line over
    the quickview of the destination at depth 0, the root and a theory as
    destinations; the walk's checks under `quick`, the caller's running
    checks counted in the background line — titles alphabetical, the call
    to make the first time, nothing at zero; `"no"` starting none;
    `"blocking"` keeping the lock until every check running on a passed
    node has ended, whoever started it, its failure posted to its
    starter."""
    kinds = {"theory": Block, "lemma": Checked, "searched": Searched_Checked}
    f = forest(kinds)
    x = add(f, Block(f, slot(), "X", slot()), "theory")
    for name in "PQR":
        add(x, Checked(x, slot(), name), "lemma")
    y = add(f, Block(f, slot(), "Y", slot()), "theory")
    add(y, Checked(y, slot(), "S"), "lemma")
    add(y, Searched_Checked(y, slot(), "W"), "searched")
    for node in f._tree_order():
        if node.job() is not None:
            node.job().outcome = Succeeded("by simp")           # proven, unchecked: the walk starts the check
    tools = {t.name: t for t in mcp.tools(f, loaded(kinds))}
    n = f.resolve

    async def scenario():
        a, b, c = Agent("main", True), Agent("a9f3c2d1e4b5", False), Agent("b7e2d4c6a8f0", False)
        result = await tools["evaluate_to"].run(a, {"node_id": P})
        assert body(result).splitlines() == [
            "Evaluation reached lemma_P.", "Sessions:", "- theory_X (incomplete)", "  - lemma_P (incomplete)",
            "  - lemma_Q (not evaluated)", "  - lemma_R (not evaluated)", "- theory_Y (not evaluated)"]
        assert result.trailer() == "1 proof check is running in the background; call `check_construct` to wait for them."
        check = n(P).evaluation_job()
        assert isinstance(check, Check) and check.starter is a and check.began
        result = await tools["evaluate_to"].run(a, {"node_id": "theory_X"})
        assert body(result).splitlines()[:2] == ["Evaluation reached theory_X.", "Sessions:"]
        assert result.trailer() == "3 proof checks are running in the background."
        assert n(P).evaluation_job() is check                       # a check on the node already: no second
        result = await tools["evaluate_to"].run(b, {"node_id": "theory_Y"})
        assert result.trailer() == ("1 counterexample search and 1 proof check are running in the background;"
                                    " call `check_construct` to wait for them.")
        result = await tools["evaluate_to"].run(b, {"node_id": "Sessions"})
        assert body(result).splitlines() == ["Evaluation reached Sessions.", "Sessions:", "- theory_X (incomplete)",
                                             "- theory_Y (incomplete)"]
        assert result.trailer() == "1 counterexample search and 1 proof check are running in the background."
        # a walk starting nothing for an agent with nothing running: no trailer at all
        result = await tools["evaluate_to"].run(c, {"node_id": "theory_X", "checks": "no"})
        assert isinstance(result, With_Trailer) and result.trailer() == ""
        # an edit's own evaluation runs with `quick`: T, proven and unchecked, gets c's check
        t = add(y, Checked(y, slot(), "T"), "lemma")
        t.job().outcome = Succeeded("by simp")
        result = await tools["edit"].run(c, dict(action="append", target_id="theory_Y", evaluate=True,
                                                 constructs=[{"kind": "lemma", "name": "U"}]))
        assert isinstance(result, With_Trailer) and t.evaluation_job().starter is c
        assert result.trailer() == "1 proof check is running in the background; call `check_construct` to wait for them."
        u = n("theory_Y.lemma_U")
        u.job().outcome = Succeeded("by simp")
        result = await tools["evaluate_to"].run(c, {"node_id": "theory_Y.lemma_U", "checks": "no"})
        assert u.evaluation_job() is None and result.trailer() == "1 proof check is running in the background."
        # a construction started automatically is named before the background line
        await tools["edit"].run(c, dict(action="append", target_id="theory_Y", evaluate=False, auto_construct=True,
                                        constructs=[{"kind": "lemma", "name": "V"}]))
        result = await tools["evaluate_to"].run(c, {"node_id": "theory_Y"})        # U's check starts now too
        assert n("theory_Y.lemma_V").job().owner is c and u.evaluation_job().starter is c
        assert result.trailer() == ("Automatically started the proof construction on `theory_Y.lemma_V`; call"
                                    " `check_construct` before you exit.\n\n"
                                    "2 proof checks are running in the background.")
        # blocking: the passed nodes' checks are a's; b waits for them under the lock
        task = calling(tools["evaluate_to"], b, node_id="theory_X", checks="blocking")
        await still_waiting(task)
        assert f.lock.locked()
        for id in (P, Q):
            await report(n(id).evaluation_job())
        await still_waiting(task)
        await report(n(R).evaluation_job(), ["bad"])
        result = await asyncio.wait_for(task, 2.0)
        assert body(result).splitlines()[0] == "Evaluation reached theory_X." and not f.lock.locked()
        assert result.trailer() == "1 counterexample search and 1 proof check are running in the background."
        assert [m.text for m in a.mailbox] == [
            "The proof on `theory_X.lemma_R` no longer holds. Call `construct` to prove it again."]
        assert b.mailbox == []
        await settled(f)
    tm.run(scenario())


def test_evaluate_to_s_refusals_render_the_cause_alone():
    """TOOL_SCHEMAS §4: a failed `evaluate_to` has no opening line — an id no
    node bears, a malformed call."""
    *_, tools = build(JOB_KINDS)
    evaluate_to = tools["evaluate_to"]
    e, lines = refused(evaluate_to, NodeNotFound, node_id="block_Z")
    assert e.id == "block_Z" and len(lines) == 1
    e, lines = refused(evaluate_to, InvalidField, node_id="t_c", checks="later")
    assert (e.field, e.of_tool) == ("checks", True)
    assert lines == ["The argument `checks` must be one of `no`, `quick`, `blocking`."]
    e, lines = refused(evaluate_to, MissingField)
    assert (e.holder, e.field, e.of_tool, len(lines)) == ("evaluate_to", "node_id", True, 1)
    e, lines = refused(evaluate_to, InvalidField, node_id="t_c", ignore_error="yes")
    assert (e.field, len(lines)) == ("ignore_error", 1)


# --- edit ---------------------------------------------------------------------

def test_append_links_at_the_end_and_shows_the_new_nodes_whole():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["edit"], action="append", target_id="block_Theory",
               constructs=[block("S2", t("x")), t("y")], evaluate=False)
    assert names(thy) == ["Section", "c", "S2", "y"]
    assert out == [
        "Done: append block_Theory.",
        "block_Theory (not evaluated)",             # on the path: the lone tree, dashless
        "- block_Section (not evaluated)",          # beside the focus: lines
        "- t_c (not evaluated)",
        "- block_S2 (not evaluated)",               # the batch, whole
        "  - t_x (not evaluated)",
        "- t_y (not evaluated)",
    ]


def test_the_roots_first_layer_takes_an_append_and_is_ordered_like_any_other():
    """TOOL_SCHEMAS §1: `append` on `Sessions` — the call the empty
    forest's hint instructs — and an insertion beside a first-layer node;
    then the root's other permission, a `move … into` it (TOOL_SCHEMAS §2,
    EXCEPTIONS §3's `ProtectedNode` row), whose index is counted after the
    node's removal."""
    f, thy, *_, tools = build()
    out = call(tools["edit"], action="append", target_id="Sessions", constructs=[block("Two")],
               evaluate=False)
    assert names(f) == ["Theory", "Two"]
    assert out == ["Done: append Sessions.", "Sessions:",
                   "- block_Theory (not evaluated)", "- block_Two (not evaluated)"]
    call(tools["edit"], action="insert_before", target_id="block_Theory", constructs=[block("One")],
         evaluate=False)
    assert names(f) == ["One", "Theory", "Two"]
    out = call(tools["move"], source_id="block_Theory",
               location={"position": "into", "node_id": "Sessions"}, evaluate=False)
    assert names(f) == ["One", "Two", "Theory"]           # `into` the root: to the end of the first layer
    assert out[0] == "Done: move block_Theory into Sessions."


def test_insert_before_and_after_place_beside_the_target():
    f, thy, sec, a, b, c, tools = build()
    call(tools["edit"], action="insert_before", target_id="t_b", constructs=[t("p")], evaluate=False)
    call(tools["edit"], action="insert_after", target_id="t_b", constructs=[t("q"), t("r")],
         evaluate=False)
    assert names(sec) == ["a", "p", "b", "q", "r"]
    out = call(tools["edit"], action="insert_after", target_id="block_Section", constructs=[t("s")],
               evaluate=False)
    assert names(thy) == ["Section", "s", "c"]
    assert out[:3] == ["Done: insert_after block_Section.", "block_Theory (not evaluated)",
                       "- block_Section (not evaluated)"]
    assert out[3:] == ["- t_s (not evaluated)", "- t_c (not evaluated)"]


def test_amend_focuses_the_replacement_and_what_follows_it():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["edit"], action="amend", target_id="block_Section",
               constructs=[block("Renamed"), t("z")], evaluate=False)
    assert names(thy) == ["Renamed", "z", "c"] and names(thy.sub_nodes[0]) == ["a", "b"]
    assert out == [
        "Done: amend block_Section.",
        "block_Theory (not evaluated)",
        "- block_Renamed (not evaluated)",          # inherited children, printed whole
        "  - t_a (not evaluated)",
        "  - t_b (not evaluated)",
        "- t_z (not evaluated)",
        "- t_c (not evaluated)",
    ]


def test_the_quickview_prints_what_a_call_added_whole_and_no_deeper_than_its_depth():
    """PRINT.md §5's table: every node of an `edit`'s batch and all under
    it (-1); the moved node's subtree (-1); a deleted node's parent with
    its children as lines (0)."""
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["edit"], action="append", target_id="block_Theory",
               constructs=[block("S2", block("S3", t("x")), t("z")), block("S4", t("y"))],
               evaluate=False)
    assert out[4:] == ["- block_S2 (not evaluated)", "  - block_S3 (not evaluated)",
                       "    - t_x (not evaluated)", "  - t_z (not evaluated)",
                       "- block_S4 (not evaluated)", "  - t_y (not evaluated)"]
    out = call(tools["move"], source_id="block_S2",
               location={"position": "before", "node_id": "block_Section"}, evaluate=False)
    assert names(thy) == ["S2", "Section", "c", "S4"]
    assert out == ["Done: move block_S2 before block_Section.", "block_Theory (not evaluated)",
                   "- block_S2 (not evaluated)", "  - block_S3 (not evaluated)",
                   "    - t_x (not evaluated)", "  - t_z (not evaluated)",
                   "- block_Section (not evaluated)", "- t_c (not evaluated)",
                   "- block_S4 (not evaluated)"]
    out = call(tools["delete"], node_id="t_z")
    assert out == ["Done: delete t_z.", "block_Theory (not evaluated)",
                   "- block_S2 (not evaluated)", "  - block_S3 (not evaluated)",   # no t_x: depth 0
                   "- block_Section (not evaluated)", "- t_c (not evaluated)",
                   "- block_S4 (not evaluated)"]


def test_evaluate_runs_to_the_last_new_node_and_names_a_stop():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["edit"], action="append", target_id="block_Section", constructs=[t("x")],
               evaluate=True)
    x = sec.sub_nodes[-1]
    assert [tm.st(n) for n in (a, b, x, c)] == [READY, READY, READY, tm.NOT_EVALUATED]
    assert out[0] == "Done: append block_Section." and "  - t_x (complete)" in out
    out = call(tools["edit"], action="insert_after", target_id="t_x",
               constructs=[t("bad", fail=True), t("after")], evaluate=True)
    bad, after = sec.sub_nodes[-2:]
    assert tm.st(bad) is CANNOT_EVALUATE and tm.st(after) is NOT_EVALUATED
    assert out[0] == "Done: insert_after t_x; evaluation stopped at t_bad."
    assert out[-3:] == ["  - t_bad (failed)", "  - t_after (not evaluated)", "- t_c (not evaluated)"]


def test_edit_refusals_open_with_the_operation_and_leave_the_forest_alone():
    f, thy, sec, a, b, c, tools = build()
    edit = tools["edit"]
    e, lines = refused(edit, HoldsNoChildren, action="append", target_id="t_c", constructs=[t("x")],
                       evaluate=False)
    assert lines[0] == "Cannot append t_c" and (e.id, e.kind) == ("t_c", "t")
    for action in ("insert_before", "insert_after", "amend"):
        e, lines = refused(edit, ProtectedNode, action=action, target_id="Sessions",
                           constructs=[t("x")], evaluate=False)
        assert lines[0] == f"Cannot {action} Sessions" and e.id == "Sessions"
    e, lines = refused(edit, NodeNotFound, action="append", target_id="t_zzz", constructs=[t("x")],
                       evaluate=False)
    assert lines[0] == "Cannot append t_zzz" and e.id == "t_zzz"
    e, lines = refused(edit, MissingField, action="append", target_id="block_Theory",
                       constructs=[t("a"), {"kind": "t"}], evaluate=False)
    assert lines[0] == "Cannot append block_Theory"
    assert (e.holder, e.field, e.of_tool, e.raw_ast_path) == ("t", "name", False, "constructs[1]")
    assert names(thy) == ["Section", "c"] and names(sec) == ["a", "b"]


def test_a_malformed_call_is_refused_on_its_own_shape_with_no_opening_line():
    """TOOL_SCHEMAS §4's block, both ways: every line of it comes from a
    call in the loop below, and every call in the loop renders a line of
    it; the cases after it fall outside the block and are asserted by
    class and fields."""
    f, thy, sec, *_, tools = build(JOB_KINDS)              # `auto_construct` in `it takes …`
    edit, move, delete = tools["edit"], tools["move"], tools["delete"]
    malformed, = fenced_blocks(TOOL_SCHEMAS, "4.")
    rendered = set()
    for tool, arguments in [
        (edit, dict(action="append", target_id="t_c", constructs=[t("x")])),
        (edit, dict(action="append", target_id="t_c", constructs=[t("x")], evaluate=False, kind="t")),
        (edit, dict(action="append", target_id="t_c", constructs=t("x"), evaluate=False)),
        (edit, dict(action="append", target_id="block_Theory", constructs=[], evaluate=False)),
        (edit, dict(action="amend", target_id="block_Section", constructs=[], evaluate=True)),
        (edit, dict(action="prepend", target_id="t_c", constructs=[t("x")], evaluate=False)),
        (move, dict(source_id="t_a", location={"position": "under", "node_id": "t_c"}, evaluate=False)),
    ]:
        e, lines = refused(tool, RawASTError, **arguments)
        assert isinstance(e, (MissingField, UnexpectedField, InvalidField)) and e.of_tool
        assert len(lines) == 1 and lines[0] in malformed, arguments
        rendered.add(lines[0])
    assert rendered == set(malformed)
    # Beyond the block, asserted by class and fields: a nested argument's
    # shape errors, and a missing top-level one on another tool.
    for tool, arguments, field in [
        (edit, dict(action="append", target_id="t_c", constructs=[t("x")], evaluate="yes"), "evaluate"),
        (edit, dict(action="append", target_id="t_c", constructs=[t("x")], evaluate=False, auto_construct="yes"),
         "auto_construct"),
        (move, dict(source_id="t_a", location=5, evaluate=False), "location"),
        (move, dict(source_id="t_a", location={"position": 5, "node_id": "t_c"}, evaluate=False),
         "location.position"),
    ]:
        e, lines = refused(tool, InvalidField, **arguments)
        assert (e.field, e.of_tool, len(lines)) == (field, True, 1)
    e, lines = refused(move, UnexpectedField, source_id="t_a",
                       location={"position": "before", "node_id": "t_c", "x": 1}, evaluate=False)
    assert (e.holder, e.field, e.holder_is_top, e.of_tool) == ("location", "x", False, True)
    e, lines = refused(move, MissingField, source_id="t_a", location={"position": "before"},
                       evaluate=False)
    assert (e.holder, e.field, e.of_tool) == ("move", "location.node_id", True)
    e, lines = refused(delete, MissingField)
    assert (e.holder, e.field, e.of_tool) == ("delete", "node_id", True)
    assert names(thy) == ["Section", "c"] and names(sec) == ["a", "b"]


# --- move ---------------------------------------------------------------------

def test_move_before_after_and_into_count_the_index_after_the_removal():
    f, thy, sec, a, b, c, tools = build()
    move = tools["move"]
    out = call(move, source_id="t_a", location={"position": "after", "node_id": "t_b"}, evaluate=False)
    assert names(sec) == ["b", "a"]
    assert out == ["Done: move t_a after t_b.", "block_Theory (not evaluated)",
                   "- block_Section (not evaluated)", "  - t_b (not evaluated)",
                   "  - t_a (not evaluated)", "- t_c (not evaluated)"]
    call(move, source_id="t_a", location={"position": "before", "node_id": "t_b"}, evaluate=False)
    assert names(sec) == ["a", "b"]
    call(move, source_id="t_c", location={"position": "into", "node_id": "block_Section"}, evaluate=False)
    assert names(sec) == ["a", "b", "c"] and names(thy) == ["Section"]
    call(move, source_id="t_a", location={"position": "into", "node_id": "block_Section"}, evaluate=False)
    assert names(sec) == ["b", "c", "a"]                  # into its own parent: to the end


def test_move_evaluates_the_moved_subtree_when_asked():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["move"], source_id="block_Section", location={"position": "after", "node_id": "t_c"},
               evaluate=True)
    assert names(thy) == ["c", "Section"]
    assert (c._status, a._status, b._status) == (READY, READY, READY)
    assert out == ["Done: move block_Section after t_c.", "block_Theory (incomplete)",   # its ending did not run
                   "- t_c (complete)", "- block_Section (complete)", "  - t_a (complete)", "  - t_b (complete)"]


def test_move_refusals():
    f, thy, sec, a, b, c, tools = build()
    move = tools["move"]
    e, lines = refused(move, HoldsNoChildren, source_id="t_a",
                       location={"position": "into", "node_id": "t_c"}, evaluate=False)
    assert lines[0] == "Cannot move t_a into t_c" and (e.id, e.kind) == ("t_c", "t")
    e, lines = refused(move, MoveIntoOwnSubtree, source_id="block_Section",
                       location={"position": "after", "node_id": "t_a"}, evaluate=False)
    assert lines[0] == "Cannot move block_Section after t_a"
    assert (e.id, e.destination) == ("block_Section", "block_Section")
    e, lines = refused(move, MoveBesideItself, source_id="t_a",
                       location={"position": "after", "node_id": "t_a"}, evaluate=False)
    assert lines[0] == "Cannot move t_a after t_a" and e.id == "t_a"
    e, lines = refused(move, ProtectedNode, source_id="Sessions",
                       location={"position": "into", "node_id": "block_Section"}, evaluate=False)
    assert lines[0] == "Cannot move Sessions into block_Section" and e.id == "Sessions"
    e, lines = refused(move, ProtectedNode, source_id="t_a",
                       location={"position": "before", "node_id": "Sessions"}, evaluate=False)
    assert lines[0] == "Cannot move t_a before Sessions" and e.id == "Sessions"
    assert names(sec) == ["a", "b"] and names(thy) == ["Section", "c"]


# --- delete -------------------------------------------------------------------

def test_delete_shows_the_old_parent_with_what_is_left():
    f, thy, sec, a, b, c, tools = build()
    out = call(tools["delete"], node_id="t_a")
    assert names(sec) == ["b"]
    assert out == ["Done: delete t_a.", "block_Theory (not evaluated)",
                   "- block_Section (not evaluated)", "  - t_b (not evaluated)", "- t_c (not evaluated)"]
    out = call(tools["delete"], node_id="block_Section")
    assert names(thy) == ["c"]
    assert out == ["Done: delete block_Section.", "block_Theory (not evaluated)", "- t_c (not evaluated)"]
    e, lines = refused(tools["delete"], ProtectedNode, node_id="Sessions")
    assert lines[0] == "Cannot delete Sessions" and e.id == "Sessions"
    e, lines = refused(tools["delete"], NodeNotFound, node_id="t_a")
    assert lines[0] == "Cannot delete t_a" and e.id == "t_a"


# --- recall -------------------------------------------------------------------

def test_recall_renders_the_node_in_recall_and_the_briefing_without_an_id():
    """RECALL.md §2, §3: with an id the lines are the framework's at
    `Recall`'s depths — `t_x`, four levels down, is what tells `Recall`
    from the briefing, which goes to the bottom; `Sessions` as the id
    renders the root in `Recall`; a read takes no lock (MCP_SPECIFICATION
    §5)."""
    f, thy, sec, *_, tools = build()
    inner = add(sec, Block(sec, slot(), "Inner", slot()))
    add(inner, T(inner, slot(), "x"))
    sessions = ["block_Theory (not evaluated)", "- block_Section (not evaluated)",
                "  - t_a (not evaluated)", "  - t_b (not evaluated)",
                "  - block_Inner (not evaluated)", "- t_c (not evaluated)"]
    briefing = [*sessions[:5], "    - t_x (not evaluated)", sessions[5]]
    assert call(tools["recall"]) == briefing
    assert call(tools["recall"], node_id="Sessions") == sessions
    assert call(tools["recall"], node_id="block_Section") == [
        "- block_Section (not evaluated)", "  - t_a (not evaluated)", "  - t_b (not evaluated)",
        "  - block_Inner (not evaluated)", "    - t_x (not evaluated)"]

    async def under_the_lock():
        async with f.lock:
            return await asyncio.wait_for(tools["recall"].run(agent(), {}), timeout=1)
    assert asyncio.run(under_the_lock()).splitlines() == briefing


def test_recall_refusals_render_the_cause_alone():
    """RECALL.md §3's block: its first two lines are RENDER_BASELINES §2's,
    which test_exceptions ties to the classes; the third is `recall`'s
    own.  Every refusal by class and fields, one line, no opening line,
    the forest untouched."""
    f, thy, sec, *_, tools = build()
    other = add(thy, Block(thy, slot(), "Other", slot()))
    add(other, T(other, slot(), "a"))                       # a second `a`: `t_a` is ambiguous
    recall = tools["recall"]
    _, [not_found, ambiguous, unexpected] = fenced_blocks(RECALL, "3.")
    assert {not_found, ambiguous} <= set(fenced_lines(DOCS / "RENDER_BASELINES.md", "2."))
    e, lines = refused(recall, NodeNotFound, node_id="t_z")
    assert (e.id, e.opr, len(lines)) == ("t_z", None, 1)
    e, lines = refused(recall, AmbiguousId, node_id="t_a")
    assert (e.id, e.candidates, len(lines)) == ("t_a", ["block_Section.t_a", "block_Other.t_a"], 1)
    e, lines = refused(recall, InvalidField, node_id=3)
    assert (e.field, e.of_tool, len(lines)) == ("node_id", True, 1)
    e, lines = refused(recall, UnexpectedField, id="t_c")
    assert (e.holder, e.field, e.of_tool) == ("recall", "id", True) and lines == [unexpected]
    assert names(thy) == ["Section", "c", "Other"] and names(sec) == ["a", "b"]


# --- the construct tools (CONSTRUCT_INTERACTION §5) ----------------------------
#
# Every case runs in one loop, since the runs outlive the calls, and ends with
# every job of its forest ended (`settled`).

class Unready(Proof):                   # a class whose own condition for a start fails
    def _check(self):
        return False


class Unready_Lemma(Lemma):
    construction_job_class = Unready


THEORIES = {"theory": Block, "section": Block, "lemma": Checked, "definition": T,
            "unready": Unready_Lemma, "searched": Searched}
P, Q, R = "theory_X.lemma_P", "theory_X.lemma_Q", "theory_X.lemma_R"
S, T_, U = "theory_Y.lemma_S", "theory_Y.lemma_T", "theory_Y.unready_U"      # T_: beside the class T
SEARCHED = "theory_Y.searched_V"


def theories():
    """theory_X > [section_Basics, definition_f, lemma_P, lemma_Q, lemma_R],
    theory_Y > [lemma_S, lemma_T, unready_U, searched_V] — the lemmas carry
    both jobs, titled as `Theorem`'s; the tools over it, by name; and the
    forest's node by its id."""
    f = forest(THEORIES)
    x = add(f, Block(f, slot(), "X", slot()), "theory")
    add(x, Block(x, slot(), "Basics", slot()), "section")
    add(x, T(x, slot(), "f"), "definition")
    for name in "PQR":
        add(x, Checked(x, slot(), name), "lemma")
    y = add(f, Block(f, slot(), "Y", slot()), "theory")
    for name in "ST":
        add(y, Checked(y, slot(), name), "lemma")
    add(y, Unready_Lemma(y, slot(), "U"), "unready")
    add(y, Searched(y, slot(), "V"), "searched")
    tools = {t.name: t for t in mcp.tools(f, loaded(THEORIES))}
    return f, tools, f.resolve


async def settled(f) -> None:
    """Every job of the forest ended before the loop closes: a run cancelled
    silently, a check reported passing."""
    for node in f._tree_order():
        job = node.job()
        if job is not None and job.outcome is RUNNING:
            job.cancel(None)
        check = node.evaluation_job()
        if check is not None and check.outcome is RUNNING:
            await report(check)
    await asyncio.sleep(0)


def calling(tool, caller: Agent, **arguments) -> asyncio.Task:
    """The call in a task of its own, so the case can watch it wait."""
    return asyncio.ensure_future(tool.run(caller, arguments))


async def still_waiting(task: asyncio.Task) -> None:
    await asyncio.sleep(0.05)
    assert not task.done()


async def returned(task: asyncio.Task) -> With_Trailer:
    """A `check_construct` that returned with its state lines: the body
    empty, the trailer its."""
    result = await asyncio.wait_for(task, 2.0)
    assert isinstance(result, With_Trailer) and result.text == ""
    return result


async def asked(job, owner: Agent) -> None:
    """The job's run started by `owner` and waiting on a `Verdict`."""
    job.ends_with = asking
    job.release = asyncio.Event()
    job.start(owner)
    job.release.set()
    await until(owner, lambda: job.pending_question is not None)


def test_the_nodes_of_a_call_the_skipping_and_the_one_refusal():
    """CONSTRUCT_INTERACTION §5: the nodes the ids name, a non-leaf standing
    for every node under it, those without a construction job left out,
    each once, in tree order; `auto_construct` written on each as the call
    gives it — off when left out — and stored; a node that cannot be
    started now is skipped, not refused; a run of another agent's is
    skipped by `cancel_construct` and goes on; the quickview's focuses at
    depth 0 are the named nodes, one under another left out.  Refused only
    when no node of the call has a construction job, RENDER_BASELINES §2's
    two lines; a call that fails starts nothing."""
    async def scenario():
        f, tools, n = theories()
        me, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)
        construct, cancel = tools["construct"], tools["cancel_construct"]
        tm.TABLE.clear_writes()
        text = await construct.run(me, {"node_ids": ["theory_X", Q], "auto_construct": True})
        assert tm.TABLE.transactions == 3                # each node once, stored by its start
        assert text.splitlines() == [
            "Started the proof construction on `theory_X.lemma_P`, on `theory_X.lemma_Q` and on"
            " `theory_X.lemma_R`; call `check_construct` before you exit.",
            "Sessions:", "- theory_X (not evaluated)", "  - section_Basics (not evaluated)",
            "  - definition_f (not evaluated)", "  - lemma_P (not evaluated, automatic construction)",
            "  - lemma_Q (not evaluated, automatic construction)", "  - lemma_R (not evaluated, automatic construction)",
            "- theory_Y (not evaluated)"]
        for id in (P, Q, R):
            job = n(id).job()
            assert job.outcome is RUNNING and job.owner is me and job.auto_construct
            assert f.store.get(n(id).identity, "auto_construct") is True
        text = await cancel.run(me, {"node_ids": ["theory_X"]})
        assert text.splitlines()[0] == ("Cancelled the proof construction on `theory_X.lemma_P`, on"
                                        " `theory_X.lemma_Q` and on `theory_X.lemma_R`.")
        for id in (P, Q, R):
            job = n(id).job()
            assert job.outcome is NOT_STARTED and not job.auto_construct
            assert f.store.get(n(id).identity, "auto_construct") is False
        # skipped, not refused: a run of another agent's, and a class whose condition fails
        await construct.run(other, {"node_ids": [P]})
        text = await construct.run(me, {"node_ids": [P, "theory_Y"]})
        assert text.splitlines()[:2] == [
            "Started the proof construction on `theory_Y.lemma_S` and on `theory_Y.lemma_T`; call"
            " `check_construct` before you exit.",
            "Started the counterexample search on `theory_Y.searched_V`; call `check_construct` before you exit."]
        assert n(P).job().owner is other and n(U).job().outcome is NOT_STARTED
        text = await cancel.run(me, {"node_ids": [P, S]})
        assert text.splitlines()[0] == "Cancelled the proof construction on `theory_Y.lemma_S`."
        assert n(P).job().outcome is RUNNING and n(P).job().owner is other
        # the one refusal, and a failing call starting nothing
        causes = fenced_lines(RB, "2.")
        for tool in (construct, cancel):
            with pytest.raises(ConstructNotSupported) as e:
                await tool.run(me, {"node_ids": ["theory_X.section_Basics"]})
            assert e.value.id == "theory_X.section_Basics"
            assert str(e.value) == "`theory_X.section_Basics` has nothing to construct." and str(e.value) in causes
            with pytest.raises(ConstructNotSupported) as e:
                await tool.run(me, {"node_ids": ["theory_X.section_Basics", "theory_X.definition_f"]})
            assert e.value.id is None
            assert str(e.value) == "None of these nodes has anything to construct." and str(e.value) in causes
        with pytest.raises(NodeNotFound) as e:
            await construct.run(me, {"node_ids": [Q, "theory_X.lemma_Z"]})
        assert e.value.id == "theory_X.lemma_Z" and n(Q).job().outcome is NOT_STARTED
        for arguments in ({"node_ids": []}, {"node_ids": "theory_X"}, {"node_ids": [P], "auto_construct": 1}, {}):
            with pytest.raises(RawASTError) as e:
                await construct.run(me, arguments)
            assert e.value.of_tool
        await settled(f)
    tm.run(scenario())


def test_edit_writes_auto_construct_on_each_new_nodes_job():
    """TOOL_SCHEMAS §1, MODULE_STRUCTURE §4.2: `edit`'s `auto_construct` is
    written on every new node's construction job after `gen`, off when
    left out, stored, and tagged in the quickview."""
    async def scenario():
        f, tools, n = theories()
        me = Agent("main", True)
        text = await tools["edit"].run(me, dict(
            action="append", target_id="theory_Y", evaluate=False, auto_construct=True,
            constructs=[{"kind": "lemma", "name": "W"}, {"kind": "definition", "name": "g"},
                        {"kind": "searched", "name": "Z"}]))
        assert text.splitlines()[-3:] == ["  - lemma_W (not evaluated, automatic construction)",
                                          "  - definition_g (not evaluated)",
                                          "  - searched_Z (not evaluated, automatic construction)"]
        for id in ("theory_Y.lemma_W", "theory_Y.searched_Z"):
            assert n(id).job().auto_construct and f.store.get(n(id).identity, "auto_construct") is True
        assert n("theory_Y.definition_g").job() is None
        await tools["edit"].run(me, dict(action="append", target_id="theory_Y", evaluate=False,
                                         constructs=[{"kind": "lemma", "name": "Y"}]))
        y = n("theory_Y.lemma_Y")
        assert y.job().auto_construct is False and f.store.get(y.identity, "auto_construct") is False
        await tools["edit"].run(me, dict(action="amend", target_id="theory_Y.lemma_Y", evaluate=False,
                                         auto_construct=True, constructs=[{"kind": "lemma", "name": "Y"}]))
        y = n("theory_Y.lemma_Y")
        assert y.job().auto_construct is True and f.store.get(y.identity, "auto_construct") is True
        await tools["edit"].run(me, dict(action="amend", target_id="theory_Y.lemma_W", evaluate=False,
                                         constructs=[{"kind": "lemma", "name": "W"}]))
        assert n("theory_Y.lemma_W").job().auto_construct is False
    tm.run(scenario())


def test_check_construct_answers_no_job_at_once_and_returns_on_an_interrupting_message():
    """CONSTRUCT_INTERACTION §5: neither kind running or waiting at the
    start — `No job is running.`, a plain result, at once, a message
    changing nothing; otherwise the body is empty and the state lines are
    the trailer.  Condition 1: an interrupting message in the mailbox, a
    plain one leaving the call waiting; delivery is the boundary's."""
    async def scenario():
        f, tools, n = theories()
        me = Agent("main", True)
        check = tools["check_construct"]
        assert await asyncio.wait_for(check.run(me, {"wait_seconds": 3600}), 1.0) == mcp.NO_JOB
        jobs.post(f.conversation.log, Message(me, "hello", interrupts=True))
        assert await asyncio.wait_for(check.run(me, {"wait_seconds": 3600}), 1.0) == mcp.NO_JOB
        me.mailbox.clear()
        n(P).job().start(me)
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        jobs.post(f.conversation.log, Message(me, "note", interrupts=False))
        await still_waiting(task)                                  # judged again on the wake: no return
        jobs.post(f.conversation.log, Message(me, "urgent", interrupts=True))
        result = await returned(task)
        assert result.trailer() == "The proof construction on `theory_X.lemma_P` is still running."
        assert [m.text for m in me.mailbox] == ["note", "urgent"]
        # a message that no longer stands does not return the call
        other = Agent("a9f3c2d1e4b5", False)
        me.mailbox.clear()
        await asked(n(Q).job(), other)
        n(Q).job().cancel(None)                                     # the question is now nobody's
        me.mailbox.extend(other.mailbox)
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        task.cancel()
        await settled(f)
    tm.run(scenario())


def test_check_construct_delivers_a_pending_question_again():
    """Condition 2: a construction job of the caller's waits for an answer
    — the call returns at once, the question put back into the mailbox
    when it is no longer there, one entry per job at most."""
    async def scenario():
        f, tools, n = theories()
        me = Agent("main", True)
        check = tools["check_construct"]
        job = n(P).job()
        await asked(job, me)
        result = await returned(calling(check, me, wait_seconds=3600))
        assert [m.question for m in me.mailbox] == [job.pending_question]   # there already: not posted again
        assert result.trailer() == "The proof construction on `theory_X.lemma_P` is waiting for your answer."
        assert jobs.deliver(f.conversation.log, me) == [job.question_message(job.pending_question)]
        assert me.mailbox == []
        await returned(calling(check, me, wait_seconds=3600))
        assert [m.question for m in me.mailbox] == [job.pending_question]   # put back
        await returned(calling(check, me, wait_seconds=3600))
        assert len(me.mailbox) == 1
        # another agent's question holds nothing for the caller
        other = Agent("a9f3c2d1e4b5", False)
        await asked(n(Q).job(), other)
        job.receive_answer({"verdict": "accept"})
        await until(me, lambda: job.outcome is not RUNNING)
        me.mailbox.clear()
        n(R).job().start(me)
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        task.cancel()
        await settled(f)
    tm.run(scenario())


def test_check_construct_returns_once_a_title_of_the_callers_has_no_job_left():
    """Condition 3: since the call started a job of the caller's ended —
    here silently, a run cancelled by `cancel_construct`'s cancel and a
    check reported passing — and none of its title is left running; the
    trailer then says `All … have finished.` for the title, under the
    state lines of what stands.  A settlement returns the call by its
    notification, which interrupts.  Another agent's job counts for
    nothing."""
    async def scenario():
        f, tools, n = theories()
        me, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)
        check = tools["check_construct"]
        p, q, s, t = n(P), n(Q), n(S), n(T_)
        p.job().start(me)
        q.job().start(me)
        await s.start_evaluation_job(me)
        await t.start_evaluation_job(me)
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        p.job().cancel(None)
        await still_waiting(task)                                 # Q, of the same title, still runs
        await report(s.evaluation_job())
        await still_waiting(task)                                 # T's check, of the same title, still runs
        q.job().cancel(None)
        result = await returned(task)
        assert result.trailer() == ("The proof check on `theory_Y.lemma_T` is still running.\n"
                                    "All proof constructions have finished.")
        assert me.mailbox == []
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        await report(t.evaluation_job())
        result = await returned(task)
        assert result.trailer() == "All proof checks have finished."
        p.job().start(me)
        q.job().start(me)
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        p.job().release.set()                                     # P settles: its notification interrupts
        result = await returned(task)
        assert result.trailer() == "The proof construction on `theory_X.lemma_Q` is still running."
        assert [m.text for m in me.mailbox] == ["The proof construction on `theory_X.lemma_P` succeeded."]
        me.mailbox.clear()
        n(R).job().start(other)
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        n(R).job().cancel(None)
        await still_waiting(task)
        task.cancel()
        await settled(f)
    tm.run(scenario())


def test_check_construct_s_all_finished_lines_construction_titles_first():
    """CONSTRUCT_INTERACTION §5: one `All … have finished.` line per title
    the caller had a job of and has none of, construction titles first,
    then evaluation titles — here both titles ending in one wake of the
    call, the check reported before the construction was cancelled."""
    async def scenario():
        f, tools, n = theories()
        me = Agent("main", True)
        p, t = n(P), n(T_)
        p.job().start(me)
        await t.start_evaluation_job(me)
        task = calling(tools["check_construct"], me, wait_seconds=3600)
        await still_waiting(task)
        await report(t.evaluation_job())
        p.job().cancel(None)
        result = await returned(task)
        assert result.trailer() == "All proof constructions have finished.\nAll proof checks have finished."
        await settled(f)
    tm.run(scenario())


def test_check_construct_s_deadline_and_its_two_clamps(monkeypatch):
    """Condition 4: the deadline, a return of the same shape as any other;
    `wait_seconds` clamped silently to at least 3 seconds and to a minute
    under the client's twelve-hour limit."""
    async def scenario():
        f, tools, n = theories()
        me = Agent("main", True)
        check = tools["check_construct"]
        n(P).job().start(me)
        with monkeypatch.context() as m:
            m.setattr(mcp, "WAIT_AT_LEAST", 0.05)
            started = asyncio.get_running_loop().time()
            result = await returned(calling(check, me, wait_seconds=0))
            assert 0.05 <= asyncio.get_running_loop().time() - started < 1.0
        assert result.trailer() == "The proof construction on `theory_X.lemma_P` is still running."
        deadlines = []
        original = asyncio.wait_for

        async def recording(awaitable, timeout):
            deadlines.append(timeout)
            return await original(awaitable, timeout)
        jobs.post(f.conversation.log, Message(me, "urgent", interrupts=True))     # holds at once: no waiting
        with monkeypatch.context() as m:
            m.setattr(asyncio, "wait_for", recording)
            for seconds in (0, 2, 3, 7, 12 * 3600 - 60, 12 * 3600, 10 ** 9):
                await check.run(me, {"wait_seconds": seconds})
        assert deadlines == [3, 3, 3, 7, 12 * 3600 - 60, 12 * 3600 - 60, 12 * 3600 - 60]
        await settled(f)
    tm.run(scenario())


def test_check_construct_s_state_lines_in_every_form():
    """The state lines (CONSTRUCT_INTERACTION §5): the caller's jobs by
    title and situation — construction titles first, each one's waiting
    then running, then evaluation titles, alphabetical within — up to
    three nodes as one sentence, more as a header over one full id per
    line (the fenced list); no quickview."""
    async def scenario():
        f, tools, n = theories()
        me, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)
        check = tools["check_construct"]
        jobs.post(f.conversation.log, Message(me, "urgent", interrupts=True))     # every call returns at once

        async def lines() -> list[str]:
            return (await returned(calling(check, me, wait_seconds=3600))).trailer().splitlines()
        for id in (Q, R, S, T_):
            n(id).job().start(me)
        assert await lines() == fenced_blocks(CI, "5.")[3] == [
            "The following proof constructions are still running:",
            "  - theory_X.lemma_Q", "  - theory_X.lemma_R", "  - theory_Y.lemma_S", "  - theory_Y.lemma_T"]
        for id in (Q, R):
            n(id).job().cancel(None)
            await asked(n(id).job(), me)
        await asked(n(P).job(), other)                            # another agent's: not the caller's
        for id in (P, Q, R):
            await n(id).start_evaluation_job(me)
        n(SEARCHED).job().start(me)
        assert await lines() == [
            "The counterexample search on `theory_Y.searched_V` is still running.",
            "The proof construction on `theory_X.lemma_Q` and on `theory_X.lemma_R` is waiting for your answer.",
            "The proof construction on `theory_Y.lemma_S` and on `theory_Y.lemma_T` is still running.",
            "The proof check on `theory_X.lemma_P`, on `theory_X.lemma_Q` and on `theory_X.lemma_R`"
            " is still running."]
        for id in (S, T_):
            n(id).job().cancel(None)
            await asked(n(id).job(), me)
        assert await lines() == [
            "The counterexample search on `theory_Y.searched_V` is still running.",
            "The following proof constructions are waiting for your answer:",
            "  - theory_X.lemma_Q", "  - theory_X.lemma_R", "  - theory_Y.lemma_S", "  - theory_Y.lemma_T",
            "The proof check on `theory_X.lemma_P`, on `theory_X.lemma_Q` and on `theory_X.lemma_R`"
            " is still running."]
        await settled(f)
    tm.run(scenario())


def test_answer_s_four_refusals_and_its_results():
    """CONSTRUCT_INTERACTION §5: refused when no question of a run of the
    caller's waits on the node — no job, a job not running, a run that
    asked nothing (`NoQuestionPending`) — when the question is another
    agent's (`ConstructOwnedByAnother`), when the answer fails the pending
    question's schema in `answer`'s place (the checker's sentence), or
    when `receive` refuses it (`BadAnswer`); accepted, the question's
    response, by default `answered_notice`; `receive` asking instead, an
    empty result and the new question posted.  No quickview.  The first
    two refusals' lines are RENDER_BASELINES §2's."""
    async def scenario():
        f, tools, n = theories()
        me, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)
        answer = tools["answer"]
        causes = fenced_lines(RB, "2.")

        async def refused(cls, caller, **arguments):
            with pytest.raises(cls) as e:
                await answer.run(caller, arguments)
            return e.value, str(e.value).splitlines()
        e, lines = await refused(NoQuestionPending, me, node_id="theory_X.definition_f", answer={})
        assert e.id == "theory_X.definition_f"
        assert lines == ["`theory_X.definition_f` has no question waiting for an answer."] and lines[0] in causes
        job = n(P).job()
        e, _ = await refused(NoQuestionPending, me, node_id=P, answer={"verdict": "accept"})
        job.start(me)
        e, _ = await refused(NoQuestionPending, me, node_id=P, answer={"verdict": "accept"})
        assert e.id == P and job.outcome is RUNNING
        job.cancel(None)
        await asked(job, me)
        e, lines = await refused(ConstructOwnedByAnother, other, node_id=P, answer={"verdict": "accept"})
        assert (e.id, e.refusal) == (P, "The proof construction on `theory_X.lemma_P` belongs to another agent.")
        assert lines == [e.refusal] and lines[0] in causes
        e, lines = await refused(InvalidField, me, node_id=P, answer={"verdict": "maybe"})
        assert (e.field, e.of_tool) == ("answer.verdict", True)
        assert lines == ["The argument `answer.verdict` must be one of `accept`, `reject`."]
        e, _ = await refused(MissingField, me, node_id=P, answer={})
        assert (e.holder, e.field, e.of_tool) == ("answer", "answer.verdict", True)
        e, _ = await refused(UnexpectedField, me, node_id=P, answer={"verdict": "accept", "x": 1})
        assert (e.holder, e.field, e.holder_is_top) == ("answer", "x", False)
        assert isinstance(job.pending_question, test_jobs.Verdict)
        assert await answer.run(me, {"node_id": P, "answer": {"verdict": "reject"}}) == ""
        assert isinstance(job.pending_question, test_jobs.Why)
        assert me.mailbox[-1].question is job.pending_question
        e, lines = await refused(BadAnswer, me, node_id=P, answer={"reason": ""})
        assert lines == ["A rejection needs a reason."] and isinstance(job.pending_question, test_jobs.Why)
        assert await answer.run(me, {"node_id": P, "answer": {"reason": "too long"}}) == "Noted."
        await until(me, lambda: job.outcome is not RUNNING)
        assert job.outcome == Succeeded("by simp") and job.pending_question is None
        await asked(n(Q).job(), me)
        assert await answer.run(me, {"node_id": Q, "answer": {"verdict": "accept"}}) == (
            "Answered the proof construction on `theory_X.lemma_Q`; call `check_construct` before you exit.")
        # malformed, against the advertised schema: `answer` a bare object
        e, _ = await refused(MissingField, me, node_id=P)
        assert (e.holder, e.field) == ("answer", "answer")
        e, _ = await refused(InvalidField, me, node_id=P, answer="yes")
        assert (e.field, e.reason) == ("answer", "must be an object")
        e, _ = await refused(NodeNotFound, me, node_id="theory_X.lemma_Z", answer={})
        assert e.id == "theory_X.lemma_Z"
        await settled(f)
    tm.run(scenario())


# --- from the review of steps 10–11 (§3's surviving mutations) -----------------

def test_check_construct_counts_no_job_of_another_agent_s_ended():
    """CONSTRUCT_INTERACTION §5 condition 3 and the `All … have finished.`
    line: a job of the caller's; another agent's construction ending, a
    title the caller never had, neither returns the call nor is named."""
    async def scenario():
        f, tools, n = theories()
        me, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)
        check = tools["check_construct"]
        n(P).job().start(other)
        await n(P).start_evaluation_job(me)
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        n(P).job().cancel(None)                                    # another agent's: counts for nothing
        await still_waiting(task)
        await report(n(P).evaluation_job())
        result = await returned(task)
        assert result.trailer() == "All proof checks have finished."
        await settled(f)
    tm.run(scenario())


def test_check_construct_counts_a_job_started_during_the_call():
    """CONSTRUCT_INTERACTION §5: condition 3 and the `All …` line count the
    titles the caller had a job of during the call — a job started after
    the call began included."""
    async def scenario():
        f, tools, n = theories()
        me = Agent("main", True)
        check = tools["check_construct"]
        n(P).job().start(me)
        task = calling(check, me, wait_seconds=3600)
        await still_waiting(task)
        await n(Q).start_evaluation_job(me)                        # started during the call
        await still_waiting(task)
        await report(n(Q).evaluation_job())
        result = await returned(task)
        assert result.trailer() == ("The proof construction on `theory_X.lemma_P` is still running.\n"
                                    "All proof checks have finished.")
        await settled(f)
    tm.run(scenario())


def test_auto_construct_is_written_on_the_nodes_the_call_skipped_too():
    """CONSTRUCT_INTERACTION §5: on each node of the call `auto_construct`
    is written as the call gives it — one running under another agent and
    one whose class's condition fails included — and stored; on
    `cancel_construct`'s nodes with no run too."""
    async def scenario():
        f, tools, n = theories()
        me, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)
        n(P).job().start(other)
        await tools["construct"].run(me, {"node_ids": [P, U], "auto_construct": True})
        for id in (P, U):
            assert n(id).job().auto_construct is True and f.store.get(n(id).identity, "auto_construct") is True
        assert n(P).job().owner is other and n(U).job().outcome is NOT_STARTED
        await tools["cancel_construct"].run(me, {"node_ids": [U], "auto_construct": False})
        assert n(U).job().auto_construct is False and f.store.get(n(U).identity, "auto_construct") is False
        await settled(f)
    tm.run(scenario())


def test_answer_on_another_agent_s_run_that_asked_nothing_is_no_question_pending():
    """CONSTRUCT_INTERACTION §5: a run that has asked nothing is
    `NoQuestionPending`, whoever owns it; `ConstructOwnedByAnother` is for
    a question that is another agent's."""
    async def scenario():
        f, tools, n = theories()
        me, other = Agent("main", True), Agent("a9f3c2d1e4b5", False)
        n(P).job().start(other)
        with pytest.raises(NoQuestionPending) as e:
            await tools["answer"].run(me, {"node_id": P, "answer": {"verdict": "accept"}})
        assert e.value.id == P and n(P).job().outcome is RUNNING
        await settled(f)
    tm.run(scenario())
