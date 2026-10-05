# RedScore: redflow Generation Benchmark

<!-- tab: RedScore: redflow Generation Benchmark -->

# RedScore: redflow Generation Benchmark

2026-10-01 · @someone

## Overview

RedScore compares each generated redflow (GEN) with the correct redflow for the task (GT) in five moves:

1. Check the syntax.
2. Map steps and variables.
3. Score each step on four parameters.
4. Subtract penalties.
5. Average the 3 runs.

| Number | What it means | Range |
| --- | --- | --- |
| Base Score | How well GEN's steps match GT's steps, with missing and extra steps counted | 0 to 100 |
| Penalties | Points taken off for sequence, variable, logic-block and critical-step problems | subtracted |
| **Final Score** | Base Score minus penalties, never below 0 | 0 to 100 per run |
| **Task Score** | Average of the 3 runs' Final Scores | 0 to 100 per task |

Each task needs, once:

- the **GT redflow** and its execution parameters, proven by a successful run
- the GT's **critical steps** marked: the step that commits the change, like the final Invite, Save or Submit
- the **video or PDF** the generator reads

The URL line is not scored. The user supplies it on every run, so it is not an AI output.

## Flowchart

[Embedded widget: RedScore flow · 6 steps, 1 syntax gate, 4 penalties](node/0c580bda-aacd)

Each of the 3 generated runs goes through the flow on its own. A syntax error ends that run with a Final Score of 0; the 3 Final Scores are then averaged.

## Algorithm, step by step

Steps 1 to 5 run once for each generated redflow; step 6 combines the 3 runs of a task.

### Step 1: Syntax validation

Run the redflow validator on GEN. Any error means GEN cannot run: that run's Final Score is 0 and steps 2 to 5 are skipped.

### Step 2: Map steps and variables

One LLM call (fixed model, temperature 0) receives both redflows with numbered steps and returns:

- **pairs**: the GEN step that does the same action on the same element as each GT step; each step is used at most once
- for each pair: **same element?** and **same intent?**, each yes or no
- **missing steps**: GT steps with no partner
- **extra steps**: GEN steps with no partner

Code then does three checks:

- **Variables:** pair each GEN variable with the GT variable that has the same default value, e.g. `$first_name = "john"` with `$legal_first_name = "john"`. A GT variable with no partner is a **missing variable**.
- **Sequence:** read the pairs in GT order. The GEN step numbers must keep rising; a pair where the number drops is **out of sequence**.
- **Logic blocks:** every IF/ELSE, FOR\_EACH, WHEN, UNTIL and WAIT\_UNTIL in GT must exist in GEN with the same condition, and its steps must sit inside it.

The mapping is saved, so a person can review it.

### Step 3: Score each step

Every mapped pair gets up to 1 point from four parameters. A missing GT step scores 0.

| Parameter | Points | Checked by |
| --- | --- | --- |
| Keyword is the same (CLICK, FILL, FILL\_AND\_ENTER, SELECT, HOVER) | 0.3 | code |
| Element is the same | 0.4 | LLM, from step 2 |
| Variables are the same after mapping, nothing hard-coded | 0.2 | code |
| Intent means the same | 0.1 | LLM, from step 2 |

### Step 4: Base Score

Missing steps are already in the total with 0 points; each extra step adds one empty slot. So both missing and extra steps pull the score down.

```latex
\text{Base Score} = \frac{\sum \text{step points}}{N_{GT} + N_{extra}} \times 100
```

### Step 5: Penalties and Final Score

| Problem found | Penalty | Why it matters |
| --- | --- | --- |
| Step out of sequence | −5 per step | e.g. Next clicked before the email is filled |
| Missing variable (no GEN partner, including a hard-coded value) | −5 per variable | works only for the test value |
| Logic block mismatch (IF/ELSE, FOR\_EACH, WHEN, UNTIL, WAIT\_UNTIL missing, wrong condition, or its steps outside it) | −10 per block | wrong result for some inputs |
| Critical step missing | −30 | run finishes, but the job is never done |

