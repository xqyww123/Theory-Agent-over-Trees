/*  Title:      src/scala/tat.scala
    Author:     Qiyuan Xu

The launcher (docs/MODULE_STRUCTURE.md §5): the Isabelle tools TAT_new,
TAT_mcp and TAT_compile.  All run in the JVM that `isabelle` starts.
*/

package isabelle.tat

import isabelle._

import scala.collection.mutable


object TAT {
  /** the working directory's database **/

  val database: Path = Path.basic("TAT.sqlite")

  /* the table this side owns; Forest_Store's tables share the file and
     neither side reads the other's */

  object Plugins {
    val theory: SQL.Column = SQL.Column.string("theory", primary_key = true)
    val table: SQL.Table = SQL.Table("plugins", List(theory))

    def add(db: SQL.Database, plugins: List[String]): Unit =
      db.transaction {
        db.create_table(table)
        db.execute_batch_statement(db.insert_permissive(table),
          batch = plugins.map(plugin => (stmt: SQL.Statement) => stmt.string(1) = plugin))
      }

    def read(db: SQL.Database): List[String] =
      if (db.exists_table(table)) {
        db.execute_query_statement(
          table.select(List(theory), sql = "ORDER BY rowid"), List.from[String], _.string(theory))
      }
      else Nil
  }


  /* absolute: the path travels to the Python side, which may be a process
     started elsewhere (ARCHITECTURE §9); no `[` or `]`, which both clients
     read as pattern syntax in the entries that hide the directory from the
     agents (CLIENT_HOOKS.md §5) */

  def working_directory(arg: String): Path = {
    val dir = Path.explode(arg).absolute
    if (dir.implode.exists(c => c == '[' || c == ']')) {
      error(dir.implode + " contains [ or ], which TAT cannot use in a working directory path")
    }
    dir
  }


  /* the one argument of TAT_mcp and TAT_compile, read with Getopts in its
     internal mode: a usage error is an ERROR, which ends the tool with 2 */

  def working_directory_argument(getopts: Getopts, args: List[String]): Path =
    getopts(args, internal = true) match {
      case List(arg) => working_directory(arg)
      case _ => getopts.usage(internal = true)
    }



  /** the names Isabelle refuses, for the ML side to ask (docs/COMPILATION.md §2) **/

  /* Isabelle's own predicates, not a copy of its lists: the answer is the
     words, separated by a space, of those that hold of the name */

  object Reserved_Name extends Scala.Fun_String("TAT.reserved_name") {
    val here = Scala_Project.here
    def apply(name: String): String =
      List(
        "file" -> Path.is_reserved(name),
        "theory" -> Sessions.illegal_theory(name),
        "session" -> Sessions.illegal_session(name)).filter(_._2).map(_._1).mkString(" ")
  }

  /* a ROOT entry's options, applied as Isabelle reads a ROOT -- so that
     what creation accepts, the final reading accepts: the names and values
     in turn; the answer is empty when every one is accepted, else the
     index of the first refused and Isabelle's message */

  object Check_Options extends Scala.Fun_Strings("TAT.check_options") {
    val here = Scala_Project.here
    private lazy val defaults: Options = Options.init()
    def apply(args: List[String]): List[String] = {
      def check(options: Options, specs: List[List[String]], i: Int): List[String] =
        specs match {
          case Nil => Nil
          case List(name, value) :: rest =>
            Exn.capture(options + Options.Spec(name, Some(value))) match {
              case Exn.Res(options1) => check(options1, rest, i + 1)
              case Exn.Exn(ERROR(msg)) => List(i.toString, msg)
              case Exn.Exn(exn) => throw exn
            }
          case _ => error("TAT.check_options: the arguments are not pairs")
        }
      check(defaults, args.grouped(2).toList, 0)
    }
  }



  /** isabelle TAT_new **/

  /* the agent clients' hooks (docs/CLIENT_HOOKS.md, whose fenced blocks
     these are verbatim): one script, and one file per client that calls
     it -- each written when absent, never rewritten */

