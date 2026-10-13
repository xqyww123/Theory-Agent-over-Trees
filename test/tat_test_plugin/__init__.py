"""The test plugin's Python package (ai-artifacts/TEST_HARNESS_PLAN.md §5): what
`test/Test_TAT_Framework.thy` names in `python_packages`, twice.  Its one node
class, `Note`, gives a conversation of the harness every tool and both
kinds of job (the jobs plan, step 9): a `text` command, with a construction
job that asks one question and settles by the answer, and an evaluation
job whose work `TAT_test.fork_job` forks — passing, failing, or waiting for
a file the case may never write, so that the case can cancel it.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from Isabelle_RPC_Host.unicode import IsaTerm
from isabelle_theory_agent import isabelle_driver, jobs, model as M
from isabelle_theory_agent.jobs import Answered, Failed, Succeeded
from isabelle_theory_agent.plugin import TAT_node


class Verdict(jobs.Interactive_Question):
    text = "Accept the note?"
    schema = {"type": "object",
              "properties": {"verdict": {"type": "string", "enum": ["accept", "reject"]}},
              "required": ["verdict"], "additionalProperties": False}

    def receive(self, answer):
        self.verdict = answer["verdict"]
        return Answered()


class Note_Construction(jobs.Construction_Job):
    """Asks the owner once and settles by the answer."""

    @classmethod
    def title(cls, plural=False):
        return "note constructions" if plural else "note construction"

    @classmethod
    def failure_header(cls, failure):
        return "The note was rejected:"

    async def _run(self):
        verdict = Verdict()
        await self.ask(verdict)
        return Succeeded(verdict.verdict) if verdict.verdict == "accept" else Failed("rejected by its owner")


class Note_Check(jobs.Evaluation_Job):
    """Its work is `TAT_test.fork_job`'s, ending as the note's `work` says;
    a waiting work waits for the file `<node id>.wait` in the working
    directory."""

    @classmethod
    def title(cls, plural=False):
        return "note checks" if plural else "note check"

    @classmethod
    def failure_header(cls, failure):
        return "The note check failed:"

    @classmethod
    def failure_notification(cls, ids, automatic):
        tail = ", so its note construction was started automatically." if automatic else "."
        return jobs.listed(ids, lambda on: f"The note check {on} failed{tail}",
                           "The following note checks failed" + tail[:-1] + ":")

    async def _start(self):
        path = self.conversation.working_directory / f"{self.node_id}.wait"
        await isabelle_driver.call(self.conversation, "TAT_test.fork_job",
                                   (self.id, (self.node.work, str(path))))


class Note_RawAST(TypedDict):
    kind: Literal["note"]
    name: str
    text: str
    work: str


@TAT_node
class Note(M.Leaf):
    """A `text` command, run through `TAT_test.run`; `work` says how its
    evaluation job's work ends: `pass`, `fail` or `wait`."""

    construct_schema = {
        "type": "object",
        "properties": {
            "kind": {"const": "note"},
            "name": {"type": "string", "description": "The note's name"},
            "text": {"type": "string", "description": "The note's text"},
            "work": {"type": "string", "enum": ["pass", "fail", "wait"],
                     "description": "How the note check's work ends"},
        },
        "required": ["kind", "name", "text", "work"],
        "additionalProperties": False,
    }
    argument_schema = Note_RawAST
    construction_job_class = Note_Construction
    evaluation_job_class = Note_Check

    def __init__(self, parent, state, name: str, text: str, work: str):
        super().__init__(parent, state)
        self.name, self.text, self.work = name, text, work

    @classmethod
    async def gen(cls, config, raw):
        return cls(config.parent, config.state, raw["name"], raw["text"], raw["work"])

    def to_store(self, rows):
        rows.put("name", self.name)
        rows.put("text", self.text)
        rows.put("work", self.work)

    @classmethod
    def from_store(cls, config, rows):
        return cls(config.parent, config.state, rows.get("name"), rows.get("text"), rows.get("work"))

    def command(self) -> str:
        return f"text \\<open>{self.text}\\<close>"

    async def _eval_opr(self):
        records = await isabelle_driver.call(
            self.forest().conversation, "TAT_test.run",
            (self.state.to_msgpack(), (self.resulting_state().to_msgpack(), self.command())))
        errors = [e for _, errs, _ in records for e in errs]
        if errors:
            return M.CannotEvaluate(tuple(IsaTerm.from_agent(e) for e in errors))
        return M.Ready()

    def emit(self, indent, out):
        M.emit_lines(indent, out, self.command())
        return indent
