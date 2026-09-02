#!/usr/bin/env python
"""Runs the ML framework test (Test_TAT_Framework.thy + tat_framework_ml_test.py).

    python test/run_ml_framework_test.py [ADDR]

With no ADDR it starts an Isa-REPL server itself (repl_server.sh, base
session Minilang_AoA), waits for it, runs the test, and kills it.  With an
ADDR it uses the running server — whose environment must already carry this
directory on PYTHONPATH, or `Remote_Procedure_Calling.load` cannot import
`tat_framework_ml_test`.

The test passes iff evaluating the theory raises no error: every assertion
lives in `tat_framework_ml_test.drive`, and its failure comes back as the
error of the theory's final ML command.
"""

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time

from IsaREPL import Client

HERE = os.path.dirname(os.path.abspath(__file__))
REPL_SERVER = os.path.join(HERE, "..", "..", "Isa-REPL", "repl_server.sh")
BASE_SESSION = "Minilang_AoA"
STARTUP_TIMEOUT = 3600          # the first start builds the wrapper session


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def wait_for_server(addr: str, proc: subprocess.Popen, log_path: str) -> None:
    deadline = time.time() + STARTUP_TIMEOUT
    while True:
        if proc.poll() is not None:
            with open(log_path) as f:
                sys.stderr.write(f.read()[-4000:])
            raise SystemExit(f"repl_server exited with {proc.returncode}")
        try:
            await Client.test_server(addr, timeout=60)
            return
        except (ConnectionError, OSError):
            if time.time() > deadline:
                raise SystemExit("repl_server did not come up in time")
            await asyncio.sleep(5)


async def run(addr: str) -> None:
    with open(os.path.join(HERE, "Test_TAT_Framework.thy")) as f:
        source = f.read()
    async with Client(addr, "Draft") as c:
        outputs = await c.eval(source, import_dir=HERE)
    # out.output is always empty under repl_server.sh, which runs
    # REPL.disable_output (); the loop matters only against a server
    # configured otherwise
    for out in outputs or []:
        for kind, msg in out.output:
            print(f"[{out.command}] {kind.name}: {msg}")
        if out.errors:
            raise SystemExit(f"errors in `{out.command}`: {out.errors}")
    print("ML framework test passed")


async def main() -> None:
    if len(sys.argv) > 1:
        await run(sys.argv[1])
        return
    addr = f"127.0.0.1:{free_port()}"
    env = dict(os.environ)
    # this directory for tat_framework_ml_test, the repository root so that
    # `import isabelle_theory_agent` works even without a pip install
    env["PYTHONPATH"] = os.pathsep.join(
        [HERE, os.path.dirname(HERE), env.get("PYTHONPATH", "")])
    env["ISABELLE_RPC_PYTHON"] = sys.executable
    outdir = tempfile.mkdtemp(prefix="tat_repl_out_")
    log_path = os.path.join(outdir, "server.log")
    with open(log_path, "w") as log:
        proc = subprocess.Popen([REPL_SERVER, addr, BASE_SESSION, outdir],
                                env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        await wait_for_server(addr, proc, log_path)
        await run(addr)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
