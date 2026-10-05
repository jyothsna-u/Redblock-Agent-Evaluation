import statistics, random
from redscore import score, tokens, JUDGE_CACHE, CONFIG

GT = '''URL "https://qa-venus.cellularautomata.company/settings/team"
STEPS
    - CLICK ON "Invite Button" INTENT "To start with the process of inviting the user"
    - FILL $legal_first_name INTO "Legal first name box" INTENT "To fill $legal_first_name in the legal first name box"
    - FILL $legal_last_name INTO "Legal last name box" INTENT "To fill $legal_last_name in the legal last name box"
    - FILL $email INTO "Email box" INTENT "To fill $email in the email box"
    - CLICK ON "Next Button on the bottom right" INTENT "To go to next page of inviting user process"
    - CLICK ON "Radio Button for $role" INTENT "To select $role for the newly added user"
    - CLICK ON "Next Button on the bottom right" INTENT "To complete role selection process and proceed with the next step"
    - IF $role EQUALS "Custom"
        - CLICK ON "Next Button" INTENT "To finish custom options selection part and proceed with inviting user"
    - CLICK ON "Invite Button" INTENT "To submit the details and complete the process of inviting the user"
'''
GT_PARAMS = '''$email = "john1@redblockdemo.com"
$legal_first_name = "john"
$legal_last_name = "smith"
$role = "Admin"
'''
CRITICAL = {9}   # step 9 = final "Invite Button" (submit)

# ---- Run 1: realistic output with several different mistakes
GEN1 = '''URL "https://qa-venus.cellularautomata.company/settings/team"
STEPS
    - CLICK ON "Invite user button at top right" INTENT "Open the invite user form"
    - FILL $first_name INTO "First name input" INTENT "Enter $first_name"
    - FILL_AND_ENTER $last_name INTO "Last name input" INTENT "Enter $last_name"
    - CLICK ON "Next button" INTENT "Go to role selection"
    - FILL $user_email INTO "Email input" INTENT "Enter $user_email"
    - CLICK ON "Admin radio button" INTENT "Select the Admin role"
    - CLICK ON "Next button" INTENT "Continue"
    - CLICK ON "Invite button" INTENT "Send the invitation"
    - CLICK ON "Close button on the success dialog" INTENT "Close the confirmation"
'''
GEN1_PARAMS = '''$user_email = "john1@redblockdemo.com"
$first_name = "john"
$last_name = "smith"
'''

# ---- Run 2: same video, second generation - nearly right
GEN2 = '''URL "https://qa-venus.cellularautomata.company/settings/team"
STEPS
    - CLICK ON "Invite user button at top right" INTENT "Open the invite user form"
    - FILL $first_name INTO "First name input" INTENT "Enter $first_name"
    - FILL $last_name INTO "Last name input" INTENT "Enter $last_name"
    - FILL $user_email INTO "Email input" INTENT "Enter $user_email"
    - CLICK ON "Next button" INTENT "Go to role selection"
    - CLICK ON "Radio button for $user_role" INTENT "Select $user_role"
    - CLICK ON "Next button" INTENT "Continue"
    - IF $user_role EQUALS "Custom"
        - CLICK ON "Next button" INTENT "Finish custom options"
    - CLICK ON "Invite button" INTENT "Send the invitation"
    - CLICK ON "Close button on the success dialog" INTENT "Close the confirmation"
'''
GEN2_PARAMS = GEN1_PARAMS + '$user_role = "Admin"\n'

# ---- Run 3: same video, third generation - drops the final submit
GEN3 = '''URL "https://qa-venus.cellularautomata.company/settings/team"
STEPS
    - CLICK ON "Invite user button at top right" INTENT "Open the invite user form"
    - FILL $first_name INTO "First name input" INTENT "Enter $first_name"
    - FILL $last_name INTO "Last name input" INTENT "Enter $last_name"
    - FILL $user_email INTO "Email input" INTENT "Enter $user_email"
    - CLICK ON "Next button" INTENT "Go to role selection"
    - CLICK ON "Radio button for $user_role" INTENT "Select $user_role"
    - CLICK ON "Next button" INTENT "Continue"
'''
GEN3_PARAMS = GEN2_PARAMS

