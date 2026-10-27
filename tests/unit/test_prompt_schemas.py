"""Every LLM output schema must be expressible in Gemini's response schema format.

The first real run failed because Gemini rejects integer enums (Literal[1, 2, 3]).
"""
import pytest
from google.genai import types

from backend.pipeline import prompts

SCHEMAS = [prompts.ResearchPlan, prompts.ClaimDraft, prompts.Judgements, prompts.ReportDraft]


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda s: s.__name__)
def test_schema_converts_to_gemini_format(schema):
    from google.genai import _transformers

    config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema)
    converted = _transformers.t_schema(None, config.response_schema)

    assert converted is not None
