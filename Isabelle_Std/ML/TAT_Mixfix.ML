(*  Title:      Isabelle_Std/ML/TAT_Mixfix.ML

A mixfix annotation as the plugin writes it (docs/node_classes/COMMON.md §4), read
with Isabelle's own parser of the annotation, Parse.mixfix, under the context's
keywords: what the file carries is what the command receives.
*)

signature TAT_MIXFIX =
sig
  val read : Proof.context -> string option -> mixfix
    (*NoSyn for none; otherwise the annotation text in its ascii, parentheses
      included, as `mixfix_text` writes it, through Parse.mixfix -- a text it
      does not read whole is an error, the operation's messages*)
end

structure TAT_Mixfix : TAT_MIXFIX =
struct

fun read _ NONE = NoSyn
  | read ctxt (SOME text) =
      let val tokens = filter Token.is_proper (Token.explode (Thy_Header.get_keywords' ctxt) Position.none text) in
        (case Scan.read Token.stopper Parse.mixfix tokens of
          SOME mixfix => mixfix
        | NONE => error ("Malformed mixfix annotation: " ^ quote text))
      end

end
