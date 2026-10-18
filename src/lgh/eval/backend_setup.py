"""Read-only setup discovery; no model imports, downloads, or service changes."""
from __future__ import annotations

import csv
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess

from lgh.config.loader import load_config
from lgh.eval.backend_contract import Experiment, KEV_MODEL, rule_config_hash
from lgh.eval.compare import file_hash
from lgh.train.data import DatasetError


def gpu_snapshot() -> dict:
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,memory.free,driver_version', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=3, check=True)
        observed = []
        for name, total, free, driver in csv.reader(result.stdout.splitlines(), skipinitialspace=True):
            observed.append({'name': name, 'total_mib': int(total), 'free_mib': int(free), 'driver': driver})
        return {'observed': observed, 'true_peak_vram': None}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {'observed': None, 'true_peak_vram': None, 'note': 'nvidia-smi unavailable; GPU telemetry unverified'}


def snapshot_experiment(output: Path, *, cwd: Path) -> dict:
    if output.exists():
        raise DatasetError(f'{output} already exists; choose a new output directory')
    config = load_config(cwd=cwd, repo_root=cwd)
    model = Path(config.laya.model)
    model_config = model/'rl_agent_config.json'
    metadata = json.loads(model_config.read_text()).get('lgh_training', {}) if model_config.is_file() else {}
    weights = model/'model.safetensors'
    try:
        laya_version = 'laya==' + version('laya')
    except PackageNotFoundError:
        laya_version = None
    current = {
        'kind': 'laya', 'url': 'http://127.0.0.1:8766', 'model': config.laya.model,
        'revision': file_hash(weights) if weights.is_file() else None,
        'code_revision': laya_version, 'device': config.laya.device, 'dtype': None,
        'temperatures': config.laya.temperatures,
        'provenance': 'local_finetuned' if metadata else 'unknown',
        'training_dataset_sha256': metadata.get('dataset_sha256'),
        'runtime': {'precision_note': 'confirm actual daemon device/precision; CLI flags may override configured device'},
    }
    backends = {
        'laya_current': current,
        'kev': {'kind': 'kev', 'url': 'http://127.0.0.1:8009', 'model': KEV_MODEL,
                'device': 'cuda', 'dtype': 'bfloat16', 'provenance': 'released'},
        'laya_released': {'kind': 'laya', 'url': 'http://127.0.0.1:8767',
                          'model': 'convaiinnovations/laya-typed-decisions',
                          'device': config.laya.device, 'code_revision': laya_version, 'provenance': 'released'},
    }
    if config.laya.model == 'convaiinnovations/laya-typed-decisions':
        backends['laya_current']['provenance'] = 'released'
        backends.pop('laya_released')
    experiment = Experiment.model_validate({
        'version': 1, 'config': config.model_dump(mode='json'),
        'hardware': {'gpu': 'NVIDIA RTX 3090', 'vram_gb': 24, 'source': 'user supplied'},
        'backends': backends,
    })
    setup = {'status': 'needs_review', 'rule_config_sha256': rule_config_hash(config),
             'gpu_snapshot': gpu_snapshot(),
             'notes': ['Resolve released weight revisions and Kev serving-code commit before measurement.',
                       'Supply original training export and independent dataset/replay references.',
                       'Active daemon/configuration are not changed. Endpoint/device/precision are evaluation targets, not observed active settings.']}
    output.mkdir(parents=True, exist_ok=False)
    (output/'experiment.json').write_text(experiment.model_dump_json(indent=2)+'\n')
    (output/'setup.json').write_text(json.dumps(setup, indent=2)+'\n')
    return setup
