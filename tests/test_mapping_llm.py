import json
from pathlib import Path

import pytest

from redscore import llm
from redscore.mapping import MappingError, build_prompt, load_prompt, render_numbered
from redscore.parser import parse

ROOT = Path(__file__).resolve().parent.parent
TASK = ROOT / "tasks" / "venus-jml-create-account"
GT = parse((TASK / "gt.redflow").read_text())
GEN = parse((TASK / "gen/run_1.redflow").read_text())
GOOD = json.loads((ROOT / "tests/fixtures/venus/mapping_run_1.json").read_text())


def test_render_numbered_labels_steps_and_blocks():
    text = render_numbered(GT, "GT")
    lines = text.splitlines()
    assert lines[1].startswith("[GT1]") and "Invite Button" in lines[1]
    assert any(line.startswith("[B1]") and "IF $role" in line for line in lines)
    assert any(line.startswith("[GT9]") for line in lines)
    assert '$role = "Admin"' in text


def test_prompt_version_tracks_content():
    template, version = load_prompt()
    assert version.startswith("mapping_v1@")
    prompt = build_prompt(GT, GEN, template)
    assert "{{GT}}" not in prompt and "[GEN9]" in prompt


def test_extract_json_handles_think_and_fences():
    raw = '<think>pairs...{not json}</think>\n```json\n{"pairs": []}\n```'
    assert llm._extract_json(raw) == {"pairs": []}
    with pytest.raises(MappingError):
        llm._extract_json("no json here")


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("REASONING_MODEL_NAME", "test-model")
    monkeypatch.chdir(tmp_path)   # no .env picked up
    return tmp_path


def test_llm_mapper_caches(env, monkeypatch):
    calls = []

    def fake_chat(model, messages):
        calls.append(messages)
        return json.dumps(GOOD)

    monkeypatch.setattr(llm, "_chat", fake_chat)
    mapper = llm.llm_mapper(cache_dir=env / "cache")
    m1 = mapper(GT, GEN)
    m2 = mapper(GT, GEN)
    assert len(calls) == 1
    assert m1.meta["cache"] == "miss" and m2.meta["cache"] == "hit"
    assert m1.meta["model"] == "test-model" and m1.meta["temperature"] == 0
    assert [p.gen for p in m2.pairs] == [1, 2, 3, 5, 4, 6, 7, 8]
    # offline mapper reads the same cache, and fails without it
    assert llm.llm_mapper(cache_dir=env / "cache", offline=True)(GT, GEN).pairs == m2.pairs
    with pytest.raises(MappingError):
        llm.llm_mapper(cache_dir=env / "empty", offline=True)(GT, GEN)


def test_llm_mapper_retries_once_with_error(env, monkeypatch):
    answers = ['{"pairs": [{"gt": 1, "gen": 99, "same_element": true, "same_intent": true}]}', json.dumps(GOOD)]
    seen = []

    def fake_chat(model, messages):
        seen.append(messages)
        return answers[len(seen) - 1]

    monkeypatch.setattr(llm, "_chat", fake_chat)
    m = llm.llm_mapper(cache_dir=env / "cache")(GT, GEN)
    assert m.meta["attempts"] == 2
    assert "GEN99 does not exist" in seen[1][-1]["content"]


def test_llm_mapper_gives_up_after_retry(env, monkeypatch):
    monkeypatch.setattr(llm, "_chat", lambda model, messages: "sorry")
    with pytest.raises(MappingError):
        llm.llm_mapper(cache_dir=env / "cache")(GT, GEN)
