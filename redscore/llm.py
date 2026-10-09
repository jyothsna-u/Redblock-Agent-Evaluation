"""Pinned LLM mapping call (OpenAI-compatible endpoint, temperature 0) with an on-disk cache.

Config comes from the environment (or a git-ignored .env in the working directory):
    REASONING_MODEL_API_KEY, REASONING_MODEL_NAME, REASONING_MODEL_API_BASE_URL
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .files import write_atomic
from .mapping import DEFAULT_PROMPT, Mapper, Mapping, MappingError, build_prompt, load_prompt, validate_mapping
from .parser import Script

DEFAULT_CACHE = Path("results") / "cache" / "mapping"


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader; existing environment variables win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise MappingError("no JSON object in LLM response")
    try:
        return json.loads(text[start:end + 1])
    except ValueError as e:
        raise MappingError(f"invalid JSON in LLM response: {e}")


def llm_mapper(prompt_name: str = DEFAULT_PROMPT, cache_dir: Path = DEFAULT_CACHE,
               model: Optional[str] = None, offline: bool = False, refresh: bool = False) -> Mapper:
    """Mapper backed by the pinned LLM. `offline=True` only reads the cache (for re-scoring).

    `refresh=True` asks the LLM again even when a cached mapping exists; the new answer becomes the cached
    one and the previous answer is kept in cache/mapping/replaced/ (evidence of how much the judge varies).
    """
    load_dotenv()
    template, prompt_version = load_prompt(prompt_name)
    model = model or os.environ.get("REASONING_MODEL_NAME")
    if not model:
        raise RuntimeError("REASONING_MODEL_NAME is not set (see .env.example)")
    cache_dir = Path(cache_dir)

    def mapper(gt: Script, gen: Script) -> Mapping:
        prompt = build_prompt(gt, gen, template)
        # Key on what the LLM actually sees, so blank lines, comments and the URL line reuse the cached mapping.
        key = hashlib.sha256("\x00".join([model, prompt_version, prompt]).encode()).hexdigest()
        meta = {"source": "llm", "model": model, "prompt_version": prompt_version, "cache_key": key,
                "temperature": 0}
        path = cache_dir / f"{key}.json"
        if path.exists() and refresh:
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            (cache_dir / "replaced").mkdir(parents=True, exist_ok=True)
            path.replace(cache_dir / "replaced" / f"{key}_{stamp}.json")
        if path.exists():
            try:
                cached = json.loads(path.read_text())
                return validate_mapping(gt, gen, cached["data"], dict(meta, cache="hit"))
            except (ValueError, KeyError, MappingError):
                # A damaged or invalid entry is set aside (kept for inspection) and the call is made again.
                path.replace(path.with_suffix(".corrupt"))
        if offline:
            raise MappingError(f"no cached mapping for this GT/GEN/model/prompt (key {key[:12]})")

        messages =[{"role": "user", "content": prompt}]
        last_err = None
        failed = []                       # kept in the cache so run history shows rejected answers
        for attempt in range(2):          # one retry, with the error fed back
            raw = _chat(model, messages)
            try:
                data = _extract_json(raw)
                mapping = validate_mapping(gt, gen, data, dict(meta, cache="refresh" if refresh else "miss",
                                                               attempts=attempt + 1))
            except MappingError as e:
                last_err = e
                failed.append({"raw": raw, "error": str(e)})
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": f"That answer is invalid: {e}. "
                                                         "Reply again with only the corrected JSON object."}]
                continue
            write_atomic(path, json.dumps({"meta": meta, "prompt": prompt, "raw": raw, "data": data,
                                           "failed_attempts": failed}, indent=2))
            return mapping
        rejected = cache_dir / "rejected" / f"{key}.json"
        write_atomic(rejected, json.dumps({"meta": meta, "prompt": prompt, "failed_attempts": failed}, indent=2))
        raise MappingError(f"LLM mapping failed after retry: {last_err} (rejected replies: {rejected})")

    mapper.model = model                    # type: ignore[attr-defined]
    mapper.prompt_version = prompt_version  # type: ignore[attr-defined]
    mapper.judge = f"llm:{model}@{prompt_version}"   # type: ignore[attr-defined]
    return mapper


def _chat(model: str, messages) -> str:
    from openai import APIError, OpenAI

    base_url = os.environ.get("REASONING_MODEL_API_BASE_URL")
    api_key = os.environ.get("REASONING_MODEL_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("REASONING_MODEL_API_BASE_URL / REASONING_MODEL_API_KEY are not set (see .env.example)")
    # The client retries connection errors, timeouts, 429 and 5xx with exponential backoff (honouring Retry-After).
    client = OpenAI(base_url=base_url, api_key=api_key,
                    timeout=float(os.environ.get("REASONING_MODEL_TIMEOUT", "300")),
                    max_retries=int(os.environ.get("REASONING_MODEL_MAX_RETRIES", "4")))
    try:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0)
    except APIError as e:   # still failing after the client's retries, or not retryable (e.g. auth)
        raise RuntimeError(f"mapping LLM call to {base_url} failed: {e}") from e
    return resp.choices[0].message.content or ""