  val hook_files: List[(Path, String)] =
    List(
      Path.explode(".tat/on-compaction.sh") ->
"""#!/bin/sh
# Written by `isabelle TAT_new`; the agent clients' hooks call it (docs/CLIENT_HOOKS.md).
not_running() { echo 'TAT is not running in this directory.' >&2; exit 1; }
pid=$(sed -n 1p tat.lock 2>/dev/null)
port=$(sed -n 2p tat.lock 2>/dev/null)
{ [ -n "$port" ] && kill -0 "$pid" 2>/dev/null; } || not_running
if [ $# -eq 0 ]
then curl -sS --fail-with-body -o /dev/null -X POST "http://127.0.0.1:$port/on-compaction"
else curl -sS --fail-with-body -X POST "http://127.0.0.1:$port/on-compaction?client=$1"
fi
rc=$?
[ $rc -eq 7 ] && not_running
exit $rc
""",
      Path.explode(".claude/settings.json") ->
"""{ "hooks": { "SessionStart": [ { "hooks": [
  { "type": "command", "timeout": 10, "command": "sh .tat/on-compaction.sh claude-code" } ] } ] } }
""",
      Path.explode(".codex/hooks.json") ->
"""{ "hooks": { "SessionStart": [ { "hooks": [
  { "type": "command", "timeout": 10, "additionalContextLimit": 20000, "command": "sh .tat/on-compaction.sh codex" } ] } ] } }
""",
      Path.explode(".gemini/settings.json") ->
"""{ "hooks": {
  "SessionStart": [ { "matcher": "*", "hooks": [ { "name": "TAT", "type": "command", "command": "sh .tat/on-compaction.sh gemini-cli" } ] } ],
  "PreCompress": [ { "matcher": "*", "hooks": [ { "name": "TAT", "type": "command", "command": "sh .tat/on-compaction.sh" } ] } ] } }
""",
      Path.explode(".cursor/hooks.json") ->
"""{ "version": 1, "hooks": {
  "sessionStart": [ { "command": "sh .tat/on-compaction.sh cursor" } ],
  "preCompact":   [ { "command": "sh .tat/on-compaction.sh" } ] } }
""",
      Path.explode(".opencode/plugins/tat.js") ->
"""export const TAT = async ({ $ }) => ({
  event: async ({ event }) => {
    if (event.type === "session.created") await $`sh .tat/on-compaction.sh`.quiet()
  },
  "experimental.session.compacting": async (_input, output) => {
    output.context.push(await $`sh .tat/on-compaction.sh opencode`.text())
  },
})
""")

  def write_hooks(dir: Path): Unit =
    for ((path, text) <- hook_files if !(dir + path).is_file) {
      Isabelle_System.make_directory((dir + path).dir)
      File.write(dir + path, text)
    }

  val tat_new_tool: Isabelle_Tool =
    Isabelle_Tool("TAT_new", "create a working directory for TAT", Scala_Project.here,
      { args =>
        val plugins = new mutable.ListBuffer[String]

        val getopts = Getopts("""
Usage: isabelle TAT_new [OPTIONS] WORKING_DIRECTORY

  Options are:
    -P PLUGIN    a plugin to load in this working directory. Give the full
                 name (SESSION.THEORY) of the theory that defines the plugin.
                 Example: -P My_Nodes.Locale_Node

  Create WORKING_DIRECTORY for TAT. Afterwards, you can start TAT on it
  with: isabelle TAT_mcp WORKING_DIRECTORY
""",
          "P:" -> (arg => plugins += arg))

        val dir =
          getopts(args) match {
            case List(arg) => working_directory(arg)
            case _ => getopts.usage()
          }

        // a directory TAT_new did not make is refused, so everything in a
        // working directory is TAT's (MODULE_STRUCTURE §5)
        if (dir.is_file) error(dir.implode + " is not a directory")
        if (dir.is_dir && File.read_dir(dir).nonEmpty && !(dir + database).is_file) {
          error(dir.implode + " is not empty and is not a TAT working directory")
        }

        Isabelle_System.make_directory(dir)
        using(SQLite.open_database(dir + database))(Plugins.add(_, plugins.toList))
        write_hooks(dir)
      })



  /** the log (docs/LOGGING.md §7) **/

