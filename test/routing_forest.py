"""A test double for the forest walk (not a pytest module): enough of
`Forest._evaluate` to drive `Session` and `Theory` before the plan's §7
step 4 writes the real one.  A walk is routed to the one tree holding its
destination — an evaluating walk's node, an invalidate-only walk's position —
and a position under the root or a `Session` walks nothing.  The scheduling
of imports and the stops across trees (the plan's §6) are step 4's."""

import isabelle_theory_agent.model as M
from isabelle_theory_agent.model import Evaluating, Session


class Routing_Forest(M.Forest):

    async def _evaluate(self, ev, mode):
        node = ev.destination if isinstance(mode, Evaluating) else mode.destination.parent
        while not isinstance(node, M.Unchained_Node):
            if isinstance(node.parent, Session):
                return await node._evaluate(ev, mode)
            node = node.parent
        return M.EvaluationResult(None, M.INVALIDATING)
