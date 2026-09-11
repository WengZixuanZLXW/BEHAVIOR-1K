"""CPU-only: a request must not be able to freeze the simulation indefinitely.

R freezes the env, so a hanging call stalls every robot, not one. This checks
the bound is actually wired into the SDK client on every backend.
"""
from __future__ import annotations
import os, sys

sys.path.insert(0, "/home/zixuanwe/Desktop/BEHAVIOR-1K")
from openai import APITimeoutError, APIError
from coop2.cognitive.agent.llm_client import LLMClient


def main() -> int:
    print("test: every backend passes the timeout down to the SDK client")
    for backend, kwargs in (
        ("azure", dict(azure_endpoint="https://example.invalid/", api_version="2024-12-01-preview")),
        ("foundry", dict(base_url="https://example.invalid/v1/")),
        ("deepseek", dict(base_url="https://example.invalid/v1/")),
    ):
        client = LLMClient(api_key="sk-test", backend=backend, **kwargs)
        assert client.timeout == 100.0, (backend, client.timeout)
        assert client.client.timeout == 100.0, (backend, client.client.timeout)
        # Per-attempt, so retries would multiply the bound rather than respect it.
        assert client.client.max_retries == 0, (backend, client.client.max_retries)
    print("  ok: 100 s per request, and the SDK does not retry behind it")

    print("\ntest: the bound is overridable, for a slower model or a probe")
    client = LLMClient(api_key="sk-test", backend="azure",
                       azure_endpoint="https://example.invalid/", timeout=5.0)
    assert client.timeout == 5.0 and client.client.timeout == 5.0
    print("  ok: timeout= is honoured")

    print("\ntest: a timeout reaches the caller, which is what the fallback needs")
    # APITimeoutError is an APIConnectionError, so it carries no status_code and
    # cannot be mistaken for the 429 branch that generate() retries.
    assert issubclass(APITimeoutError, APIError)
    err = APITimeoutError(request=None)
    assert getattr(err, "status_code", None) is None, "would be retried as a 429"
    print("  ok: a timeout raises rather than looping in the rate-limit retry")

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