  /* Following a conversation's log directory: the path printed once the
     Isabelle side names it, every `warning` record printed as it is written
     -- a line that is not JSON skipped (LOGGING.md §6) -- and what is left
     read at the end.  A later directory, after TAT.reset, is followed once
     the previous one is drained.  Shared with TAT_compile (COMPILATION.md §5). */

  class Log_Follower(progress: Progress) {
    // the directory, and how far into each of its files the follower has read
    private val state = Synchronized[Option[(Path, Map[String, Long])]](None)
    private val running = Synchronized(true)

    private def warning(file: String, line: String): Unit =
      Exn.capture(JSON.parse(line)) match {
        case Exn.Res(record) if JSON.string(record, "level").contains("warning") =>
          val message = JSON.value(record, "data").flatMap(JSON.string(_, "message")).getOrElse("")
          val time = JSON.string(record, "ts").getOrElse("").dropWhile(_ != 'T').drop(1)
          progress.echo("### " + message + " (" + file + ", " + time + ")")
        case _ =>
      }

    // the complete lines each file gained; an incomplete last line waits,
    // and so does a file that cannot be read now -- the log is nothing the
    // launcher may fail over
    private def read(dir: Path, offsets: Map[String, Long]): Map[String, Long] =
      if (!dir.is_dir) offsets
      else {
        File.read_dir(dir).filter(_.endsWith(".jsonl")).foldLeft(offsets) { (offsets, name) =>
          val path = dir + Path.basic(name)
          val offset = offsets.getOrElse(name, 0L)
          Exn.capture(if (path.is_file) Bytes.read_file(path, offset).text else "") match {
            case Exn.Res(text) =>
              val cut = text.lastIndexOf('\n')
              if (cut < 0) offsets
              else {
                val complete = text.substring(0, cut + 1)
                for (line <- Library.split_lines(complete) if line.nonEmpty) warning(name, line)
                offsets + (name -> (offset + Bytes(complete).size))
              }
            case Exn.Exn(_) => offsets
          }
        }
      }

    private def drained(st: Option[(Path, Map[String, Long])]): Option[(Path, Map[String, Long])] =
      st.map({ case (dir, offsets) => (dir, read(dir, offsets)) })

    def drain(): Unit = state.change(drained)

    def follow(dir: Path): Unit =
      state.change({ st =>
        drained(st)
        progress.echo("Log: " + dir.implode)
        Some((dir, Map.empty))
      })

    Isabelle_Thread.fork(name = "TAT.log_follower", daemon = true) {
      while (running.value) { drain(); Thread.sleep(200) }
    }

    // the end: what is left is read now, before the ending's messages
    def stop(): Unit = { running.change(_ => false); drain() }
  }



  /** the Isabelle process of TAT_mcp and TAT_compile **/

  val boot: Path = Path.explode("$TAT_HOME/ML/TAT_Boot.ML")

  /* Steps 1 to 5 of MODULE_STRUCTURE §5, up to the ending: the Isabelle
     process on the base heap `logic`, booted with the protocol command
     `command` on the working directory `dir`, then `arguments`, then the
     plugins' theory names.  Answers what TAT.finished carried -- or 2 and
     the reason, when the process ended without it; whatever fails before
     the process answers is an ERROR, which ends the tool with 2. */

