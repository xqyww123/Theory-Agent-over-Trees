"""Ids: the name grammar, resolution and shortest-form printing
(MCP_SPECIFICATION §2, §2.1), on the doc's own example
`session_Arith.theory_X.section_Basics.lemma_P`.
Run: python -m pytest test/test_ids.py
"""

import pickle
import sys
import types
import typing

try:
    import Isabelle_RPC_Host  # noqa: F401
except ImportError:                       # the test needs no Isabelle
    m = types.ModuleType("Isabelle_RPC_Host")
    m.Connection = object  # type: ignore[attr-defined]
    sys.modules["Isabelle_RPC_Host"] = m

import pytest

from isabelle_theory_agent import model as M
from isabelle_theory_agent.exceptions import AmbiguousId, NodeNotFound
from isabelle_theory_agent.model import Isar_State_Slot, is_valid_name

CONN = typing.cast(typing.Any, object())


def slot(): return Isar_State_Slot.assign(CONN)


# --- stub node classes: ids need no evaluation ------------------------------

class Stub:
    def is_finished(self): return False
    def __repr__(self): return self.name

class Thm(Stub, M.Leaf):                  # compulsory in both directions
    async def _eval_opr(self): raise NotImplementedError

class Sec(Stub, M.StdBlock):
    output_omissible = input_omissible = True
    drop_priority = 0
    async def _eval_beginning_opr(self): raise NotImplementedError

class Sess(Sec):
    drop_priority = 1

class Thy(Sec):
    drop_priority = 2


def mk_leaf(parent, name):
    n = Thm(parent, slot()); n.name = name
    parent.sub_nodes.append(n); return n

def mk_block(cls, parent, name):
    n = cls(parent, slot(), [], slot()); n.name = name
    parent.sub_nodes.append(n); return n


@pytest.fixture
def forest():
    f = M.Forest(slot(), [])
    arith = mk_block(Sess, f, "session_Arith")
    x = mk_block(Thy, arith, "theory_X")
    basics = mk_block(Sec, x, "section_Basics")
    p = mk_leaf(basics, "lemma_P")
    return f, arith, x, basics, p


# --- printing ---------------------------------------------------------------

def test_shortest_form_when_unique(forest):
    f, arith, x, basics, p = forest
    assert f.id_of(p) == "lemma_P"
    assert f.id_of(basics) == "section_Basics"      # its own component stays
    assert f.id_of(x) == "theory_X"
    assert f.id_of(arith) == "session_Arith"
    assert f.id_of(f) == "$Root"

def test_printing_stops_at_the_first_collision(forest):
    f, arith, x, basics, p = forest
    y = mk_block(Thy, arith, "theory_Y")
    mk_leaf(y, "lemma_P")
    # Section (priority 0) and Session (1) go; Theory (2) can no longer.
    assert f.id_of(p) == "theory_X.lemma_P"

def test_drop_order_is_by_priority_then_outermost(forest):
    f, arith, x, basics, p = forest
    # A second lemma_P under theory_X itself: dropping section_Basics from
    # p's id is now ambiguous, so the section stays while Session and
    # Theory — droppable in priority order — both go.
    mk_leaf(x, "lemma_P")
    assert f.id_of(p) == "section_Basics.lemma_P"


# --- reading ----------------------------------------------------------------

def test_reading_accepts_every_omissible_drop(forest):
    f, arith, x, basics, p = forest
    for form in ("session_Arith.theory_X.section_Basics.lemma_P",
                 "theory_X.section_Basics.lemma_P",
                 "theory_X.lemma_P",
                 "section_Basics.lemma_P",
                 "session_Arith.lemma_P",
                 "lemma_P"):
        assert f.resolve(form) is p
    assert f.resolve("$Root") is f
    assert f.resolve("section_Basics") is basics

def test_ambiguous_id_lists_candidates_in_tree_order(forest):
    f, arith, x, basics, p = forest
    y = mk_block(Thy, arith, "theory_Y")
    mk_leaf(y, "lemma_P")
    with pytest.raises(AmbiguousId) as e:
        f.resolve("lemma_P")
    assert e.value.id == "lemma_P"
    assert e.value.candidates == ["theory_X.lemma_P", "theory_Y.lemma_P"]

def test_not_found_guesses_close_ids(forest):
    f, arith, x, basics, p = forest
    with pytest.raises(NodeNotFound) as e:
        f.resolve("lemma_fo")
    assert e.value.id == "lemma_fo" and "lemma_P" in e.value.near_matches

def test_a_dropped_component_must_be_input_omissible(forest):
    f, arith, x, basics, p = forest
    # Thm is compulsory: an id skipping over it never matches anything, and
    # a wrong interior component does not resolve.
    with pytest.raises(NodeNotFound):
        f.resolve("theory_Y.lemma_P")

def test_nested_same_name(forest):
    f, arith, x, basics, p = forest
    inner = mk_block(Sec, basics, "section_Basics")
    with pytest.raises(AmbiguousId):
        f.resolve("section_Basics")
    assert f.resolve("section_Basics.section_Basics") is inner
    assert f.id_of(inner) == "section_Basics.section_Basics"


# --- the name grammar -------------------------------------------------------

def test_name_grammar():
    for good in ("lemma_P", "HOL-Library", "x'", "a_b", "T2", "a'b-c_d'"):
        assert is_valid_name(good), good
    for bad in ("Ch. 2 lemmas", "", "a_", "a-", "-a", "_a", "1a", "a.b",
                "$Root", "a b"):
        assert not is_valid_name(bad), bad


# --- identity and position --------------------------------------------------

def test_index_of_and_identity(forest):
    f, arith, x, basics, p = forest
    assert basics.index_of() == 0 and x.index_of() == 0
    q = mk_leaf(basics, "lemma_Q")
    assert q.index_of() == 1
    assert q.identity > p.identity > x.identity     # creation order, opaque

def test_identity_survives_pickling_and_counter_moves_past_it(forest, monkeypatch):
    f, arith, x, basics, p = forest
    frozen = pickle.dumps(arith)
    monkeypatch.setattr(M.Node, "_identity_counter", 0)   # a fresh process
    thawed = pickle.loads(frozen)
    reloaded_p = thawed.sub_nodes[0].sub_nodes[0].sub_nodes[0]
    assert reloaded_p.identity == p.identity
    fresh = Thm(thawed.sub_nodes[0].sub_nodes[0], slot())
    loaded = {n.identity for n in [thawed] + M._tree_order(thawed)}
    assert fresh.identity not in loaded                   # no collision
