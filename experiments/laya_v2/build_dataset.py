"""Build auditable synthetic curriculum. Run with the project Python interpreter."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from lgh.laya.questions import load_questions
from lgh.schema.envelope import LayaState
from lgh.train.data import assert_disjoint, class_support, load_rows

from curriculum import TRAIN, VALIDATION, CALIBRATION

KEYS = ('task_alignment', 'destructive_risk', 'sensitive_resource', 'external_impact',
        'reversibility', 'verification_needed', 'handling')
NAMES = ('parser', 'catalog', 'scheduler', 'renderer', 'inventory', 'notifier')


def build(output: Path, revision: int = 2) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    train = TRAIN
    if revision == 3:
        from curriculum_v3 import TRAIN as train
    questions = load_questions()
    partitions = {}
    for split, scenarios, names in [('train', train, NAMES), ('validation', VALIDATION, ('search', 'export')),
                                     ('calibration', CALIBRATION, ('billing', 'indexer'))]:
        rows = []
        for family, goal, command, labels, rationale, environment, *options in scenarios:
            for index, name in enumerate(names):
                extra = options[0] if options else {}
                action = {'tool': 'edit' if command and command.startswith(('apply_patch:', 'write ')) else 'shell',
                          'operation': 'edit' if command and command.startswith(('apply_patch:', 'write ')) else 'execute'}
                if command is not None:
                    action['command'] = command.format(name=name)
                action.update({k: v.format(name=name) for k, v in extra.items() if k in ('tool', 'operation', 'target')})
                state = LayaState.model_validate({
                    'goal': goal.format(name=name), 'environment': environment,
                    'repo': {'branch': f'work/{name}', 'dirty': 'uncommitted' in goal or 'no backup' in goal, 'changed': []},
                    'action': action, 'recent': extra.get('recent', []),
                    **({'plan': extra['plan']} if 'plan' in extra else {}),
                }).model_dump(exclude_none=True)
                rows.append({'trace_id': f'curriculum-v{revision}-{family}-{index}', 'timestamp': '2026-10-24T00:00:00Z',
                             'group_id': family, 'state': state, 'questions': questions,
                             'labels': dict(zip(KEYS, labels, strict=True)), 'source': 'frontier',
                             'provenance': {'kind': 'synthetic', 'author': 'Codex', 'version': revision,
                                            'rationale': rationale, 'split': split}})
        path = output / f'{split}.jsonl'
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        partitions[split] = load_rows(path)
    assert_disjoint(partitions)
    manifest = {'kind': 'synthetic curriculum, not production evidence', 'partitions': {
        name: {'rows': len(rows), 'families': len({r['group_id'] for r in rows}),
               'sha256': hashlib.sha256((output / f'{name}.jsonl').read_bytes()).hexdigest(),
               'support': class_support(rows, questions)} for name, rows in partitions.items()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', type=int, choices=[2, 3], default=2)
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.revision), indent=2))