A missing step already scores 0 in the Base Score. Its penalty covers what it breaks beyond that one step.

```latex
\text{Final Score} = \max\left(0,\ \text{Base Score} - \sum \text{penalties}\right)
```

### Step 6: Task Score

```latex
\text{Task Score} = \frac{\text{Final}_1 + \text{Final}_2 + \text{Final}_3}{3}
```

Also record the lowest of the 3 Final Scores, to see how unstable the generator is.

## Worked example: Venus-JML Create Account

On the real Venus-JML Create Account GT, three generated runs score Final 55.0, 90.0 and 37.8, so the **Task Score is 60.9**. The GEN runs are realistic examples written to trigger each penalty.

### The GT

Nine steps, one IF block (around GT8), and one critical step: GT9, the final Invite.

```
STEPS
    - CLICK ON "Invite Button" INTENT "To start with the process of inviting the user"                                   # GT1
    - FILL $legal_first_name INTO "Legal first name box" INTENT "To fill $legal_first_name in the legal first name box" # GT2
    - FILL $legal_last_name INTO "Legal last name box" INTENT "To fill $legal_last_name in the legal last name box"    # GT3
    - FILL $email INTO "Email box" INTENT "To fill $email in the email box"                                            # GT4
    - CLICK ON "Next Button on the bottom right" INTENT "To go to next page of inviting user process"                 # GT5
    - CLICK ON "Radio Button for $role" INTENT "To select $role for the newly added user"                              # GT6
    - CLICK ON "Next Button on the bottom right" INTENT "To complete role selection process and proceed"              # GT7
    - IF $role EQUALS "Custom"
        - CLICK ON "Next Button" INTENT "To finish custom options selection part and proceed with inviting user"      # GT8
    - CLICK ON "Invite Button" INTENT "To submit the details and complete the process of inviting the user"          # GT9, critical

$email = "john1@redblockdemo.com"
$legal_first_name = "john"
$legal_last_name = "smith"
$role = "Admin"
```

### Run 1, step by step

**Step 1, syntax:** valid.

```
STEPS
    - CLICK ON "Invite user button at top right" INTENT "Open the invite user form"          # GEN1
    - FILL $first_name INTO "First name input" INTENT "Enter $first_name"                   # GEN2
    - FILL_AND_ENTER $last_name INTO "Last name input" INTENT "Enter $last_name"            # GEN3
    - CLICK ON "Next button" INTENT "Go to role selection"                                   # GEN4
    - FILL $user_email INTO "Email input" INTENT "Enter $user_email"                        # GEN5
    - CLICK ON "Admin radio button" INTENT "Select the Admin role"                           # GEN6
    - CLICK ON "Next button" INTENT "Continue"                                                # GEN7
    - CLICK ON "Invite button" INTENT "Send the invitation"                                   # GEN8
    - CLICK ON "Close button on the success dialog" INTENT "Close the confirmation"          # GEN9

$user_email = "john1@redblockdemo.com"
$first_name = "john"
$last_name = "smith"
```

**Step 2, mapping:**

| GEN variable | Default value | GT variable |
| --- | --- | --- |
| $user\_email | john1@redblockdemo.com | $email |
| $first\_name | john | $legal\_first\_name |
| $last\_name | smith | $legal\_last\_name |
| none | Admin | $role, **missing** (Admin typed into the element description) |

In GT order the GEN step numbers run 1, 2, 3, 5, **4**, 6, 7, 8. The drop marks GT5 as out of sequence: GEN clicks Next before filling the email. GT8 and its IF block have no partner. GEN9 is extra.

**Step 3, step points:**

