from __future__ import annotations

import json

import pytest

from lgh.cli import main
from lgh.config.merge import merge_configs
from lgh.config.models import GuardrailConfig
from lgh.teacher import TeacherError, normalize_proposal, resolve_teacher
from lgh.teacher.openrouter import OpenRouterTeacher, parse_json_content


def _cfg(model: str = "x-ai/grok-4") -> GuardrailConfig:
    cfg = GuardrailConfig()
    cfg.teacher.model = model
    return cfg


def test_repo_cannot_override_teacher() -> None:
    user = GuardrailConfig()
    user.teacher.model = "x-ai/grok-4"
    repo = GuardrailConfig()
    repo.teacher.model = "openai/gpt-5"
    repo.teacher.base_url = "https://evil.example/v1"
    merged = merge_configs(user, repo)
    assert merged.teacher.model == "x-ai/grok-4"
    assert merged.teacher.base_url == user.teacher.base_url


def test_resolve_teacher_unknown_kind() -> None:
    with pytest.raises(TeacherError, match="unknown teacher"):
        resolve_teacher(True, "claude", config=_cfg(), api_key="sk-test")


def test_resolve_teacher_requires_propose() -> None:
    with pytest.raises(TeacherError, match="--teacher requires --propose"):
        resolve_teacher(False, "llm", config=_cfg(), api_key="sk-test")


def test_resolve_teacher_missing_key() -> None:
    with pytest.raises(TeacherError, match="OPENROUTER_API_KEY"):
        resolve_teacher(True, "llm", config=_cfg(), api_key="")


def test_resolve_teacher_missing_model() -> None:
    with pytest.raises(TeacherError, match="teacher.model"):
        resolve_teacher(True, "llm", config=GuardrailConfig(), api_key="sk-test")


def test_cli_unknown_teacher(capsys) -> None:
    assert main(["review", "--propose", "--teacher", "claude"]) == 1
    assert "unknown teacher" in capsys.readouterr().err


def test_cli_teacher_requires_propose(capsys) -> None:
    assert main(["review", "--teacher", "llm"]) == 1
    assert "--teacher requires --propose" in capsys.readouterr().err


def test_parse_json_content_strips_fences() -> None:
    data = parse_json_content("```json\n{\"handling\": \"allow\"}\n```")
    assert data["handling"] == "allow"


def test_normalize_proposal_rejects_bad_handling() -> None:
    with pytest.raises(TeacherError, match="invalid label"):
        normalize_proposal(
            {
                "handling": "maybe",
                "task_alignment": "aligned",
                "reversibility": "trivial",
                "destructive_risk": 0.1,
                "sensitive_resource": 0.0,
                "external_impact": 0.0,
                "verification_needed": 0.2,
            }
        )


def test_openrouter_propose_valid_json() -> None:
    captured: dict = {}

    def fake_post(url, headers, body, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "task_alignment": "outside_scope",
                                "destructive_risk": 0.4,
                                "sensitive_resource": 0.1,
                                "external_impact": 0.9,
                                "reversibility": "difficult",
                                "verification_needed": 0.8,
                                "handling": "replan",
                                "reason": "force push to origin",
                            }
                        )
                    }
                }
            ]
        }

    teacher = OpenRouterTeacher(
        model="x-ai/grok-4",
        api_key="sk-test",
        post=fake_post,
    )
    proposal = teacher.propose({"goal": "ship", "action": {"command": "git push --force"}})
    assert proposal["handling"] == "replan"
    assert proposal["model"] == "x-ai/grok-4"
    assert proposal["reason"] == "force push to origin"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "x-ai/grok-4"


def test_openrouter_propose_rejects_invalid_label() -> None:
    def fake_post(url, headers, body, timeout):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "task_alignment": "aligned",
                                "destructive_risk": 0.1,
                                "sensitive_resource": 0.0,
                                "external_impact": 0.0,
                                "reversibility": "trivial",
                                "verification_needed": 0.2,
                                "handling": "yolo",
                                "reason": "nah",
                            }
                        )
                    }
                }
            ]
        }

    teacher = OpenRouterTeacher(model="openai/gpt-5", api_key="sk-test", post=fake_post)
    with pytest.raises(TeacherError, match="invalid label"):
        teacher.propose({"goal": "edit a file"})
