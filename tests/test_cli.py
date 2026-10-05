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
    assert "venus-jml-create-account  gen spec-example  rules rules-v1  critical: GT9" in out
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


def test_task_folder_without_gt_is_a_clean_error(tmp_path, capsys):
    code = main(["task", "--task", str(tmp_path / "missing"), "--gen-version", "v1", "--results", str(tmp_path)])
    assert code == 1
    assert "gt.redflow not found" in capsys.readouterr().err
