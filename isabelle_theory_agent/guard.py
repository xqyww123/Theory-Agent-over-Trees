"""The guard script that keeps Claude Code's agents in the agent directory
(CLIENT_HOOKS.md §5): `configure` copies it into the working directory's
`.tat/`, and Claude Code runs it before each call of a file-writing tool
and of the tool that launches a subagent, and at each creation of a
worktree — standard library only, under `-I`, no connection.  It finds the
agent directory beside its own, judges from the hook's JSON alone, and
never exits 2; a failure of its own answers as the hook it serves needs.
"""

import json
import os
import sys

WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}
LAUNCH_TOOLS = {"Agent", "Task"}
CLIENTS_FILES = "TAT does not allow changing the agent client's own files."
WORKTREES = "TAT does not allow git worktrees. Start the subagent without worktree isolation."
ALLOW = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}


def outside(agent_directory: str) -> str:
    return f"TAT allows writing only inside {agent_directory}."


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def hook_of(payload: dict) -> str | None:
    """Which of the three hooks the payload is — a write, a launch, a
    worktree — or none the guard serves."""
    event, tool = payload.get("hook_event_name"), payload.get("tool_name")
    if event == "WorktreeCreate":
        return "worktree"
    if event == "PreToolUse" and tool in WRITE_TOOLS:
        return "write"
    if event == "PreToolUse" and tool in LAUNCH_TOOLS:
        return "launch"
    return None


def write_judged(agent_directory: str, tool_input: dict) -> dict:
    """The one rule: the path, absolute, made canonical, lies inside the
    agent directory and is neither `.mcp.json` nor under `.claude/`."""
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not os.path.isabs(path):
        return deny(outside(agent_directory))
    canonical = os.path.realpath(path)
    if not canonical.startswith(agent_directory + os.sep):
        return deny(outside(agent_directory))
    relative = os.path.relpath(canonical, agent_directory)
    if relative == ".mcp.json" or relative == ".claude" or relative.startswith(".claude" + os.sep):
        return deny(CLIENTS_FILES)
    return ALLOW


def launch_judged(tool_input: dict) -> dict | None:
    """`deny` for worktree isolation; no decision otherwise."""
    return deny(WORKTREES) if tool_input.get("isolation") == "worktree" else None


def answered(answer: dict | None) -> int:
    if answer is not None:
        print(json.dumps(answer))
    return 0


def worktree_refused() -> int:
    print(WORKTREES, file=sys.stderr)
    return 1


def main() -> int:
    agent_directory = os.path.realpath(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "TAT.agents"))
    refused = deny(outside(agent_directory))
    try:
        payload = json.load(sys.stdin)
        hook = hook_of(payload)
    except Exception:           # a payload whose hook cannot be told is refused as a write
        return answered(refused)
    if hook == "worktree":      # reads nothing, so has no failure to answer
        return worktree_refused()
    if hook == "write":
        try:
            return answered(write_judged(agent_directory, payload["tool_input"]))
        except Exception:
            return answered(refused)
    if hook == "launch":
        try:
            return answered(launch_judged(payload["tool_input"]))
        except Exception:       # undecided: exit 1, which no client reads as a block
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
