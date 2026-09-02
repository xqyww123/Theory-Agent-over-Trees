"""The node class table (MODULE_STRUCTURE §4.3).
Run: python -m pytest test/test_plugin.py
"""

import sys
import types

try:
    import Isabelle_RPC_Host  # noqa: F401
except ImportError:                       # the test needs no Isabelle
    m = types.ModuleType("Isabelle_RPC_Host")
    m.Connection = object  # type: ignore[attr-defined]
    sys.modules["Isabelle_RPC_Host"] = m

import pytest

from isabelle_theory_agent import model as M, plugin
from isabelle_theory_agent.exceptions import TAT_InternalError


@pytest.fixture(autouse=True)
def fresh_table(monkeypatch):
    monkeypatch.setattr(plugin, "kinds", {})


class L(M.Leaf):
    def is_finished(self): return False
    async def _eval_opr(self): return True


def test_one_class_registers_every_kind_it_answers_to():
    cls = plugin.TAT_node(["lemma", "theorem", "corollary"])(L)
    assert cls is L
    assert plugin.kinds == {"lemma": L, "theorem": L, "corollary": L}
    assert list(plugin.kinds) == ["lemma", "theorem", "corollary"]


def test_a_kind_has_one_class():
    plugin.TAT_node(["lemma"])(L)
    with pytest.raises(TAT_InternalError):
        plugin.TAT_node(["lemma"])(L)


def test_output_omissible_but_input_compulsory_is_rejected():
    class Bad(L):
        output_omissible = True            # input_omissible stays False
    with pytest.raises(TAT_InternalError):
        plugin.TAT_node(["bad"])(Bad)
    class Fine(L):
        output_omissible = input_omissible = True
    plugin.TAT_node(["fine"])(Fine)
    class AlsoFine(L):
        input_omissible = True             # printed always, droppable on input
    plugin.TAT_node(["also_fine"])(AlsoFine)


def test_load_imports_and_the_import_registers(tmp_path, monkeypatch):
    (tmp_path / "fake_tat_pkg.py").write_text(
        "from isabelle_theory_agent import model, plugin\n"
        "@plugin.TAT_node(['fake'])\n"
        "class Fake(model.Leaf):\n"
        "    def is_finished(self): return False\n"
        "    async def _eval_opr(self): return True\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    plugin.load(["fake_tat_pkg"])
    assert list(plugin.kinds) == ["fake"]
