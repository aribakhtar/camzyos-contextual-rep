import importlib.util

import pytest


@pytest.mark.skipif(importlib.util.find_spec("ragas") is None, reason="Install the optional eval extra")
def test_ragas_judge_initializes_without_network():
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness
    judge = llm_factory("gpt-4.1-mini", client=AsyncOpenAI(api_key="test-placeholder"))
    assert Faithfulness(llm=judge) is not None
