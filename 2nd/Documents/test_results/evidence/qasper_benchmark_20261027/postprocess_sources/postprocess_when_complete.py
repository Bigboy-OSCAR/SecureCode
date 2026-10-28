"""Wait for the existing runner, then analyze, audit and update the report.

Never starts or retries inference. An incomplete runner, changed source, failed
audit or concurrent report edit stops this pipeline without publishing results.
The OS runner lock remains held through postprocessing to prevent a new run
from mutating the evidence being audited.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

from common import HERE, OUT, dump, now, read, sha

STAGES = [
    ('analysis', 'analyze_results.py', ['analyze']),
    ('verification', 'verify_results.py', []),
    ('report', 'report_documents.py', ['apply']),
]
NEW_SOURCES = ['postprocess_when_complete.py', 'test_postprocess_when_complete.py',
               'verify_results.py', 'test_verify_results.py', 'report_documents.py']


def source_guard(out):
    protocol = read(out / 'protocol.json')
    manifest = read(out / 'postprocess_manifest.json')
    assert sha(out / 'protocol.json') == manifest['protocol_sha256'], 'Protocol changed'
    assert set(manifest['sources']) == set(NEW_SOURCES), 'Postprocessing source list changed'
    assert manifest['stages'] == [list(stage) for stage in STAGES], 'Postprocessing stage list changed'
    for name, expected in manifest['sources'].items():
        assert sha(HERE / name) == expected, ('Postprocessing source changed', name)
        assert sha(out / 'postprocess_sources' / name) == expected, ('Postprocessing snapshot changed', name)
    for path, expected in protocol['source_hashes'].items():
        assert sha(path) == expected, ('Frozen experiment source changed', path)
    return protocol, manifest


def completion_guard(out):
    completed = read(out / 'completed.json')
    assert completed['rows'] == 3936, 'Incomplete result population'
    assert sha(out / 'results.jsonl') == completed['results_sha256'], 'Completed results changed'
    return completed


def freeze(out):
    assert not (out / 'postprocess_manifest.json').exists(), 'Postprocessing is already frozen'
    snapshot = out / 'postprocess_sources'
    sources = {}
    with tempfile.TemporaryDirectory(prefix='.postprocess_sources-', dir=out) as temporary:
        staging = Path(temporary)
        for name in NEW_SOURCES:
            source = HERE / name
            sources[name] = sha(source)
            (staging / name).write_bytes(source.read_bytes())
            assert sha(staging / name) == sources[name]
        if snapshot.exists():
            # Recover an interruption between the atomic rename and manifest write.
            assert {p.name for p in snapshot.iterdir()} == set(sources)
            assert all(sha(snapshot / name) == expected for name, expected in sources.items())
        else:
            os.replace(staging, snapshot)
    manifest = {'created_at_utc': now(), 'sources': sources,
                'protocol_sha256': sha(out / 'protocol.json'),
                'purpose': 'Post-inference full-result verification and report generation; does not alter frozen experiment design.',
                'stages': STAGES}
    dump(out / 'postprocess_manifest.json', manifest)
    return manifest


def watch(out):
    out = Path(out)
    assert out == OUT, 'This supervisor is bound to the existing experiment'
    status = {'pid': os.getpid(), 'started_at_utc': now(), 'status': 'starting',
              'stages_completed': [], 'inference_started_or_retried': False}

    def update(**values):
        status.update(values, updated_at_utc=now())
        dump(out / 'postprocess_status.json', status)

    with (out / 'postprocess.lock').open('a+') as supervisor_lock:
        fcntl.flock(supervisor_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        supervisor_lock.seek(0)
        supervisor_lock.truncate()
        supervisor_lock.write(str(os.getpid()) + '\n')
        supervisor_lock.flush()
        try:
            source_guard(out)
            with (out / 'runner.lock').open('a+') as runner_lock:
                runner_lock.seek(0)
                update(status='waiting_for_runner', observed_runner_pid=runner_lock.read().strip())
                fcntl.flock(runner_lock.fileno(), fcntl.LOCK_EX)
                source_guard(out)
                completed = completion_guard(out)
                update(status='runner_complete', completed_result_rows=completed['rows'])
                for name, script, arguments in STAGES:
                    source_guard(out)
                    update(status='running_stage', active_stage=name)
                    log = out / ('postprocess_' + name + '.log')
                    command = [sys.executable, '-B', str(HERE / script), *arguments]
                    with log.open('ab') as stream:
                        stream.write(('\nStarted ' + now() + '\n').encode())
                        stream.flush()
                        child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                                 pass_fds=(runner_lock.fileno(), supervisor_lock.fileno()))
                        update(child_pid=child.pid, child_command=command)
                        returncode = child.wait()
                        update(child_pid=None, last_child_returncode=returncode)
                        if returncode:
                            raise subprocess.CalledProcessError(returncode, command)
                    source_guard(out)
                    status['stages_completed'].append(name)
                    update(last_successful_stage=name)
                evidence = read(out / 'report_update_verification.json')
                assert evidence['status'] == 'PASS'
                update(status='report_ready_for_final_review', active_stage=None,
                       report_path=evidence['report_path'], report_sha256=evidence['report_sha256'])
        except BaseException as error:
            update(status='needs_attention', error_type=type(error).__name__, error=str(error),
                   traceback=traceback.format_exc())
            raise
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['freeze', 'watch'])
    arguments = parser.parse_args()
    result = freeze(OUT) if arguments.phase == 'freeze' else watch(OUT)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
