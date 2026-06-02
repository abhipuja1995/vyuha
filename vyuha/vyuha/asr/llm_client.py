"""
Shared LLM API client for vyuha.asr scorers.

Ported from sarvamai/llm_wer and sarvamai/llm_intent_entity (llm_api.py).
Supports OpenAI-compatible endpoints and Google Vertex AI (Gemini) via
the OpenAI-compatible Vertex endpoint.
"""
from __future__ import annotations

import json
import jsonlines
import queue
import re
import threading
import time
import traceback
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Type

from joblib import Parallel, delayed
from pydantic import BaseModel
from pydantic_core import from_json
from tqdm import tqdm


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _parse_json(content: str) -> dict | None:
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    for pattern in [
        r"```(?:json)?\s*(\{.*?\})\s*```",
        r"(?:json|JSON|output|Output):\s*(\{.*?\})",
        r"\{.*\}",
    ]:
        m = re.search(pattern, cleaned, re.DOTALL)
        if m:
            raw = m.group(1) if m.groups() else m.group(0)
            try:
                return from_json(raw, allow_partial=True)  # type: ignore
            except Exception:
                pass
    return None


def _write_buffer(
    buffer: list,
    path: Path,
    lock: threading.Lock | None,
    data: dict | None = None,
    flush: bool = False,
    chunk: int = 1000,
) -> None:
    if data:
        buffer.append(data)
    if (flush and buffer) or len(buffer) >= chunk:
        wb = list(buffer)
        buffer.clear()
        ctx = lock or _null_context()
        with ctx:
            with jsonlines.open(path, mode="a") as w:
                w.write_all(wb)


class _null_context:
    def __enter__(self): return self
    def __exit__(self, *_): pass


def _validate(content: Any, key: Any, schema: Type[BaseModel]) -> dict:
    try:
        parsed = _parse_json(content) if isinstance(content, str) else content
        if parsed is None:
            raise ValueError("Could not parse JSON")
        validated = schema.model_validate(parsed)
        return {"key": key, "response": validated.model_dump(), "status": "success"}
    except Exception as exc:
        return {
            "key": key, "response": content, "status": "parse_error",
            "error": str(exc), "traceback": traceback.format_exc(),
        }


# ── ChatCompletionsAPI ────────────────────────────────────────────────────────