| GT step | GEN step | Keyword 0.3 | Element 0.4 | Variables 0.2 | Intent 0.1 | Points |
| --- | --- | --- | --- | --- | --- | --- |
| GT1 Invite | GEN1 | 0.3 | 0.4 | 0.2 | 0.1 | **1.0** |
| GT2 First name | GEN2 | 0.3 | 0.4 | 0.2 | 0.1 | **1.0** |
| GT3 Last name | GEN3 | 0 (FILL\_AND\_ENTER) | 0.4 | 0.2 | 0.1 | **0.7** |
| GT4 Email | GEN5 | 0.3 | 0.4 | 0.2 | 0.1 | **1.0** |
| GT5 Next | GEN4 | 0.3 | 0.4 | 0.2 | 0.1 | **1.0** |
| GT6 Radio for $role | GEN6 | 0.3 | 0.4 | 0 (Admin hard-coded) | 0.1 | **0.8** |
| GT7 Next | GEN7 | 0.3 | 0.4 | 0.2 | 0.1 | **1.0** |
| GT8 IF Custom: Next | missing |  |  |  |  | **0** |
| GT9 Invite, critical | GEN8 | 0.3 | 0.4 | 0.2 | 0.1 | **1.0** |
| extra | GEN9 Close dialog |  |  |  |  | adds 1 slot |

**Step 4, Base Score:**

```latex
\text{Base} = \frac{1 + 1 + 0.7 + 1 + 1 + 0.8 + 1 + 0 + 1}{9 + 1} \times 100 = \frac{7.5}{10} \times 100 = 75.0
```

**Step 5, penalties:**

| Problem | Where | Penalty |
| --- | --- | --- |
| Out of sequence | GT5 Next, before the email | −5 |
| Missing variable | $role | −5 |
| Logic block mismatch | IF $role EQUALS "Custom" missing | −10 |
| Critical step missing | none, GT9 is present | 0 |

```latex
\text{Final}_1 = \max(0,\ 75.0 - 20) = 55.0
```

### All three runs

Run 2 matched every GT step and only added the extra Close click. Run 3 matched GT1 to GT7 with no variable or order errors, but dropped the IF block and the final Invite.

| Run | Points | Slots | Base Score | Penalties | Final Score |
| --- | --- | --- | --- | --- | --- |
| 1 | 7.5 | 10 | 75.0 | sequence −5, variable −5, IF block −10 | **55.0** |
| 2 | 9.0 | 10 | 90.0 | none | **90.0** |
| 3 | 7.0 | 9 | 77.8 | IF block −10, critical step −30 | **37.8** |

```latex
\text{Task Score} = \frac{55.0 + 90.0 + 37.8}{3} = 60.9
```

Lowest run: 37.8. Without the critical-step penalty, Run 3 would score 67.8 even though no user is ever invited.

## Comparing generator versions

Every generator version runs the same set of tasks, 3 runs each, and is reported with these numbers:

| Benchmark number | How it is computed |
| --- | --- |
| Mean Task Score | average Task Score across all tasks |
| Mean Base Score | shows step capture on its own, before penalties |
| Penalties by type | total points lost to sequence, variables, logic blocks and critical steps |
| Syntax failures | runs that scored 0 at step 1 |
| Critical-step misses | runs that lost the final Invite, Save or Submit; any increase is a regression |

Compare a new version with the previous one task by task. A change counts as real only if the 95% bootstrap interval of the per-task differences excludes 0. List every task that got better or worse, so an average gain cannot hide a drop on one Skill.

Store every GEN redflow, its mapping, and the version of the weights and penalties. When the rules change, re-score the stored GENs, so all versions stay on one scale.

## Open decisions

- Parameter weights: 0.3 keyword, 0.4 element, 0.2 variables, 0.1 intent
- Penalty sizes: 5 for sequence, 5 per variable, 10 per logic block, 30 for a critical step
- Pass mark for a run, e.g. Final Score of 90 or above
- Which LLM and prompt do the mapping, pinned for every run
- Who marks the critical steps on each GT

