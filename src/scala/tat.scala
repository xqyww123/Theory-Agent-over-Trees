/*  Title:      src/scala/tat.scala
    Author:     Qiyuan Xu

The launcher (docs/MODULE_STRUCTURE.md §5): the Isabelle tools TAT, TAT_new,
TAT_mcp and TAT_compile.  All run in the JVM that `isabelle` starts.
*/

package isabelle.tat

import isabelle._

import java.io.{File => JFile}
import java.nio.file.{Files, Path => JPath}
import java.util.concurrent.TimeUnit

import scala.collection.mutable
import scala.jdk.CollectionConverters._


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


  /* TAT_new's work after the parse, shared with TAT: the absolute path and
     its refusals, the directory made, the plugins recorded */

  def create(arg: String, plugins: List[String]): Path = {
    val dir = working_directory(arg)

    // a directory TAT_new did not make is refused, so everything in a
    // working directory is TAT's (MODULE_STRUCTURE §5)
    if (dir.is_file) error(dir.implode + " is not a directory")
    if (dir.is_dir && File.read_dir(dir).nonEmpty && !(dir + database).is_file) {
      error(dir.implode + " is not empty and is not a TAT working directory")
    }

    Isabelle_System.make_directory(dir)
    using(SQLite.open_database(dir + database))(Plugins.add(_, plugins))
    dir
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

  Create WORKING_DIRECTORY for TAT. The recommended way to use TAT is
  isabelle TAT WORKING_DIRECTORY; with it, you don't need to run
  isabelle TAT_new yourself.
""",
          "P:" -> (arg => plugins += arg))

        val arg =
          getopts(args) match {
            case List(arg) => arg
            case _ => getopts.usage()
          }
        create(arg, plugins.toList)
      })



  /** the log (docs/LOGGING.md §7) **/

  /* Following a conversation's log directory: the path printed once the
     Isabelle side names it, every `warning` record printed as it is written
     -- a line that is not JSON skipped (LOGGING.md §6) -- and what is left
     read at the end.  A later directory, after TAT.reset, is followed once
     the previous one is drained.  Shared with TAT_compile (COMPILATION.md §5).
     `warnings` false only keeps the records from being echoed: under
     isabelle TAT nothing reaches the terminal while the client runs
     (MODULE_STRUCTURE §5); they stay in the log. */

  class Log_Follower(progress: Progress, warnings: Boolean = true) {
    // the directory, and how far into each of its files the follower has read
    private val state = Synchronized[Option[(Path, Map[String, Long])]](None)
    private val running = Synchronized(true)

    private def warning(file: String, line: String): Unit =
      Exn.capture(JSON.parse(line)) match {
        case Exn.Res(record) if warnings && JSON.string(record, "level").contains("warning") =>
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



  /** the agent client (docs/CONSTRUCT_INTERACTION.md §8, docs/MODULE_STRUCTURE.md §5) **/

  // the clients TAT serves, as -c names them, each with the command the shell runs
  val clients: List[(String, String)] = List("claude-code" -> "claude", "codex" -> "codex")

  def client_command(name: String): String =
    clients.collectFirst({ case (`name`, command) => command }) getOrElse
      error("TAT doesn't know the agent client " + name)

  /* the command found on PATH as the shell finds it: the entries split at
     `:`, an empty one the current directory, the first regular executable
     file taken and made absolute, nothing else -- no link followed, no `..`
     rewritten */

  def find_on_path(command: String): JPath =
    Library.space_explode(':', Isabelle_System.getenv("PATH")).iterator
      .map(entry => JPath.of(entry, command))
      .find(path => Files.isRegularFile(path) && Files.isExecutable(path))
      .map(_.toAbsolutePath)
      .getOrElse(error("TAT cannot find " + command + " on the path"))

  // the client isabelle TAT starts: its executable, and the user's arguments
  sealed case class Client(executable: JPath, args: List[String]) {
    def command: String = executable.getFileName.toString
  }


  /* the terminal: its mode is saved before the client starts only when stdin
     is a terminal, stdout is that same terminal, and the tool's process
     group is the terminal's foreground group; restored after the client has
     been reaped when the tool still holds the terminal then (MODULE_STRUCTURE §5) */

  // the fields after the last `)` of /proc/self/stat, by their proc(5) names:
  // state, ppid, pgrp, session, tty_nr, tpgid
  private val Proc_Stat = """(?s).*\) (\S+) (-?\d+) (-?\d+) (-?\d+) (-?\d+) (-?\d+) .*""".r

  // the tool's process group is the terminal's foreground group; read through
  // the JDK, which reads to the end -- procfs reports the file's size as 0,
  // and Isabelle's File.read reads that many bytes
  private def foreground(): Boolean =
    Exn.capture(Files.readString(JPath.of("/proc/self/stat"))) match {
      case Exn.Res(Proc_Stat(_, _, pgrp, _, _, tpgid)) => tpgid != "-1" && pgrp == tpgid
      case _ => false
    }

  // stty on the tool's own fd 0, which must be the terminal and not a pipe:
  // the trimmed output on exit 0
  private def stty(args: List[String]): Option[String] =
    Exn.capture {
      val builder =
        isabelle.setup.Environment.process_builder(("stty" :: args).asJava, null, null, false)
      builder.redirectInput(ProcessBuilder.Redirect.INHERIT)
      builder.redirectError(ProcessBuilder.Redirect.DISCARD)
      val process = builder.start()
      val output = File.read_stream(process.getInputStream)
      if (process.waitFor() == 0) Some(output.trim) else None
    } match {
      case Exn.Res(mode) => mode
      case Exn.Exn(_) => None
    }

  // stdout the same file as stdin
  private def same_streams(): Boolean =
    Exn.capture(Files.isSameFile(JPath.of("/proc/self/fd/0"), JPath.of("/proc/self/fd/1"))) match {
      case Exn.Res(same) => same
      case Exn.Exn(_) => false
    }

  // the mode as `stty -g` prints it; None when stdin is no terminal, or the
  // condition above fails
  private def saved_terminal_mode(): Option[String] =
    if (foreground() && same_streams()) stty(List("-g")) else None


  // SIGTERM's grace (the owner: at least 10 s); test/harness.py's
  // TERMINATION is the tests' counterpart
  val CLIENT_BOUND: Time = Time.seconds(10)

  /* The client once started: its process and the mode saved before it.
     `terminate` ends a client that still runs (MODULE_STRUCTURE §5): a
     snapshot of its descendants, SIGTERM, the bounded wait, a second
     snapshot when the client still runs at the bound, then SIGKILL to the
     client and to every process of either snapshot, and the wait; a client
     already gone is left as it is.  Then the mode is restored when one was
     saved and the tool still holds the terminal.  Run once, every caller
     waiting for it; nothing in it can fail: a snapshot that cannot be taken
     is empty, and the rest runs uninterruptibly, as Bash.Process.terminate
     does. */

  final class Started_Client(process: Process, saved_mode: Option[String]) {
    def terminate(): Unit = terminated

    private def descendants(): List[ProcessHandle] =
      Exn.capture(process.descendants().toList.asScala.toList) match {
        case Exn.Res(processes) => processes
        case Exn.Exn(_) => Nil
      }

    private lazy val terminated: Unit =
      Isabelle_Thread.try_uninterruptible {
        if (process.isAlive) {
          val before = descendants()
          process.destroy()
          val after =
            if (process.waitFor(CLIENT_BOUND.ms, TimeUnit.MILLISECONDS)) Nil else descendants()
          process.destroyForcibly()
          for (p <- before ::: after) p.destroyForcibly()
          process.waitFor()
        }
        for (mode <- saved_mode if foreground()) stty(List(mode))
      }
  }


  /* the launch's state: which of the conversation's end and the client's
     exit came first, the client once started, and whether one may still
     start */

  private sealed case class Launch_State(
    end: Option[(Int, List[String])] = None,
    client: Option[Started_Client] = None,
    closed: Boolean = false
  ) {
    // the first entered wins; every event that ends the conversation enters
    // here: the TAT.finished message, a failure of the TAT.finished or
    // TAT.serving handler (decoding included), the start's failure, the
    // process's termination, the client's exit
    def ended(rc: Int, messages: List[String]): Launch_State =
      if (end.isDefined) this else copy(end = Some((rc, messages)))
  }



  /** the Isabelle process of TAT, TAT_mcp and TAT_compile **/

  val boot: Path = Path.explode("$TAT_HOME/ML/TAT_Boot.ML")

  /* Steps 1 to 5 of MODULE_STRUCTURE §5, up to the end: the Isabelle
     process on the base heap `logic`, booted with the protocol command
     `command` on the working directory `dir`, then `arguments`, then the
     plugins' theory names; `client`, under isabelle TAT, started once the
     Python side serves and ended with the conversation.  Answers what
     TAT.finished carried, the client's exit code when that came first,
     or 2 and the reason when the process ended without either; whatever
     fails before the process answers is an ERROR, which ends the tool
     with 2. */

  def launch(
    progress: Progress,
    dir: Path,
    logic: String,
    dirs: List[Path],
    options: Options,
    command: String,
    arguments: List[String] = Nil,
    client: Option[Client] = None
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

    val log = new Log_Follower(progress, warnings = client.isEmpty)

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

    val state = Synchronized(Launch_State())
    def finish(rc: Int, messages: List[String]): Unit = state.change(_.ended(rc, messages))

    // the client ended, and none may start any more: the shutdown hook's
    // body, and the wait's end
    def end_client(): Unit = {
      val started = state.change_result(st => (st.client, st.copy(closed = true)))
      started.foreach(_.terminate())
    }

    // the client started in the agent directory, with the message's launch
    // arguments and then the user's: the state records it, or the failure
    // as the conversation's end
    def start_client(st: Launch_State, c: Client, agent_directory: String,
      launch_arguments: List[String]): Launch_State = {
      val saved_mode = saved_terminal_mode()
      val builder =
        isabelle.setup.Environment.process_builder(
          (c.executable.toString :: launch_arguments ::: c.args).asJava,
          new JFile(agent_directory), null, false)
      builder.inheritIO()
      Exn.capture(builder.start()) match {
        case Exn.Res(process) =>
          // on an executor, never in this thread, which holds the lock that
          // is recording the client: `finish` under it would be overwritten
          process.onExit().thenRunAsync(() => finish(process.exitValue(), Nil))
          st.copy(client = Some(new Started_Client(process, saved_mode)))
        case Exn.Exn(exn) =>
          st.ended(Process_Result.RC.failure,
            List("TAT cannot start " + c.command + ": " + Exn.message(exn)))
      }
    }

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
            // ERROR, and this message is the conversation's end itself
            catch {
              case exn: Throwable =>
                (Process_Result.RC.failure,
                  List("TAT.finished could not be decoded: " + Exn.message(exn)))
            }
          finish(rc, messages)
          true
        }),
        // the Python side is serving (MODULE_STRUCTURE §4.6): the URL printed;
        // under isabelle TAT the client started, unless the conversation has
        // ended, a client exists, or none may start any more
        "TAT.serving" -> ((msg: Prover.Protocol_Output) => {
          try {
            val (url, agent_directory, launch_arguments) = {
              import XML.Decode._
              triple(string, string, list(string))(Symbol.decode_yxml(msg.text))
            }
            progress.echo("TAT is serving on " + url)
            for (c <- client) {
              state.change(st =>
                if (st.end.isDefined || st.client.isDefined || st.closed) st
                else start_client(st, c, agent_directory, launch_arguments))
            }
          }
          // a failure let out would leave neither a client nor an end
          catch {
            case exn: Throwable =>
              finish(Process_Result.RC.failure,
                List("TAT.serving could not be decoded: " + Exn.message(exn)))
          }
          true
        }),
        // the Isabelle side passes the directory the Python side named
        // (LOGGING.md §7), absolute, as the Python side spelled it
        "TAT.log_directory" -> ((msg: Prover.Protocol_Output) => {
          log.follow(Path.explode(XML.Decode.string(Symbol.decode_yxml(msg.text))))
          true
        }))
    })

    // the process ending before it answers is an end too
    session.phase_changed += Session.Consumer[Session.Phase]("TAT") {
      case Session.Terminated(result) =>
        finish(Process_Result.RC.failure, List("Isabelle process terminated: " + result.print_rc))
      case _ =>
    }

    // the JVM ended from outside -- SIGTERM, a hangup -- ends the client first
    val shutdown_hook = Isabelle_System.create_shutdown_hook { end_client() }
    try {
      val process =
        Isabelle_Process.start(tat_options, session, session_background, session_heaps,
          use_prelude = List(File.platform_path(boot)),
          eval_main = Command_Line.ML_tool(List("Isabelle_Process.init_build ()")))

      POSIX_Interrupt.handler {
        // while a client exists the terminal's interrupt is the client's
        val terminate =
          state.change_result(st =>
            if (st.client.isDefined) (false, st) else (true, st.copy(closed = true)))
        if (terminate) process.terminate()
      } {
        process.await_startup()


        /* 4. the boot */

        session.protocol_command("TAT.boot",
          (command :: File.platform_path(dir) :: arguments ::: plugins).map(XML.Encode.string): _*)


        /* 5. the end: the first of the conversation's end and the client's
           exit, read once; the client ended either way, then the log's last
           records */

        val end =
          try { state.guarded_access(st => st.end.map(x => (x, st))) }
          finally { end_client() }
        log.stop()
        session.stop()
        end
      }
    }
    finally { Isabelle_System.remove_shutdown_hook(shutdown_hook) }
  }


  /* the end of TAT_mcp and TAT, from what `launch` answered: the messages
     as errors, and the exit with the code unless it is 0 */

  def start(
    progress: Progress,
    dir: Path,
    logic: String,
    dirs: List[Path],
    options: Options,
    port: Int,
    client_name: String,
    client: Option[Client]
  ): Unit = {
    val (rc, messages) =
      launch(progress, dir, logic, dirs, options, "TAT.start", List(port.toString, client_name), client)
    messages.foreach(progress.echo_error_message(_))
    if (rc != Process_Result.RC.ok) sys.exit(rc)
  }



  /** isabelle TAT_mcp **/

  val tat_mcp_tool: Isabelle_Tool =
    Isabelle_Tool("TAT_mcp", "start a TAT conversation", Scala_Project.here,
      { args =>
        var client_name = clients.head._1
        val dirs = new mutable.ListBuffer[Path]
        var logic = Isabelle_System.default_logic()
        var options = Options.init()
        var port = 0

        val getopts = Getopts("""
