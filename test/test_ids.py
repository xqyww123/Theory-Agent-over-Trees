"""Ids: the name grammar, resolution and shortest-form printing
(MCP_SPECIFICATION §2, §2.1), on the doc's own example
`session_Arith.theory_X.section_Basics.lemma_P`.
Run: python -m pytest test/test_ids.py
"""

import typing
from pathlib import Path

import pytest

from isabelle_theory_agent import model as M
from isabelle_theory_agent.exceptions import AmbiguousId, NodeNotFound
from isabelle_theory_agent.model import Isar_State_Slot, is_valid_name
from isabelle_theory_agent.store import Forest_Store

CONN = typing.cast(typing.Any, object())


def slot(): return Isar_State_Slot.assign(CONN)


# --- stub node classes: ids need no evaluation ------------------------------

class Stub:
    def to_store(self, rows): rows.put("name", self.name)
    def __repr__(self): return self.name

class Thm(Stub, M.Leaf):                  # compulsory in both directions
    @classmethod
    def from_store(cls, config, rows):
        n = cls(config.parent, config.state); n.name = rows.get("name"); return n
    async def _eval_opr(self): raise NotImplementedError

class Sec(Stub, M.StdBlock):
    output_omissible = input_omissible = True
    drop_priority = 0
    @classmethod
    def from_store(cls, config, rows):
        n = cls(config.parent, config.state, [], slot()); n.name = rows.get("name"); return n
    async def _eval_beginning_opr(self): raise NotImplementedError

class Sess(Sec):
    drop_priority = 1

class Thy(Sec):
    drop_priority = 2

# the kinds of the doc's example; a kind prefixes the name in the id
KINDS = {"lemma": Thm, "section": Sec, "session": Sess, "theory": Thy}
KIND_OF = {cls: kind for kind, cls in KINDS.items()}


def enter(parent, n, kind):
    """Set what the framework sets on a node entering the forest, and store it."""
    f = parent.forest()
    n.parent, n.kind, n.identity = parent, kind, f.store.next_identity()
    parent.sub_nodes.append(n)
    with f.store.transaction():
        f._store_node(n); f._store_children(parent)
    return n

def mk_leaf(parent, name):
    n = Thm(parent, slot()); n.name = name
    return enter(parent, n, "lemma")

def mk_block(cls, parent, name):
    n = cls(parent, slot(), [], slot()); n.name = name
    return enter(parent, n, KIND_OF[cls])


def new_forest(store=None):
    return M.Forest(M.Conversation(CONN, Path(".")),       # nothing here touches the directory
                    store if store is not None else Forest_Store(":memory:"), KINDS)


@pytest.fixture
def forest():
    f = new_forest()
    arith = mk_block(Sess, f, "Arith")
    x = mk_block(Thy, arith, "X")
    basics = mk_block(Sec, x, "Basics")
    p = mk_leaf(basics, "P")
    return f, arith, x, basics, p


# --- printing ---------------------------------------------------------------

def test_the_id_component_is_the_kind_and_the_name(forest):
    f, arith, x, basics, p = forest
    assert p.name == "P" and p.id_component() == "lemma_P"
    assert arith.id_component() == "session_Arith"

def test_shortest_form_when_unique(forest):
    f, arith, x, basics, p = forest
    assert f.id_of(p) == "lemma_P"
    assert f.id_of(basics) == "section_Basics"      # its own component stays
    assert f.id_of(x) == "theory_X"
    assert f.id_of(arith) == "session_Arith"
    assert f.id_of(f) == "Sessions"

def test_printing_stops_at_the_first_collision(forest):
    f, arith, x, basics, p = forest
    y = mk_block(Thy, arith, "Y")
    mk_leaf(y, "P")
    # Section (priority 0) and Session (1) go; Theory (2) can no longer.
    assert f.id_of(p) == "theory_X.lemma_P"

def test_drop_order_is_by_priority_then_outermost(forest):
    f, arith, x, basics, p = forest
    # A second lemma_P under theory_X itself: dropping section_Basics from
    # p's id is now ambiguous, so the section stays while Session and
    # Theory — droppable in priority order — both go.
    mk_leaf(x, "P")
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
    assert f.resolve("Sessions") is f
    assert f.resolve("section_Basics") is basics

def test_exact_full_id_wins_over_a_drop_match(forest):
    f, arith, x, basics, p = forest
    q = mk_leaf(x, "P")
    # "session_Arith.theory_X.lemma_P" is q's full id and also p's
    # section-dropped form: the exact match wins (MCP_SPECIFICATION §2.1),
    # so every id TAT prints resolves back to the node it was printed for.
    assert f.resolve("session_Arith.theory_X.lemma_P") is q
    assert f.id_of(q) == "session_Arith.theory_X.lemma_P"
    assert f.resolve(f.id_of(q)) is q and f.resolve(f.id_of(p)) is p
    with pytest.raises(AmbiguousId):        # a form that is nobody's full id
        f.resolve("lemma_P")

def test_ambiguous_id_lists_candidates_in_tree_order(forest):
    f, arith, x, basics, p = forest
    y = mk_block(Thy, arith, "Y")
    mk_leaf(y, "P")
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
    inner = mk_block(Sec, basics, "Basics")
    with pytest.raises(AmbiguousId):
        f.resolve("section_Basics")
    assert f.resolve("section_Basics.section_Basics") is inner
    assert f.id_of(inner) == "section_Basics.section_Basics"
    # the outer section's shortest form is its full id, which its inner
    # namesake also matches by dropping — the exact match wins
    assert f.resolve(f.id_of(basics)) is basics


# --- the name grammar -------------------------------------------------------

def test_name_grammar():
    for good in ("P", "HOL-Library", "x'", "a_b", "T2", "a'b-c_d'", "Sessions"):
        assert is_valid_name(good), good      # `Sessions` too: an id component always has an underscore
    for bad in ("Ch. 2 lemmas", "", "a_", "a-", "-a", "_a", "1a", "a.b", "a b"):
        assert not is_valid_name(bad), bad


# --- identity and position --------------------------------------------------

def test_index_of_and_identity(forest):
    f, arith, x, basics, p = forest
    assert basics.index_of() == 0 and x.index_of() == 0
    q = mk_leaf(basics, "Q")
    assert q.index_of() == 1
    assert q.identity > p.identity > x.identity     # creation order, opaque

def test_identity_and_ids_survive_a_reload(forest):
    f, arith, x, basics, p = forest
    mk_leaf(x, "P")                          # the section can no longer be dropped
    loaded = new_forest(f.store)             # the same database, read again
    reloaded_p = loaded.sub_nodes[0].sub_nodes[0].sub_nodes[0].sub_nodes[0]
    assert reloaded_p.identity == p.identity
    assert loaded.id_of(reloaded_p) == f.id_of(p) == "section_Basics.lemma_P"
    assert loaded.resolve("session_Arith.theory_X.lemma_P") is not reloaded_p
    fresh = mk_leaf(loaded.sub_nodes[0].sub_nodes[0], "R")
    assert fresh.identity not in {n.identity for n in loaded._all_nodes() if n is not fresh}
