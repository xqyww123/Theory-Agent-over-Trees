"""The conversation's hooks' script (CLIENT_HOOKS.md §1): `configure`
copies it into the working directory's `.tat/`, and the agent client runs
it at every hook of the conversation's — standard library only, under
`-I`.  It posts the hook's payload to the running conversation, found
through `tat.lock` beside its own directory, and prints the answer; every
failure of its own is exit 1 and one line on stderr, never exit 2, which
the client would read as a block.
"""

import os
import sys
import urllib.request

FAILURE = "TAT is not running in this directory."


def main() -> int:
    working_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        # the lock's pid line, then its port line (`toplevel._held`): absent,
        # cleared, not yet announced or a dead holder's, nothing is running
        with open(os.path.join(working_directory, "tat.lock")) as lock:
            pid, port = lock.read().split("\n")[:2]
        os.kill(int(pid), 0)
        request = urllib.request.Request(
            f"http://127.0.0.1:{int(port)}/hook", data=sys.stdin.buffer.read(),
            headers={"Content-Type": "application/json"}, method="POST")
        # the address itself, whatever proxy the environment names
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with direct.open(request) as answer:
            if answer.status != 200:
                raise ValueError(answer.status)
            sys.stdout.buffer.write(answer.read())
        return 0
    except Exception:
        print(FAILURE, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
