from lgh.eval.calibrate import fit_temperature
from lgh.eval.export_dataset import export_dataset
from lgh.laya.normalize import apply_temperature, normalize_assessment
from lgh.laya.questions import QUESTION_KEYS, load_questions


def test_seven_questions() -> None:
    questions = load_questions()
    assert list(questions) == list(QUESTION_KEYS)
    assert "block" not in questions["handling"]["criteria"]


def test_normalize_questions() -> None:
    a = normalize_assessment(
        {
            "answers": {
                "task_alignment": {"choice": "aligned", "confidence": 0.9},
                "destructive_risk": {"noul": 0.2},
                "sensitive_resource": {"noul": 0.1},
                "external_impact": {"noul": 0.1},
                "reversibility": {"choice": "trivial", "confidence": 0.8},
                "verification_needed": {"noul": 0.3},
                "handling": {"choice": "allow", "confidence": 0.9},
            }
        },
        model="m",
        latency_ms=12,
    )
    assert a.handling.value == "allow"
    assert a.latency_ms == 12


def test_choice_confidence_is_top_probability_not_entropy() -> None:
    """Laya reports entropy-based confidence on choice; we use P(top label)."""
    answers = {
        "task_alignment": {
            "choice": "unclear",
            "confidence": 0.005,
            "probabilities": {"aligned": 0.24, "supporting": 0.25, "unclear": 0.26, "outside_scope": 0.25},
        },
        "destructive_risk": {"noul": 0.3},
        "sensitive_resource": {"noul": 0.4},
        "external_impact": {"noul": 0.5},
        "reversibility": {"choice": "trivial", "confidence": 0.9, "probabilities": {"trivial": 0.97, "recoverable": 0.01, "difficult": 0.01, "irreversible": 0.01}},
        "verification_needed": {"noul": 0.4},
        "handling": {"choice": "escalate", "confidence": 0.0171},
    }
    a = normalize_assessment({"answers": answers}, model="m", latency_ms=1)
    assert a.task_alignment.confidence == 0.26
    assert a.reversibility.confidence == 0.97
    # no probabilities -> fall back to Laya's own confidence field
    assert a.handling.confidence == 0.0171


def test_temperature_monotonic() -> None:
    assert apply_temperature(0.9, 2.0) < 0.9


def test_export_skips_laya_source(tmp_path) -> None:
    rows = export_dataset([], [{"trace_id": "x", "source": "laya", "handling": "allow"}])
    assert rows == []
    t = fit_temperature([0.9, 0.1], [1, 0])
    assert t > 0