Usage: isabelle TAT_mcp [OPTIONS] WORKING_DIRECTORY

  Options are:
    -c CLIENT    the agent client that will connect: """ + clients.map(_._1).mkString(" or ") + """
                 (default: """ + clients.head._1 + """)
    -l BASE      the base heap (default: ISABELLE_LOGIC=""" + quote(logic) + """)
    -p PORT      the port of the MCP server (default: a random one the system assigns)
    -d DIR       as Isabelle's -d: a further directory whose ROOT declares
                 Isabelle sessions
    -o OPTION    as Isabelle's -o: override an Isabelle system option

  Start a TAT conversation on WORKING_DIRECTORY, providing the MCP service
  at http://127.0.0.1:PORT/mcp.
""",
          "c:" -> (arg => client_name = arg),
          "d:" -> (arg => dirs += Path.explode(arg)),
          "l:" -> (arg => logic = arg),
          "o:" -> (arg => options = options + arg),
          "p:" -> (arg => port = Value.Int.parse(arg)))

        val dir = working_directory_argument(getopts, args)
        // after the options, not in -c's handler: Getopts appends a line of
        // its own to an error raised there, and the refusal is one sentence
        client_command(client_name)

        start(new Console_Progress(), dir, logic, dirs.toList, options, port, client_name, None)
      })



  /** isabelle TAT **/

  val tat_tool: Isabelle_Tool =
    Isabelle_Tool("TAT", "start a TAT conversation and its agent client", Scala_Project.here,
      { args =>
        val plugins = new mutable.ListBuffer[String]
        var client_name = clients.head._1
        val dirs = new mutable.ListBuffer[Path]
        var logic = Isabelle_System.default_logic()
        var options = Options.init()
        var port = 0

        val getopts = Getopts("""
