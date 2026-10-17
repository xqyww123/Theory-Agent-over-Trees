(*  Title:      Isabelle_Std/ML/TAT_Mixfix.ML

A mixfix annotation as the plugin writes it (docs/node_classes/COMMON.md §4), read
with Isabelle's own parser of the annotation, Parse.mixfix, under the context's
keywords: what the file carries is what the command receives.
*)

signature TAT_MIXFIX =
sig
  val read_text : 'a parser -> string -> Proof.context -> string -> 'a
    (*Isar text read whole by the parser under the context's keywords; a text
      it does not read whole is an error, "Malformed <what>: <text>", the
      operation's messages*)
  val read : Proof.context -> string option -> mixfix
    (*NoSyn for none; otherwise the annotation text in its ascii, parentheses
      included, as `mixfix_text` writes it, through Parse.mixfix*)
end

structure TAT_Mixfix : TAT_MIXFIX =
struct

fun read_text parser what ctxt text =
  (case Scan.read Token.stopper parser
          (filter Token.is_proper (Token.explode (Thy_Header.get_keywords' ctxt) Position.none text)) of
    SOME x => x
  | NONE => error ("Malformed " ^ what ^ ": " ^ quote text))

fun read _ NONE = NoSyn
  | read ctxt (SOME text) = read_text Parse.mixfix "mixfix annotation" ctxt text

end
