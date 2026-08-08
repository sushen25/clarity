from __future__ import annotations

import logging

import boto3

from app.ai import BedrockClinicalAI, LocalHeuristicAI, get_ai
from app.clinical import DOMAINS, DOMAIN_DEFINITIONS, ExtractionResult, REPORT_SECTIONS


class _FakeBedrockClient:
    def __init__(self, output_text: str = '{"status":"sensitive-model-output"}'):
        self.output_text = output_text
        self.last_request = None

    def converse(self, **kwargs):
        self.last_request = kwargs
        return {
            "output": {"message": {"content": [{"text": self.output_text}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 12, "outputTokens": 4},
            "ResponseMetadata": {"RequestId": "test-request-id"},
        }


def test_extraction_schema_exposes_every_allowed_domain():
    schema = ExtractionResult.model_json_schema()
    domain_schema = schema["$defs"]["ExtractedEvidence"]["properties"]["domain"]

    assert domain_schema["enum"] == list(DOMAINS)
    assert domain_schema["enum"][-1] == "other"


def test_extraction_prompt_defines_domain_catalog(app, monkeypatch):
    client = _FakeBedrockClient('{"evidence":[]}')
    monkeypatch.setattr(boto3, "client", lambda *_args, **_kwargs: client)
    app.config.update(BEDROCK_ENABLED=True, AWS_REGION="ap-southeast-2", BEDROCK_MODEL_ID="test-model")

    with app.app_context():
        BedrockClinicalAI().extract("Synthetic source text", {"source_type": "transcript"}, "adult")

    system_prompt = client.last_request["system"][0]["text"]
    assert client.last_request["inferenceConfig"]["maxTokens"] == 8000
    for domain, description in DOMAIN_DEFINITIONS.items():
        assert domain in system_prompt
        assert description in system_prompt
    assert "Use 'other' only when no listed clinical domain applies" in system_prompt


def test_provider_log_identifies_local_fallback(app, caplog):
    with app.app_context(), caplog.at_level(logging.INFO, logger=app.logger.name):
        provider = get_ai()

    assert isinstance(provider, LocalHeuristicAI)
    assert "clinical_ai.provider_selected provider=local-heuristic bedrock_enabled=false" in caplog.text


def test_bedrock_logs_request_metadata_but_not_content(app, caplog, monkeypatch):
    client = _FakeBedrockClient()
    captured_client_options = {}

    def fake_client(*_args, **kwargs):
        captured_client_options.update(kwargs)
        return client

    monkeypatch.setattr(boto3, "client", fake_client)
    app.config.update(BEDROCK_ENABLED=True, AWS_REGION="ap-southeast-2", BEDROCK_MODEL_ID="test-model")

    with app.app_context(), caplog.at_level(logging.INFO, logger=app.logger.name):
        provider = get_ai()
        result = provider._json("test-operation", "sensitive-system-prompt", "sensitive-patient-input")

    assert isinstance(provider, BedrockClinicalAI)
    assert result == {"status": "sensitive-model-output"}
    sdk_config = captured_client_options["config"]
    assert sdk_config.connect_timeout == 10
    assert sdk_config.read_timeout == 600
    assert sdk_config.retries == {"mode": "standard", "total_max_attempts": 2}
    assert client.last_request["inferenceConfig"]["maxTokens"] == 7000
    assert "clinical_ai.provider_selected provider=bedrock region=ap-southeast-2 model_id=test-model" in caplog.text
    assert "bedrock.request_started operation=test-operation" in caplog.text
    assert "read_timeout_seconds=600 max_tokens=7000 sdk_max_attempts=2" in caplog.text
    assert "bedrock.response_received operation=test-operation" in caplog.text
    assert "request_id=test-request-id" in caplog.text
    assert "sensitive-system-prompt" not in caplog.text
    assert "sensitive-patient-input" not in caplog.text
    assert "sensitive-model-output" not in caplog.text


def test_draft_blocks_paragraphs_without_valid_evidence_links(app, monkeypatch):
    model_output = """{
      "sections": [
        {"key":"background","heading":"Background","paragraphs":[
          {"text":"Supported paragraph.","evidence_ids":["evidence-1"]},
          {"text":"Unsupported paragraph.","evidence_ids":[]},
          {"text":"Unknown link paragraph.","evidence_ids":["invented-id"]}
        ]},
        {"key":"summary","heading":"Summary","paragraphs":[
          {"text":"Clinician conclusion.","evidence_ids":[]}
        ]}
      ]
    }"""
    client = _FakeBedrockClient(model_output)
    monkeypatch.setattr(boto3, "client", lambda *_args, **_kwargs: client)
    app.config.update(BEDROCK_ENABLED=True, AWS_REGION="ap-southeast-2", BEDROCK_MODEL_ID="test-model")

    with app.app_context():
        result = BedrockClinicalAI().draft(
            {"cohort": "adult", "final_diagnostic_conclusion": "Clinician conclusion."},
            [{"id": "evidence-1", "domain": "developmental", "supporting_text": "Synthetic evidence."}],
            [],
            [],
        )

    system_prompt = client.last_request["system"][0]["text"]
    assert "interweaves the evidence throughout" in system_prompt
    assert "attribute information naturally to its reporter" in system_prompt
    assert "synthesise corroborating evidence from multiple reporters or settings" in system_prompt
    assert "preserve meaningful differences or contradictions" in system_prompt
    assert "must not contain evidence UUIDs, source filenames, source locations" in system_prompt
    assert "evidence_ids are output metadata only" in system_prompt
    assert "If no verified evidence supports a section" in system_prompt
    assert "For the diagnostic_criteria section, return paragraphs: []" in system_prompt
    sections = {section.key: section for section in result.sections}
    assert [section.key for section in result.sections] == [key for key, _heading in REPORT_SECTIONS]
    assert [p.text for p in sections["background"].paragraphs] == ["Supported paragraph."]
    assert sections["diagnostic_criteria"].paragraphs == []
    assert [p.text for p in sections["summary"].paragraphs] == ["Clinician conclusion."]
    assert result.validation_warnings == [
        "1 model paragraph(s) with invalid evidence links were blocked.",
        "1 unsupported model paragraph(s) were blocked.",
    ]
