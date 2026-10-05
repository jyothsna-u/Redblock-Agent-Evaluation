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


def test_task_folder_without_gt_is_a_clean_error(tmp_path, capsys):
    code = main(["task", "--task", str(tmp_path / "missing"), "--gen-version", "v1", "--results", str(tmp_path)])
    assert code == 1
    assert "gt.redflow not found" in capsys.readouterr().err
