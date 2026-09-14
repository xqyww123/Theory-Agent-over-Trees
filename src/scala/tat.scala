/*  Title:      src/scala/tat.scala
    Author:     Qiyuan Xu

The launcher (docs/MODULE_STRUCTURE.md §5): the Isabelle tools TAT_new and
TAT.  Both run in the JVM that `isabelle` starts.
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
        for (plugin <- plugins) {
          db.execute_statement(table.insert_cmd("INSERT OR IGNORE"),
            body = { stmt => stmt.string(1) = plugin })
        }
      }

    def read(db: SQL.Database): List[String] =
      if (db.exists_table(table)) {
        db.execute_query_statement(
          table.select(List(theory), sql = "ORDER BY rowid"), List.from[String], _.string(theory))
      }
      else Nil
  }

  /* absolute: the path travels to the Python side, which may be a process
     started elsewhere (ARCHITECTURE §9) */

  def working_directory(arg: String): Path = Path.explode(arg).absolute



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

  Create WORKING_DIRECTORY for TAT. TAT's own node classes are always loaded.
  On an existing working directory, TAT_new adds the given plugins and
  changes nothing else.
""",
          "P:" -> (arg => plugins += arg))

        val dir =
          getopts(args) match {
            case List(arg) => working_directory(arg)
            case _ => getopts.usage()
          }

        Isabelle_System.make_directory(dir)
        using(SQLite.open_database(dir + database))(Plugins.add(_, plugins.toList))
      })



  /** isabelle TAT **/

  val default_port = 8191

  val boot: Path = Path.explode("$TAT_HOME/ML/TAT_Boot.ML")

  val tat_tool: Isabelle_Tool =
    Isabelle_Tool("TAT", "start a TAT conversation", Scala_Project.here,
      { args =>
        val dirs = new mutable.ListBuffer[Path]
        var logic = Isabelle_System.default_logic()
        var options = Options.init()
        var port = default_port

        val getopts = Getopts("""
Usage: isabelle TAT [OPTIONS] WORKING_DIRECTORY

  Options are:
    -l BASE      the base heap (default: ISABELLE_LOGIC=""" + quote(logic) + """)
    -p PORT      the port of the MCP server (default: """ + default_port + """)
    -d DIR       as Isabelle's -d: a further directory whose ROOT declares
                 Isabelle sessions
    -o OPTION    as Isabelle's -o: override an Isabelle system option

  Start a TAT conversation on WORKING_DIRECTORY: Isabelle on the base heap,
  and the MCP server on http://127.0.0.1:PORT/mcp.
""",
          "d:" -> (arg => dirs += Path.explode(arg)),
          "l:" -> (arg => logic = arg),
          "o:" -> (arg => options = options + arg),
          "p:" -> (arg => port = Value.Int.parse(arg)))

        val dir =
          getopts(args) match {
            case List(arg) => working_directory(arg)
            case _ => getopts.usage()
          }


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


        /* 3. the Isabelle process */

        val progress = new Console_Progress()

        val results =
          progress.interrupt_handler {
            Build.build_logic(tat_options, logic, build_heap = true, progress = progress,
              dirs = dirs.toList)
          }
        if (!results.ok) sys.exit(results.rc)

        val session_background =
          Sessions.background(tat_options, logic, dirs = dirs.toList).check_errors
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
                catch { case ERROR(err) => (Process_Result.RC.failure, List(err)) }
              finish(rc, messages)
              true
            }))
        })

        // nothing the process prints is echoed: what ends the conversation
        // arrives in TAT.finished
        session.all_messages += Session.Consumer[Prover.Message]("TAT") {
          case output: Prover.Output if output.is_exit =>
            val result =
              output.properties match {
                case Markup.Process_Result(result) => ": " + result.print_rc
                case _ => ""
              }
            finish(1, List("Isabelle process terminated" + result))
          case _ =>
        }

        val process =
          Isabelle_Process.start(tat_options, session, session_background, session_heaps,
            use_prelude = List(File.platform_path(boot)),
            eval_main = Command_Line.ML_tool(List("Isabelle_Process.init_build ()")))

        val rc =
          POSIX_Interrupt.handler { process.terminate() } {
            process.await_startup()


            /* 4. the boot */

            session.protocol_command("TAT.boot",
              (File.platform_path(dir) :: port.toString :: plugins).map(XML.Encode.string): _*)


            /* 5. the ending */

            val (rc, messages) = finished.guarded_access(st => st.map(x => (x, st)))
            session.stop()
            messages.foreach(progress.echo_error_message(_))
            rc
          }
        if (rc != Process_Result.RC.ok) sys.exit(rc)
      })
}

class TAT_Tools extends Isabelle_Scala_Tools(TAT.tat_new_tool, TAT.tat_tool)
