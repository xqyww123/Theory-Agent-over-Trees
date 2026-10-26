"""A forest of the plugin `Isabelle_Std`'s classes against the fake state
slot table (not a pytest module): the kind table of the fake framework
classes and every class the plugin registers, and the seven helpers the
plugin's test modules share — `insert`, `forest`, `inv`, `refused`,
`field_check`, `reloaded`, `assert_a_missing_row_is_refused_at_start`.
A new class of the plugin adds its kinds here."""

import pytest

import test_model as tm
import test_session_theory as ts
from invariants import assert_invariants, assert_store_mirrors
from isabelle_theory_agent import edit
from isabelle_theory_agent.exceptions import InvalidField, TAT_StartupError
from isabelle_theory_agent.std import (
    datatype, define, lift_definition, lifting_context, quotient_type, record, theorem, typedef)
from isabelle_theory_agent.store import Forest_Store
from test_model import locked, run
from test_session_theory import Forest_Under_Test, session, theory

KINDS = {**ts.KINDS,
         **{kind: theorem.Theorem for kind in theorem.KINDS},
         **{kind: datatype.Datatype for kind in datatype.KINDS},
         **{kind: record.Record for kind in record.KINDS},
         **{kind: define.Define for kind in define.KINDS},
         **{kind: typedef.Typedef for kind in typedef.KINDS},
         **{kind: lift_definition.LiftDefinition for kind in lift_definition.KINDS},
         **{kind: lifting_context.LiftingContext for kind in lifting_context.KINDS},
         **{kind: quotient_type.QuotientType for kind in quotient_type.KINDS}}


def insert(f, parent, index, raws):
    return run(locked(f, edit.insert(parent, index, raws)))


def forest(*constructs, store=None, kinds=KINDS):
    """session_Arith > theory_X > the constructs; the forest and the theory."""
    f = Forest_Under_Test(store=store, kinds=kinds)
    (s,) = insert(f, f, 0, [session("Arith", theory("X") | {"children": list(constructs)})])
    return f, s.sub_nodes[0]


def inv(f):
    assert_invariants(f, tm.TABLE)
    assert_store_mirrors(f, shape=ts.shape)


def refused(f, parent, raws, cls):
    with pytest.raises(cls) as e:
        insert(f, parent, 0, raws)
    return e.value


def field_check(f, parent, raws) -> InvalidField | None:
    """The field check (PLUGIN_SYSTEM §2) of the one construct in `raws`,
    inserted at the front of `parent` — which the edit accepts — and
    deleted after: the `InvalidField` its `check_fields` raises, or None."""
    (node,) = insert(f, parent, 0, raws)
    try:
        node.check_fields()
    except InvalidField as e:
        return e
    finally:
        run(locked(f, edit.delete(node)))
    return None


def reloaded(path, *constructs, kinds=KINDS) -> tuple[list, list]:
    """The constructs inserted under `forest()`'s theory, stored at `path`,
    and the store reopened: the nodes inserted and the nodes loaded, in
    order."""
    f, x = forest(*constructs, store=Forest_Store(path, ts.stand_ins.log()), kinds=kinds)
    with f.store.transaction():
        for n in x.sub_nodes:
            f._store_node(n)
    f.store.close()
    f2 = Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=kinds)
    f2.store.close()
    return x.sub_nodes, f2.sub_nodes[0].sub_nodes[0].sub_nodes


def assert_a_missing_row_is_refused_at_start(path, identity, fields, kinds=KINDS):
    """A class's rows are read with `get`: the store at `path` reopened with
    one of the node's `fields` missing is refused at start with
    `TAT_StartupError` naming the row, each field in turn, the row put back
    after each."""
    for field in fields:
        store = Forest_Store(path, ts.stand_ins.log())
        rows = store.fields(identity)
        with store.transaction():
            store.delete_node(identity)
            for name, value in rows.items():
                if name != field:
                    store.put(identity, name, value)
        store.close()
        with pytest.raises(TAT_StartupError, match=field):
            Forest_Under_Test(store=Forest_Store(path, ts.stand_ins.log()), kinds=kinds)
        store = Forest_Store(path, ts.stand_ins.log())
        with store.transaction():
            store.put(identity, field, rows[field])
        store.close()
