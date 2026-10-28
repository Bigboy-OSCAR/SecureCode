import fcntl
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import postprocess_when_complete as pipeline


class PipelineSafetyTests(unittest.TestCase):
    def test_missing_completion_never_runs_analysis_or_updates_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            with patch.object(pipeline, 'OUT', out), patch.object(pipeline, 'source_guard'), \
                    patch.object(pipeline.subprocess, 'Popen') as execute:
                with self.assertRaises(FileNotFoundError):
                    pipeline.watch(out)
            execute.assert_not_called()
            self.assertEqual(json.loads((out / 'postprocess_status.json').read_text())['status'], 'needs_attention')

    def test_failed_verification_never_runs_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            children = [Mock(pid=100, wait=Mock(return_value=0)), Mock(pid=101, wait=Mock(return_value=1))]
            with patch.object(pipeline, 'OUT', out), patch.object(pipeline, 'source_guard'), \
                    patch.object(pipeline, 'completion_guard', return_value={'rows': 29268}), \
                    patch.object(pipeline.subprocess, 'Popen', side_effect=children) as execute:
                with self.assertRaises(subprocess.CalledProcessError):
                    pipeline.watch(out)
            commands = [call.args[0] for call in execute.call_args_list]
            self.assertEqual([Path(command[2]).name for command in commands], ['analyze_results.py', 'verify_results.py'])
            self.assertTrue(all(len(call.kwargs['pass_fds']) == 2 for call in execute.call_args_list))
            status = json.loads((out / 'postprocess_status.json').read_text())
            self.assertEqual(status['status'], 'needs_attention')
            self.assertEqual(status['stages_completed'], ['analysis'])

    def test_duplicate_supervisor_is_rejected_before_writing_status(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            with (out / 'postprocess.lock').open('a+') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(pipeline, 'OUT', out), self.assertRaises(BlockingIOError):
                    pipeline.watch(out)
            self.assertFalse((out / 'postprocess_status.json').exists())

    def test_completed_results_must_match_count_and_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / 'results.jsonl').write_text('isolated test fixture\n')
            marker = out / 'completed.json'
            marker.write_text(json.dumps({'rows': 1, 'results_sha256': pipeline.sha(out / 'results.jsonl')}))
            with self.assertRaises(AssertionError):
                pipeline.completion_guard(out)
            marker.write_text(json.dumps({'rows': 29268, 'results_sha256': 'incorrect'}))
            with self.assertRaises(AssertionError):
                pipeline.completion_guard(out)


if __name__ == '__main__':
    unittest.main()