  def launch(
    progress: Progress,
    dir: Path,
    logic: String,
    dirs: List[Path],
    options: Options,
    command: String,
    arguments: List[String] = Nil
  ): (Int, List[String]) = {

    /* 1. the working directory */

    if (!dir.is_dir) error(dir.implode + " is not a directory")
    if (!(dir + database).is_file) {
      error(dir.implode + " holds no " + database.implode + "; run isabelle TAT_new first")
    }
    val plugins = using(SQLite.open_database(dir + database))(Plugins.read)


    /* 2. the options: TAT's two last, so they win -- nobody answers a
       dialogue in a headless process, and the tracing limiter asks one */

    val tat_options =
      options.string.update("isabelle_rpc_dialogue", "absent").
        int.update("editor_tracing_messages", 0)

    // the boot restores this option's value, and every load asserts it
    // below 3 (docs/EVALUATOR_DESIGN.md §6)
    val parallel_proofs = tat_options.int("parallel_proofs")
    if (parallel_proofs >= 3) {
      error("TAT requires parallel_proofs below 3, but the options give " + parallel_proofs)
    }


    /* 3. the Isabelle session layout, the base heap, the process */

    val session_background = Sessions.background(tat_options, logic, dirs = dirs).check_errors

    // no theory is ever loaded from under the working directory
    // (docs/EVALUATOR_DESIGN.md §2): a session declared there is refused,
    // so that no file under it can be found by its session name
    val session_directories =
      session_background.sessions_structure.session_directories.toList.sortBy(_._1.getPath)
    for ((file, name) <- session_directories) {
      if (File.relative_path(dir.canonical, File.path(file)).isDefined) {
        error("Isabelle session " + name + " is declared under the working directory " +
          dir.implode + "; TAT never loads theories from there")
      }
    }

    val log = new Log_Follower(progress)

    // strict: a base heap that does not build is an ERROR
    progress.interrupt_handler {
      Build.build_logic(tat_options, logic, build_heap = true, progress = progress,
        dirs = dirs, strict = true)
    }

    val session_heaps = Store(tat_options).session_heaps(session_background, logic = logic)

    val session =
      new Session {
        override def session_options: Options = tat_options
        override val resources: Resources = new Resources(session_background)
      }

    // the first ending wins: TAT.finished, or the process's termination
    val finished = Synchronized[Option[(Int, List[String])]](None)
    def finish(rc: Int, messages: List[String]): Unit =
      finished.change(_ orElse Some((rc, messages)))

    session.init_protocol_handler(new Session.Protocol_Handler {
      override val functions: Session.Protocol_Functions =
        List("TAT.finished" -> ((msg: Prover.Protocol_Output) => {
          // as build_job.scala decodes build_session_finished: the messages carry markup
          val (rc, messages) =
            try {
              val (rc, errs) = {
                import XML.Decode._
                pair(int, list(self))(Symbol.decode_yxml(msg.text))
              }
              (rc, errs.map(Pretty.string_of(_, metric = Symbol.Metric, pure = true)))
            }
            // wider than build_job's clause: XML.Decode throws XML.Error, not
            // ERROR, and this message is the launcher's only ending
            catch {
              case exn: Throwable =>
                (Process_Result.RC.failure,
                  List("TAT.finished could not be decoded: " + Exn.message(exn)))
            }
          finish(rc, messages)
          true
        }),
        // the Isabelle side passes the directory the Python side named
        // (LOGGING.md §7), absolute, as the Python side spelled it
        "TAT.log_directory" -> ((msg: Prover.Protocol_Output) => {
          log.follow(Path.explode(XML.Decode.string(Symbol.decode_yxml(msg.text))))
          true
        }))
    })

    // the process ending before it answers is an ending too
    session.phase_changed += Session.Consumer[Session.Phase]("TAT") {
      case Session.Terminated(result) =>
        finish(Process_Result.RC.failure, List("Isabelle process terminated: " + result.print_rc))
      case _ =>
    }

    val process =
      Isabelle_Process.start(tat_options, session, session_background, session_heaps,
        use_prelude = List(File.platform_path(boot)),
        eval_main = Command_Line.ML_tool(List("Isabelle_Process.init_build ()")))

    POSIX_Interrupt.handler { process.terminate() } {
      process.await_startup()


      /* 4. the boot */

      session.protocol_command("TAT.boot",
        (command :: File.platform_path(dir) :: arguments ::: plugins).map(XML.Encode.string): _*)


      /* 5. the ending, after the log's last records */

      val ending = finished.guarded_access(st => st.map(x => (x, st)))
      log.stop()
      session.stop()
      ending
    }
  }



  /** isabelle TAT_mcp **/

  val default_port = 8191

  // the agent clients TAT serves, as -c names them (CONSTRUCT_INTERACTION §8)
  val clients: List[String] = List("claude-code", "codex")

