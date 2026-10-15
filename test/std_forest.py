"""A forest of the plugin `Isabelle_Std`'s classes against the fake state
slot table (not a pytest module): the kind table of the fake framework
classes and every class the plugin registers, and the four helpers the
plugin's test modules share — `insert`, `forest`, `inv`, `refused`.  A
new class of the plugin adds its kinds here."""

import pytest

import test_model as tm
import test_session_theory as ts
from invariants import assert_invariants, assert_store_mirrors
from isabelle_theory_agent import edit
from isabelle_theory_agent.std import datatype, theorem, typedef
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory

KINDS = {**ts.KINDS,
         **{kind: theorem.Theorem for kind in theorem.KINDS},
         **{kind: datatype.Datatype for kind in datatype.KINDS},
         **{kind: typedef.Typedef for kind in typedef.KINDS}}


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws, KINDS)))


def forest(*constructs, store=None):
    """session_Arith > theory_X > the constructs; the forest and the theory."""
    f = Forest_Under_Test(store=store, kinds=KINDS)
    (s,) = insert(f, f, 0, [session("Arith", theory("X") | {"children": list(constructs)})])
    return f, s.sub_nodes[0]


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, KINDS, shape=ts.shape)


def refused(f, parent, raws, cls):
    with pytest.raises(cls) as e:
        insert(f, parent, 0, raws)
    return e.value
