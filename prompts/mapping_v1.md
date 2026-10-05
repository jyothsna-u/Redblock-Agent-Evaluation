You compare two redflow scripts for the same task in a web application.
GT is the ground-truth redflow. GEN was generated from a screen recording or SOP.
Your job is only to MAP steps; you do not score anything.

redflow basics:
- Each action step is one line: CLICK / DOUBLE_CLICK / RIGHT_CLICK / HOVER ON "<element>",
  FILL / FILL_AND_ENTER / UPLOAD $var INTO "<element>", SELECT $var FROM "<element>",
  GRAB "<what to read>" INTO $var / GRAB ALL "<items>" INTO $list[] (reads a value off the page),
  GOTO "<url>", WAIT <seconds>, or BROWSER_FIND $var (finds the text in $var on the page, like Ctrl+F,
  and scrolls it into view). INTENT "..." says why the step is done; GOTO, WAIT and BROWSER_FIND have no INTENT.
- For a step with no quoted element, the element is what it acts on: the text BROWSER_FIND looks for,
  the URL for GOTO. For a step with no INTENT, judge same_intent by what the step is for in the flow.
- Steps are labelled [GT1], [GT2] ... and [GEN1], [GEN2] ...; logic blocks (IF, ELIF, FOR_EACH, WHEN, UNTIL,
  WAIT_UNTIL) are labelled [B1], [B2] ... in each script.
- Variables ($name) are defined at the bottom with their default values. Variable names may differ between
  GT and GEN; a variable's value tells you what it stands for (e.g. "Radio Button for $role" with
  $role = "Admin" is the same element as "Admin radio button").

Task 1, pairs. Pair each GT step with the GEN step that performs the same action on the same UI element
at the same point of the task.
- Each GT step and each GEN step may appear in at most one pair.
- Pair steps even if they are in a different order, inside a different block, or use a different keyword
  (e.g. FILL vs FILL_AND_ENTER on the same field), as long as they act on the same element for the same purpose.
- When a GT element appears several times (e.g. two "Next" buttons), pair by position in the flow and purpose.
- Do not pair a GT step with a GEN step that acts on a different element just because it is nearby.
- For each pair give:
  - same_element: true if both steps target the same UI element on the same page, false otherwise.
  - same_intent: true if the two INTENTs mean the same thing in this flow, false otherwise.

Task 2, runtime blocks. For each GT WHEN / UNTIL / WAIT_UNTIL block, give the GEN block of the same kind whose
condition describes the same page state, if there is one, with same_condition true/false.
Leave the list empty if GT has no such blocks. Ignore IF, ELIF and FOR_EACH blocks here.

Answer with ONLY a JSON object, no prose and no code fence:
{"pairs": [{"gt": <GT step number>, "gen": <GEN step number>, "same_element": true|false, "same_intent": true|false}],
 "missing_gt": [<GT step numbers with no pair>],
 "extra_gen": [<GEN step numbers with no pair>],
 "runtime_blocks": [{"gt_block": "B<n>", "gen_block": "B<n>", "same_condition": true|false}]}

GT:
{{GT}}

GEN:
{{GEN}}
