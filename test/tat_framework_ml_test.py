"""The Python half of test/TAT_Framework_Test.thy.

`TAT_Framework.start' "TAT_test.drive"` on the ML side calls the procedure
below, which drives the session's state slot table through the framework's
callbacks and the two callbacks the test theory registered.  An assertion
failure travels back as the error of the ML call, so the theory fails to
evaluate exactly when the test fails.
"""

from Isabelle_RPC_Host import Connection, IsabelleError, isabelle_remote_procedure

from isabelle_theory_agent import isabelle_driver
from isabelle_theory_agent.model import Isar_State_Slot


@isabelle_remote_procedure("TAT_test.drive")
async def drive(_: None, connection: Connection) -> None:
    a = Isar_State_Slot.assign(connection)
    b = Isar_State_Slot.assign(connection)
    c = Isar_State_Slot.assign(connection)

    # a fresh slot holds nothing
    assert not await a.is_initialized()

    # a node-class callback writes it through the env's slot_unpacker
    await connection.callback("TAT_test.make", a.to_msgpack())
    assert await a.is_initialized()
    assert await connection.callback("TAT_test.is_toplevel", a.to_msgpack())

    # copy: the target mirrors the source
    await a.copy_to(b)
    assert await b.is_initialized()

    # get on an empty slot is an error, and it travels back as an exception
    try:
        await connection.callback("TAT_test.is_toplevel", c.to_msgpack())
        raise AssertionError("get on an empty slot did not error")
    except IsabelleError as e:
        assert "holds no state" in str(e), str(e)

    # copy from an empty slot: the target mirrors the absence
    await c.copy_to(b)
    assert not await b.is_initialized()

    # delete, single and batched; deleting an absent name is not an error
    await a.delete()
    assert not await a.is_initialized()
    await isabelle_driver.delete_states(connection, [a.name, b.name, c.name])