  val tat_mcp_tool: Isabelle_Tool =
    Isabelle_Tool("TAT_mcp", "start a TAT conversation", Scala_Project.here,
      { args =>
        var client = clients.head
        val dirs = new mutable.ListBuffer[Path]
        var logic = Isabelle_System.default_logic()
        var options = Options.init()
        var port = default_port

        val getopts = Getopts("""
Usage: isabelle TAT_mcp [OPTIONS] WORKING_DIRECTORY

  Options are:
    -c CLIENT    the agent client that will connect: """ + clients.mkString(" or ") + """
                 (default: """ + clients.head + """)
    -l BASE      the base heap (default: ISABELLE_LOGIC=""" + quote(logic) + """)
    -p PORT      the port of the MCP server (default: """ + default_port + """)
    -d DIR       as Isabelle's -d: a further directory whose ROOT declares
                 Isabelle sessions
    -o OPTION    as Isabelle's -o: override an Isabelle system option

  Start a TAT conversation on WORKING_DIRECTORY, providing the MCP service
  at http://127.0.0.1:PORT/mcp.
""",
          "c:" -> (arg => client = arg),
          "d:" -> (arg => dirs += Path.explode(arg)),
          "l:" -> (arg => logic = arg),
          "o:" -> (arg => options = options + arg),
          "p:" -> (arg => port = Value.Int.parse(arg)))

        val dir = working_directory_argument(getopts, args)
        // after the options, not in -c's handler: Getopts appends a line of
        // its own to an error raised there, and the refusal is one sentence
        if (!clients.contains(client)) error("TAT knows no client " + client)

        val progress = new Console_Progress()
        val (rc, messages) =
          launch(progress, dir, logic, dirs.toList, options, "TAT.start",
            List(port.toString, client))
        messages.foreach(progress.echo_error_message(_))
        if (rc != Process_Result.RC.ok) sys.exit(rc)
      })



  /** isabelle TAT_compile (docs/COMPILATION.md) **/

  val tat_compile_tool: Isabelle_Tool =
    Isabelle_Tool("TAT_compile", "write a TAT working directory's theories and ROOT",
      Scala_Project.here,
      { args =>
        val dirs = new mutable.ListBuffer[Path]
        var logic = Isabelle_System.default_logic()
        var options = Options.init()

        val getopts = Getopts("""
Usage: isabelle TAT_compile [OPTIONS] WORKING_DIRECTORY

  Options are:
    -l BASE      the base heap (default: ISABELLE_LOGIC=""" + quote(logic) + """)
    -d DIR       as Isabelle's -d: a further directory whose ROOT declares
                 Isabelle sessions
    -o OPTION    as Isabelle's -o: override an Isabelle system option

  Write the theories of WORKING_DIRECTORY as .thy files, and a ROOT that
  declares its sessions, into WORKING_DIRECTORY. No TAT conversation may
  be running on it.

  Exit code 0: every theory was written. 1: some theory was not written,
  and the report says which and why. 2: the compile did not complete.
""",
          "d:" -> (arg => dirs += Path.explode(arg)),
          "l:" -> (arg => logic = arg),
          "o:" -> (arg => options = options + arg))

        val dir = working_directory_argument(getopts, args)

        val progress = new Console_Progress()
        val (rc, lines) = launch(progress, dir, logic, dirs.toList, options, "TAT.compile")
        if (Process_Result.RC.regular(rc)) {
          lines.foreach(progress.echo(_))
          // Isabelle reads what was written: the steps `isabelle build` takes
          // before building, which evaluate nothing; a refusal is an ERROR,
          // and so is an interrupt -- 130 is for one before the process starts
          try {
            progress.interrupt_handler {
              val structure =
                Sessions.load_structure(options, dirs = dirs.toList, select_dirs = List(dir))
              Sessions.deps(structure.selection(Sessions.Selection.empty), progress = progress).
                check_errors
            }
          }
          catch { case Exn.Interrupt() => error("Interrupt") }
        }
        else lines.foreach(progress.echo_error_message(_))
        if (rc != Process_Result.RC.ok) sys.exit(rc)
      })
}

class TAT_Tools
  extends Isabelle_Scala_Tools(TAT.tat_new_tool, TAT.tat_mcp_tool, TAT.tat_compile_tool)

class TAT_Functions extends Scala.Functions(TAT.Reserved_Name, TAT.Check_Options)