# ---- cached judge answers (pinned model, temperature 0). Only grey-zone pairs reach the judge.
gp = {"$role": ("Admin", False)}
def key(a, b): return (" ".join(sorted(tokens(a, gp))), " ".join(sorted(tokens(b, gp))))
JUDGE_CACHE[key("Invite Button", "Invite user button at top right")] = 1.0
JUDGE_CACHE[key("Next Button on the bottom right", "Next button")] = 1.0
JUDGE_CACHE[key("Invite Button", "Close button on the success dialog")] = 0.0

def report(name, r, verbose=False):
    gt, gen = r["gt"], r["gen"]
    print(f"\n==================== {name} ====================")
    if verbose:
        print("Variable mapping (GEN -> GT):", r["mapping"])
        print("\nPairs:")
        for i, j in r["pairs"] + r["order_err"]:
            s, c = r["S"][i][j]
            tag = "ORDER_ERROR" if (i, j) in r["order_err"] else "MATCH"
            src = c.get("target_src")
            d = f" dice={c['dice']:.3f}->judge" if src == "judge" else ""
            print(f"  GT{gt.steps[i].idx} (w={gt.steps[i].weight:.0f}) <-> GEN{gen.steps[j].idx}  "
                  f"A={c['A']:.2f} T={c['T']:.3f}{d} V={c['V']:.2f} B={c['B']:.0f}  S={s:.4f}  {tag}")
        for i in r["missed"]:
            print(f"  GT{gt.steps[i].idx} MISSED: {gt.steps[i].raw[:70]}")
        for j in r["extra"]:
            print(f"  GEN{gen.steps[j].idx} EXTRA: {gen.steps[j].raw[:70]}")
        print("Hard-coded values:", r["hardcoded"])
    print(f"credit={r['credit']:.4f}  W_gt={r['W_gt']}  W_gen={r['W_gen']}")
    print(f"Coverage={r['coverage']:.4f} Precision={r['precision']:.4f} StepF1={r['step_f1']:.4f}")
    print(f"Structure={r['structure']:.4f} Params={r['params']:.4f} Order={r['order']:.4f} URL={r['url']:.2f}")
    print(f"RedScore={r['redscore']:.2f}  critical_missed={r['critical_missed']}  verdict={r['verdict']}")

r1 = score(GT, GT_PARAMS, GEN1, GEN1_PARAMS, CRITICAL); report("RUN 1", r1, True)
r2 = score(GT, GT_PARAMS, GEN2, GEN2_PARAMS, CRITICAL); report("RUN 2", r2, True)
r3 = score(GT, GT_PARAMS, GEN3, GEN3_PARAMS, CRITICAL); report("RUN 3", r3, True)

# alternative alignment check: why GT1 is not paired with GEN8 (both say "Invite")
S = r1["S"]
print("\nS(GT1,GEN1)=%.4f  S(GT1,GEN8)=%.4f  S(GT9,GEN8)=%.4f" % (S[0][0][0], S[0][7][0], S[8][7][0]))

scores = [r1["redscore"], r2["redscore"], r3["redscore"]]
crit = any(r["critical_missed"] for r in (r1, r2, r3))
print("\nTask summary: runs=", [round(s, 2) for s in scores],
      "mean=%.2f min=%.2f sd=%.2f" % (statistics.mean(scores), min(scores), statistics.stdev(scores)),
      "pass^3=", all(s >= CONFIG["pass_score"] for s in scores) and not crit)

# ---- version comparison example (task means, v1 vs v2), paired bootstrap
v1 = {"create_account": statistics.mean(scores), "remove_account": 91.2, "deactivate": 88.4,
      "activate": 93.0, "add_entitlement": 79.5, "update_account": 85.1}
v2 = {"create_account": 89.6, "remove_account": 92.0, "deactivate": 90.1,
      "activate": 92.4, "add_entitlement": 86.3, "update_account": 84.7}
d = [v2[k] - v1[k] for k in v1]
random.seed(7)
boots = sorted(statistics.mean(random.choices(d, k=len(d))) for _ in range(10000))
print("\nv1 mean=%.2f v2 mean=%.2f  delta=%.2f  95%% CI=[%.2f, %.2f]" % (
    statistics.mean(v1.values()), statistics.mean(v2.values()), statistics.mean(d), boots[250], boots[9749]))
print("per-task deltas:", {k: round(v2[k] - v1[k], 2) for k in v1})
