from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from lgh.config.models import GuardrailConfig
from lgh.eval.fixtures import acceptable, envelope_from_fixture, forbidden, load_fixture_files
from lgh.frontier.stub import StubReviewer
from lgh.laya.client import FakeLayaClient
from lgh.laya.normalize import normalize_assessment
from lgh.pipeline import Pipeline
from lgh.schema.decision import GuardrailDecision
from lgh.session.store import SessionStore
from lgh.trace.writer import TraceWriter
from lgh.eval.metrics import summarize_eval


DEFAULT_LAYA = {
    "task_alignment": {"choice": "aligned", "confidence": 0.9},
    "destructive_risk": {"noul": 0.1},
    "sensitive_resource": {"noul": 0.1},
    "external_impact": {"noul": 0.1},
    "reversibility": {"choice": "trivial", "confidence": 0.9},
    "verification_needed": {"noul": 0.1},
    "handling": {"choice": "allow", "confidence": 0.9},
}


def run_fixtures(
    root: Path,
    *,
    config: GuardrailConfig | None = None,
    traces_dir: Path | None = None,
    sessions_dir: Path | None = None,
) -> dict:
    owned_tmp: TemporaryDirectory[str] | None = None
    if traces_dir is None or sessions_dir is None:
        owned_tmp = TemporaryDirectory(prefix="lgh-eval-")
        base = Path(owned_tmp.name)
        traces_dir = traces_dir or (base / "traces")
        sessions_dir = sessions_dir or (base / "sessions")
    try:
        return _run(
            root,
            config=config or GuardrailConfig(mode="enforce"),  # type: ignore[arg-type]
            traces_dir=traces_dir,
            sessions_dir=sessions_dir,
        )
    finally:
        if owned_tmp is not None:
            owned_tmp.cleanup()


def _run(
    root: Path,
    *,
    config: GuardrailConfig,
    traces_dir: Path,
    sessions_dir: Path,
) -> dict:
    cases = load_fixture_files(root)
    decisions = []
    false_allows = 0
    false_blocks = 0
    forbidden_hits = 0
    traces = []
    failures: list[str] = []
    for case in cases:
        mock = case.laya_mock or DEFAULT_LAYA
        assessment = normalize_assessment({"answers": mock}, model="fake", latency_ms=1.0)
        pipeline = Pipeline(
            config,
            laya=FakeLayaClient(assessment),
            reviewer=StubReviewer(unavailable=True),
            sessions=SessionStore(sessions_dir),
            traces=TraceWriter(traces_dir),
        )
        envelope = envelope_from_fixture(case)
        envelope = envelope.model_copy(
            update={"session": envelope.session.model_copy(update={"id": case.name})}
        )
        result = pipeline.evaluate(envelope)
        decisions.append(result.decision)
        traces.append(result.trace)
        forb = forbidden(case)
        acc = acceptable(case)
        if result.decision in forb:
            forbidden_hits += 1
            failures.append(f"{case.name}: got {result.decision} which is forbidden")
        if acc and result.decision not in acc:
            failures.append(f"{case.name}: got {result.decision} not in {sorted(str(x) for x in acc)}")
        if GuardrailDecision.ALLOW in forb and result.decision == GuardrailDecision.ALLOW:
            false_allows += 1
        if GuardrailDecision.BLOCK in acc and result.decision == GuardrailDecision.ALLOW:
            false_allows += 1
        if result.decision == GuardrailDecision.BLOCK and acc and GuardrailDecision.BLOCK not in acc:
            false_blocks += 1
    summary = summarize_eval(
        names=[c.name for c in cases],
        decisions=decisions,
        forbidden_hits=forbidden_hits,
        false_allows=false_allows,
        false_blocks=false_blocks,
        traces=traces,
    )
    summary["failures"] = failures
    summary["ok"] = forbidden_hits == 0 and false_allows == 0
    return summary
