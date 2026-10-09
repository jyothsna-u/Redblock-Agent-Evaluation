import json
import sqlite3
from pathlib import Path

from redscore.cli import main

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
TASK = TASKS / "venus-jml-create-account"
FIXTURES = ROOT / "tests" / "fixtures" / "venus"


def _run_venus(results: Path) -> int:
    return main(["task", "--task", str(TASK), "--gen-version", "spec-example",
                 "--mappings", str(FIXTURES), "--results", str(results)])


def test_task_command_end_to_end(tmp_path, capsys):
    assert _run_venus(tmp_path) == 0
    out = capsys.readouterr().out
    assert "venus-jml-create-account  gen spec-example  rules rules-v1  judge fixture  scale " in out
    assert "critical: GT9" in out
    assert "Task Score 60.9  lowest 37.8" in out
    run_dir = tmp_path / "venus-jml-create-account" / "spec-example" / "run_1"
    assert {p.name for p in run_dir.iterdir()} == {"gen.redflow", "mapping.json", "score_rules-v1.json"}
    db = sqlite3.connect(str(tmp_path / "redscore.db"))
    assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3
    assert round(db.execute("SELECT task_score FROM tasks").fetchone()[0], 1) == 60.9


def test_rescore_reuses_stored_mappings(tmp_path, capsys):
    _run_venus(tmp_path)
    rules = tmp_path / "rules_test.yaml"
    rules.write_text((ROOT / "rules" / "v1.yaml").read_text()
                     .replace("version: rules-v1", "version: rules-test")
                     .replace("critical_step: 30", "critical_step: 50"))
    capsys.readouterr()
    assert main(["rescore", "--rules", str(rules), "--tasks", str(TASKS), "--results", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "run 3: Base  77.8  Final  17.8" in out
    assert (tmp_path / "venus-jml-create-account/spec-example/run_3/score_rules-test.json").exists()


def test_task_writes_history_folder(tmp_path, capsys):
    _run_venus(tmp_path)
    (hist,) = (tmp_path / "history").iterdir()
    assert hist.name.endswith("_venus-jml-create-account_spec-example_rules-v1")
    assert f"history: {hist}" in capsys.readouterr().out
    assert {p.name for p in hist.iterdir()} == {"summary.json", "run_1.json", "run_2.json", "run_3.json"}
    summary = json.loads((hist / "summary.json").read_text())
    assert summary["execution"]["status"] == "ok"
    assert summary["execution"]["command"].startswith("redscore task --task")
    assert summary["result"]["task_score"] == 60.93
    assert summary["rules"]["penalties"]["critical_step"] == 30
    assert summary["runs"][2]["biggest_cuts"][0]["what"] == "critical_step GT9"


def test_history_cuts_add_up_to_final(tmp_path):
    _run_venus(tmp_path)
    (hist,) = (tmp_path / "history").iterdir()
    for n in (1, 2, 3):
        run = json.loads((hist / f"run_{n}.json").read_text())
        why, score = run["explanation"], run["score"]
        base_cuts = sum(c["points"] for c in why["cuts"] if c["stage"] != "penalty")
        assert abs(100 - base_cuts - score["base"]) < 0.05
        assert abs(100 - sum(c["points"] for c in why["cuts"]) - score["final"]) < 0.05
        assert run["mapping_source"].startswith("fixture:")
    run1 = json.loads((hist / "run_1.json").read_text())["explanation"]
    assert {c["what"] for c in run1["cuts"]} >= {"GT3 keyword", "GT6 variables", "GT8 missing", "GEN9 extra",
                                                  "out_of_sequence GT5", "missing_variable $role",
                                                  "logic_block B1"}


def test_rescore_writes_its_own_history(tmp_path):
    _run_venus(tmp_path)
    main(["rescore", "--rules", str(ROOT / "rules" / "v1.yaml"), "--tasks", str(TASKS), "--results", str(tmp_path)])
    names = sorted(p.name for p in (tmp_path / "history").iterdir())
    assert len(names) == 2 and names[1].endswith("_rescore")


# ---------------------------------------------------------------- trust guarantees

import shutil  # noqa: E402

from redscore.store import Store  # noqa: E402


def _venus_copy(tmp_path: Path) -> Path:
    """A writable copy of the Venus task, so tests can edit its GT."""
    task = tmp_path / "tasks" / "venus-jml-create-account"
    shutil.copytree(TASK, task, ignore=shutil.ignore_patterns("*.mp4"))
    return task


def test_rerun_of_a_scored_version_is_refused_without_force(tmp_path, capsys):
    _run_venus(tmp_path)
    capsys.readouterr()
    assert _run_venus(tmp_path) == 1
    assert "already scored" in capsys.readouterr().err


def test_force_keeps_the_old_record_under_superseded(tmp_path):
    _run_venus(tmp_path)
    assert main(["task", "--task", str(TASK), "--gen-version", "spec-example", "--mappings", str(FIXTURES),
                 "--results", str(tmp_path), "--force"]) == 0
    record = tmp_path / "venus-jml-create-account" / "spec-example"
    (old,) = (record / "superseded").iterdir()
    assert (old / "record.json").exists() and (old / "run_1" / "score_rules-v1.json").exists()
    db = sqlite3.connect(str(tmp_path / "redscore.db"))
    assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3


def test_failed_run_is_not_a_zero_and_resume_finishes_it(tmp_path, capsys):
    mappings = tmp_path / "mappings"
    shutil.copytree(FIXTURES, mappings)
    (mappings / "mapping_run_2.json").unlink()        # the judge "fails" on run 2
    args = ["task", "--task", str(TASK), "--gen-version", "v1", "--mappings", str(mappings), "--results", str(tmp_path)]
    assert main(args) == 2
    out = capsys.readouterr().out
    assert "run 2: NOT SCORED" in out and "INCOMPLETE" in out and "  Task Score " not in out
    db = sqlite3.connect(str(tmp_path / "redscore.db"))
    assert db.execute("SELECT status, final FROM runs WHERE run=2").fetchone() == ("error", None)
    assert db.execute("SELECT status, task_score FROM tasks").fetchone() == ("incomplete", None)

    shutil.copy(FIXTURES / "mapping_run_2.json", mappings)
    (mappings / "mapping_run_1.json").unlink()        # resume must not call the judge for run 1 again
    assert main(args + ["--resume"]) == 0
    assert "Task Score 60.9" in capsys.readouterr().out
    assert db.execute("SELECT status FROM tasks").fetchone() == ("complete",)


def test_rescore_uses_the_gt_snapshot_not_the_live_gt(tmp_path, capsys):
    task = _venus_copy(tmp_path)
    results = tmp_path / "results"
    main(["task", "--task", str(task), "--gen-version", "v1", "--mappings", str(FIXTURES), "--results", str(results)])
    gt = task / "gt.redflow"
    gt.write_text(gt.read_text().replace("STEPS\n", 'STEPS\n    - CLICK ON "New first step" INTENT "x"\n', 1))
    capsys.readouterr()
    assert main(["rescore", "--rules", str(ROOT / "rules" / "v1.yaml"), "--results", str(results)]) == 0
    assert "Task Score 60.9" in capsys.readouterr().out


def test_legacy_record_needs_explicit_adoption(tmp_path, capsys):
    _run_venus(tmp_path)
    record = tmp_path / "venus-jml-create-account" / "spec-example"
    (record / "record.json").unlink()
    (record / "gt.redflow").unlink()
    rescore = ["rescore", "--rules", str(ROOT / "rules" / "v1.yaml"), "--tasks", str(TASKS), "--results", str(tmp_path)]
    capsys.readouterr()
    assert main(rescore) == 2
    assert "stored before GT snapshots" in capsys.readouterr().err
    assert main(rescore + ["--adopt-live-gt"]) == 0
    rec = json.loads((record / "record.json").read_text())
    assert rec["gt_adopted_from_live_task"] and rec["judge"] == "fixture"


def test_compare_refuses_different_scales(tmp_path, capsys):
    _run_venus(tmp_path)
    rules = tmp_path / "v1_edited.yaml"      # same version label, different values
    rules.write_text((ROOT / "rules" / "v1.yaml").read_text().replace("critical_step: 30", "critical_step: 31"))
    main(["task", "--task", str(TASK), "--gen-version", "v2", "--mappings", str(FIXTURES),
          "--results", str(tmp_path), "--rules", str(rules)])
    capsys.readouterr()
    assert main(["compare", "spec-example", "v2", "--results", str(tmp_path)]) == 1
    assert "different scales (rules_sha256" in capsys.readouterr().err


def test_compare_same_scale_reports(tmp_path, capsys):
    _run_venus(tmp_path)
    main(["task", "--task", str(TASK), "--gen-version", "v2", "--mappings", str(FIXTURES), "--results", str(tmp_path)])
    capsys.readouterr()
    assert main(["compare", "spec-example", "v2", "--results", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Same scale on both sides: judge fixture" in out and "over 1 common task(s)" in out


def test_old_database_is_migrated(tmp_path):
    db = sqlite3.connect(str(tmp_path / "redscore.db"))
    db.executescript("CREATE TABLE runs (task_id TEXT, gen_version TEXT, run INTEGER, rules_version TEXT, final REAL);"
                     "CREATE TABLE tasks (task_id TEXT, gen_version TEXT, rules_version TEXT, task_score REAL);"
                     "INSERT INTO tasks VALUES ('t', 'v1', 'rules-v1', 50.0);")
    db.commit()
    store = Store(tmp_path)
    (row,) = store.tasks("v1", "rules-v1")
    assert row["task_score"] == 50.0 and row["status"] is None and row["judge"] is None


def test_task_folder_without_gt_is_a_clean_error(tmp_path, capsys):
    code = main(["task", "--task", str(tmp_path / "missing"), "--gen-version", "v1", "--results", str(tmp_path)])
    assert code == 1
    assert "gt.redflow not found" in capsys.readouterr().err
