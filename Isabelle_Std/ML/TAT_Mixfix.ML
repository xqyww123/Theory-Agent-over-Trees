(*  Title:      Isabelle_Std/ML/TAT_Mixfix.ML

A mixfix annotation as the plugin writes it (docs/node_classes/COMMON.md §4), read
with Isabelle's own parser of the annotation, Parse.mixfix, under the context's
keywords: what the file carries is what the command receives; and its converse,
the construct's arm of an annotation Isabelle holds.
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
  val fixes : Proof.context -> (string * string option * string option) list ->
    (binding * string option * mixfix) list
    (*the variables as `Variable_With_Syntax`'s wire sends them -- each its name,
      its type or none, its annotation text or none -- as the commands take
      them, the annotation read under the context's keywords*)
  val arm_of : mixfix -> (string * string * int list option * int option) option
    (*the construct's arm of an annotation: its form, its symbol or template, a
      template's argument priorities when there are any and its priority when
      not the default; NONE for NoSyn and for the forms `MIXFIX_DEFS` leaves out
      -- a structure, a binder whose body priority differs from its own*)
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

fun fixes ctxt variables =
  map (fn (name, typ, syntax) => (Binding.name name, typ, read ctxt syntax)) variables

fun arm_of NoSyn = NONE
  | arm_of (Mixfix (sy, ps, p, _)) =
      SOME ("mixfix", Input.string_of sy, if null ps then NONE else SOME ps, if p = 1000 then NONE else SOME p)
  | arm_of (Infix (sy, p, _)) = SOME ("infix", Input.string_of sy, NONE, SOME p)
  | arm_of (Infixl (sy, p, _)) = SOME ("infixl", Input.string_of sy, NONE, SOME p)
  | arm_of (Infixr (sy, p, _)) = SOME ("infixr", Input.string_of sy, NONE, SOME p)
  | arm_of (Binder (sy, p, q, _)) = if p = q then SOME ("binder", Input.string_of sy, NONE, SOME p) else NONE
  | arm_of (Structure _) = NONE

end
