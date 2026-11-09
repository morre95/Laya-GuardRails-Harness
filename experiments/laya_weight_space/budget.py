"""Persistent, fail-closed search accounting; failed/reserved calls are never refunded."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time

from experiments.laya_weight_space.protocol import SEARCH_BUDGET, read_sealed, seal, write_json
from lgh.ids import utc_now_iso
from lgh.train.data import DatasetError


class Budget:
    def __init__(self, path: Path):
        self.path = path

    @classmethod
    def create(cls, path: Path, *, protocol_sha256: str, parent_sha256: str,
               arm: str, purpose: str = 'search') -> Budget:
        if (arm not in SEARCH_BUDGET['per_arm'] or purpose not in ('search', 'tool_smoke')
                or any(not re.fullmatch('[0-9a-f]{64}', s) for s in (protocol_sha256, parent_sha256))):
            raise DatasetError('invalid budget identity')
        write_json(path, seal({'version': 1, 'protocol_sha256': protocol_sha256,
            'parent_sha256': parent_sha256, 'arm': arm, 'purpose': purpose,
            'limits': SEARCH_BUDGET, 'calls': [], 'proposals': []}))
        return cls(path)

    @contextmanager
    def _locked(self):
        # Separate lock inode remains stable across atomic ledger replacements.
        with self.path.with_suffix(self.path.suffix + '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = read_sealed(self.path)
            if state.get('version') != 1 or state.get('limits') != SEARCH_BUDGET:
                raise DatasetError('budget format/limits changed')
            yield state

    def _save(self, state: dict) -> None:
        state = seal({k: v for k, v in state.items() if k != 'sha256'})
        descriptor, name = tempfile.mkstemp(dir=self.path.parent, prefix='.budget-')
        try:
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(state, stream, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def snapshot(self) -> dict:
        with self._locked() as state:
            return state

    def proposal(self, proposal_sha256: str) -> None:
        with self._locked() as state:
            if len(state['proposals']) >= SEARCH_BUDGET['max_patch_proposals']:
                raise DatasetError('patch proposal budget exhausted')
            state['proposals'].append({'id': proposal_sha256, 'time': utc_now_iso()})
            self._save(state)

    @contextmanager
    def evaluation(self, case_ids: list[str], kind: str):
        if (kind not in ('probe', 'prediction') or not case_ids
                or len(case_ids) > SEARCH_BUDGET['max_cases_per_call']
                or any(not isinstance(i, str) or not i for i in case_ids)
                or len(set(case_ids)) != len(case_ids)):
            raise DatasetError('invalid evaluation batch')
        with self._locked() as state:
            calls = state['calls']
            if any(c['status'] == 'running' for c in calls):
                raise DatasetError('unfinished budget reservation; inspect interrupted run before continuing')
            if (len(calls) >= SEARCH_BUDGET['max_evaluation_calls']
                    or sum(len(c['case_ids']) for c in calls) + len(case_ids)
                    > SEARCH_BUDGET['max_case_exposures']):
                raise DatasetError('evaluation budget exhausted')
            entry = {'id': len(calls) + 1, 'kind': kind, 'case_ids': list(case_ids),
                     'started_at': utc_now_iso(), 'status': 'running', 'forwards': []}
            calls.append(entry)
            self._save(state)  # Reserve BEFORE inference, including failed and interrupted calls.
            start = time.monotonic()
            try:
                yield _Call(self, state, entry)
            except BaseException as exc:
                entry.update(status='failed', error_type=type(exc).__name__)
                raise
            else:
                entry['status'] = 'complete'
            finally:
                entry['elapsed_seconds'] = time.monotonic() - start
                self._save(state)


class _Call:
    def __init__(self, budget: Budget, state: dict, entry: dict):
        self.budget, self.state, self.entry = budget, state, entry

    def forward(self, batch_size: int, device: str) -> None:
        if self.entry['status'] != 'running' or len(self.entry['forwards']) >= len(self.entry['case_ids']):
            raise DatasetError('forward outside reserved case budget/reservation')
        if batch_size != SEARCH_BUDGET['questions_per_case']:
            raise DatasetError('each forward must contain exactly seven questions')
        self.entry['forwards'].append({'question_sequences': batch_size, 'device': device,
            'case_id': self.entry['case_ids'][len(self.entry['forwards'])]})
        self.budget._save(self.state)
