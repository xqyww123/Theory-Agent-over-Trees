"""The Python half of test/Test_TAT_Framework.thy.

`TAT_Framework.start' "TAT_test.drive" \\<^theory>` on the ML side calls the
procedure below, which drives the session's state slot table through the
framework's callbacks and the three callbacks the test theory registered.
An assertion failure travels back as the error of the ML call, so the
theory fails to evaluate exactly when the test fails.

`TAT_test.make` stores one of two distinguishable states — `top=True` a
toplevel state, `top=False` a theory state — and `TAT_test.is_toplevel`
reads the stored state's discriminator back, so a copy that fabricated a
state instead of mirroring the source would be caught.
"""

from Isabelle_RPC_Host import Connection, IsabelleError, isabelle_remote_procedure

from isabelle_theory_agent import isabelle_driver
from isabelle_theory_agent.model import Isar_State_Slot


@isabelle_remote_procedure("TAT_test.drive")
async def drive(_: None, connection: Connection) -> None:
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

    # get on an empty slot is an error, and it travels back as an exception
    try:
        await is_toplevel(c)
        raise AssertionError("get on an empty slot did not error")
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
