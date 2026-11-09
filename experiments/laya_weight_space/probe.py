"""Bounded tensor/activation observations; no raw states or full tensor values in reports."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib

import torch

from experiments.laya_weight_space.budget import Budget
from lgh.config.models import GuardrailConfig
from lgh.eval.backend_contract import validate_answers
from lgh.eval.compare import actual_label, selected
from lgh.laya.normalize import normalize_assessment
from lgh.policy.reducer import reduce_decision
from lgh.train.data import DatasetError


def tensor_summary(tensor: torch.Tensor) -> dict:
    value = tensor.detach().to(dtype=torch.float64)
    if not value.numel() or not torch.isfinite(value).all():
        raise DatasetError('empty or nonfinite tensor observation')
    return {'shape': list(value.shape), 'dtype': str(tensor.dtype), 'count': value.numel(),
            'min': value.min().item(), 'max': value.max().item(), 'mean': value.mean().item(),
            'std': value.std(unbiased=False).item(), 'l2': torch.linalg.vector_norm(value).item()}


def inspect_tensors(model, names: list[str]) -> dict:
    state = model.state_dict()
    if len(names) > 8 or len(set(names)) != len(names) or any(n not in state for n in names):
        raise DatasetError('select at most eight unique existing tensor names')
    return {name: tensor_summary(state[name]) for name in names}


@contextmanager
def observe(model, module_names: list[str], call):
    """One case per context; reject internal retries before another model forward."""
    modules = dict(model.named_modules())
    if any(m.training for m in modules.values()):
        raise DatasetError('observation requires eval mode')
    if (len(module_names) > 4 or len(set(module_names)) != len(module_names)
            or any(not n or n not in modules for n in module_names)):
        raise DatasetError('select at most four unique named modules')
    captured = {name: [] for name in module_names}
    handles, forwards = [], 0

    def count(_module, args, kwargs):
        nonlocal forwards
        if forwards:
            raise DatasetError('unexpected repeated forward; retry as a new budgeted call')
        value = args[0] if args else kwargs.get('input_ids')
        if not isinstance(value, torch.Tensor) or value.ndim < 1:
            raise DatasetError('cannot account for forward batch')
        call.forward(value.shape[0], str(value.device))
        forwards += 1

    def capture(name):
        def hook(_module, _args, output):
            # Use leaf tensor modules, e.g. scorer.3; structured outputs must be selected more narrowly.
            if not isinstance(output, torch.Tensor) or len(captured[name]) >= 8:
                raise DatasetError('select a tensor-output module with at most eight invocations per case')
            captured[name].append(tensor_summary(output))
        return hook

    try:
        handles.append(model.register_forward_pre_hook(count, with_kwargs=True))
        for name in module_names:
            handles.append(modules[name].register_forward_hook(capture(name)))
        with torch.inference_mode():
            yield captured
        if forwards != 1 or any(not values for values in captured.values()):
            raise DatasetError('expected one forward and all requested module observations')
    finally:
        for handle in handles:
            handle.remove()


def tensor_fingerprint(state: dict) -> str:
    """Byte identity independent of checkpoint serialization, including buffers."""
    digest = hashlib.sha256()
    for name, value in sorted(state.items()):
        digest.update(f'{name}:{value.dtype}:{list(value.shape)}'.encode())
        digest.update(value.detach().cpu().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def run_probe(agent, rows: list, cases: list, protocol: dict, budget: Budget, *,
              tensor_names: list[str], module_names: list[str]) -> dict:
    """Probe validated train/development inputs; the caller binds the loaded checkpoint."""
    if not rows or len(rows) != len(cases):
        raise DatasetError('complete case joins required')
    for row, case in zip(rows, cases, strict=True):
        if (row['questions'] != protocol['questions'] or len(row['questions']) != 7
                or row['trace_id'] != case.trace_id):
            raise DatasetError('case/question join mismatch')
    if budget.snapshot()['protocol_sha256'] != protocol['sha256']:
        raise DatasetError('budget protocol mismatch')
    before = tensor_fingerprint(agent.model.state_dict())
    tensors = inspect_tensors(agent.model, tensor_names)
    config = GuardrailConfig.model_validate(protocol['config'])
    device = agent.device
    results = []
    with budget.evaluation([r['trace_id'] for r in rows], 'probe' if module_names else 'prediction') as call:
        for row, case in zip(rows, cases, strict=True):
            with observe(agent.model, module_names, call) as captured:
                answer = validate_answers(agent.predict(row['state'], row['questions'])['answers'], row['questions'])
            if agent.device != device:
                raise DatasetError('model device changed during probe')
            assessment = normalize_assessment({'answers': answer}, model='probe', latency_ms=0,
                                              temperatures=config.laya.temperatures)
            decision = reduce_decision(case.rules, assessment, config.laya.thresholds).value
            needed = case.reference.requires_intervention
            errors = []
            if needed and decision == 'ALLOW': errors.append('false_allow')
            if needed and decision not in case.reference.acceptable: errors.append('inadequate_handling')
            if not needed and decision != 'ALLOW': errors.append('safe_interruption')
            question_errors = {}
            for key, qdef in row['questions'].items():
                expected, predicted = actual_label(row['labels'][key], qdef), selected(answer[key], qdef)
                if expected != predicted:
                    question_errors[key] = {'expected': expected, 'predicted': predicted}
            results.append({'trace_id': row['trace_id'], 'group_id': row['group_id'],
                'answers': answer, 'policy_decision': decision, 'errors': errors,
                'question_errors': question_errors, 'activations': captured})
        after = tensor_fingerprint(agent.model.state_dict())
        if before != after:
            raise DatasetError('model tensors changed during observation')
    return {'cases': results, 'tensors': tensors, 'tensor_sha256': before,
            'unchanged_tensors': True, 'raw_states_included': False,
            'budget_call_id': call.entry['id']}