Usage: isabelle TAT [OPTIONS] WORKING_DIRECTORY [CLIENT_ARGS ...]

  Options are:
    -P PLUGIN    a plugin to load in this working directory, as isabelle TAT_new -P
    -c CLIENT    the agent client: """ + clients.map(_._1).mkString(" or ") + """ (default: """ + clients.head._1 + """)
    -l BASE      the base heap, as isabelle TAT_mcp -l
    -p PORT      the port of the MCP server, as isabelle TAT_mcp -p
    -d DIR       as Isabelle's -d: a further directory whose ROOT declares
                 Isabelle sessions
    -o OPTION    as Isabelle's -o: override an Isabelle system option

  Create WORKING_DIRECTORY for TAT when it does not exist, start a TAT
  conversation on it, and start CLIENT in its agent directory,
  WORKING_DIRECTORY/TAT.agents, with CLIENT_ARGS. The conversation ends
  when the client exits.
""",
          "P:" -> (arg => plugins += arg),
          "c:" -> (arg => client_name = arg),
          "d:" -> (arg => dirs += Path.explode(arg)),
          "l:" -> (arg => logic = arg),
          "o:" -> (arg => options = options + arg),
          "p:" -> (arg => port = Value.Int.parse(arg)))

        // the options stop at WORKING_DIRECTORY; what follows is the client's, untouched
        val (arg, client_args) =
          getopts(args, internal = true) match {
            case arg :: rest => (arg, rest)
            case Nil => getopts.usage(internal = true)
          }
        // the client's name and its executable before anything is created
        val executable = find_on_path(client_command(client_name))
        val dir = create(arg, plugins.toList)

        // the tool's own output on stderr: stdout is the client's
        val progress = new Console_Progress(stderr = true)
        progress.echo("Starting TAT... It may take a while")
        start(progress, dir, logic, dirs.toList, options, port, client_name,
          Some(Client(executable, client_args)))
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
  extends Isabelle_Scala_Tools(TAT.tat_tool, TAT.tat_new_tool, TAT.tat_mcp_tool, TAT.tat_compile_tool)

class TAT_Functions extends Scala.Functions(TAT.Reserved_Name, TAT.Check_Options)