class ChatCompletionsAPI:
    """
    Thread-safe, retrying LLM API client.
    Supports OpenAI-compatible endpoints and Vertex AI Gemini.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str = "",
        base_url: str = "",
        num_workers: int = 500,
        max_retries: int = 2,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        gemini: bool = False,
        creds_path: Optional[str] = None,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        report_usage: bool = False,
        delay: float = 0.0,
    ) -> None:
        from openai import OpenAI

        self.model_name = model_name
        self.timeout = timeout
        self.delay = delay
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.num_workers = num_workers
        self.max_retries = max_retries
        self.report_usage = report_usage
        self.request_queue: queue.Queue = queue.Queue()
        self.semaphore = threading.Semaphore(num_workers)

        if not gemini:
            self.client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout)
        else:
            from google.auth.transport.requests import Request
            from google.oauth2.service_account import Credentials
            if not creds_path or not location:
                raise ValueError("`creds_path` and `location` required for Gemini")
            creds = Credentials.from_service_account_file(
                creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            pid = project_id or creds.project_id
            if not pid:
                raise ValueError("project_id required for Gemini")
            creds.refresh(Request())
            self.client = OpenAI(
                api_key=creds.token,
                base_url=(
                    f"https://{location}-aiplatform.googleapis.com/v1"
                    f"/projects/{pid}/locations/{location}/endpoints/openapi"
                ),
                timeout=timeout,
            )

        self._check_parse_endpoint()

    def _check_parse_endpoint(self) -> None:
        class _M(BaseModel):
            greeting: str
            response: str
            mood: str
        try:
            self.client.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Always respond in JSON."},
                    {"role": "user", "content": "Hello"},
                ],
                response_format=_M,
            )
            self.parse_endpoint_supported = True
        except Exception:
            self.parse_endpoint_supported = False

    def generate_single_response(
        self,
        prompt: str,
        key: Any = None,
        schema: Optional[Type[BaseModel]] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
    ) -> dict:
        if key is None:
            key = {"uuid": str(uuid.uuid4())}
        with self.semaphore:
            try:
                messages = []
                sys_content = system_prompt or self.system_prompt
                if sys_content:
                    messages.append({"role": "system", "content": sys_content})
                messages.append({"role": "user", "content": prompt})

                params: dict[str, Any] = {"model": self.model_name, "messages": messages}
                if temperature is not None or self.temperature:
                    params["temperature"] = temperature if temperature is not None else self.temperature
                if self.max_tokens:
                    params["max_tokens"] = self.max_tokens
                if self.timeout:
                    params["timeout"] = self.timeout

                if schema is not None:
                    if self.parse_endpoint_supported:
                        params["response_format"] = schema
                        resp = self.client.beta.chat.completions.parse(**params)
                        parsed = resp.choices[0].message.parsed
                        result: dict = {"key": key, "response": parsed.model_dump(), "status": "success"}  # type: ignore
                    else:
                        params.setdefault("extra_body", {})["guided_json"] = schema.model_json_schema()
                        resp = self.client.chat.completions.create(**params)
                        result = _validate(resp.choices[0].message.content, key, schema)
                else:
                    resp = self.client.chat.completions.create(**params)
                    result = {"key": key, "response": resp.choices[0].message.content, "status": "success_no_schema"}

                if self.report_usage and hasattr(resp, "usage") and resp.usage:
                    result["input_tokens"] = resp.usage.prompt_tokens
                    result["output_tokens"] = resp.usage.completion_tokens
                return result

            except Exception as exc:
                return {
                    "key": key, "response": None, "status": "api_error",
                    "error": str(exc), "traceback": traceback.format_exc(),
                }

    def append_to_request_queue(
        self,
        prompt: str,
        key: Any = None,
        schema: Optional[Type[BaseModel]] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.request_queue.put(
            {"prompt": prompt, "key": key, "schema": schema,
             "temperature": temperature, "system_prompt": system_prompt}
        )

    def generate_responses_from_queue(
        self,
        output_file_path: Optional[Path] = None,
        retry_temp: float = 0.5,
    ) -> tuple[list, list]:
        items = []
        while not self.request_queue.empty():
            items.append(self.request_queue.get())

        successful, failed = [], []
        lock = threading.Lock() if output_file_path and self.num_workers > 1 else None
        buffer: list = []

        try:
            for attempt in range(self.max_retries + 1):
                if not items:
                    break
                if attempt > 0:
                    backoff = (self.timeout or 10) * (2 ** (attempt - 1))
                    time.sleep(backoff)

                results = []
                with tqdm(total=len(items), desc=f"Attempt {attempt+1}") as pbar:
                    def _run(req: dict) -> tuple:
                        result = self.generate_single_response(**req)
                        pbar.update(1)
                        return result, req

                    if self.num_workers > 1:
                        with Parallel(n_jobs=min(self.num_workers, len(items)), prefer="threads") as p:
                            results = p(delayed(_run)(r) for r in items)
                    else:
                        results = [_run(r) for r in items]

                retry_items = []
                counts: Counter = Counter()
                is_last = attempt == self.max_retries
                for result, req in results:  # type: ignore
                    status = result["status"]
                    counts[status] += 1
                    if status in ("api_error", "parse_error") and not is_last:
                        if status == "parse_error":
                            req["temperature"] = retry_temp
                        retry_items.append(req)
                    else:
                        if status in ("success", "success_no_schema"):
                            successful.append(result)
                        else:
                            failed.append(result)
                        if output_file_path:
                            _write_buffer(buffer, output_file_path, lock, data=result)
                items = retry_items
        finally:
            if output_file_path:
                _write_buffer(buffer, output_file_path, lock, flush=True)

        return successful, failed
