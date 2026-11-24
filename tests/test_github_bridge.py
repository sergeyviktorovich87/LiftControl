import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import subprocess

spec=importlib.util.spec_from_file_location('bridge',Path(__file__).resolve().parents[1]/'deploy/offline/github-update-bridge.py')
b=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BridgeTests(unittest.TestCase):
    def test_only_fixed_operations(self):
        for raw in ('{"id":1,"action":"shell","target":"x"}',
                    '{"id":1,"action":"install","target":"0.13.18;ls"}',
                    '{"id":0,"action":"check","target":""}'):
            with patch.object(b.u,'api_container',return_value='a'*64),patch.object(b.u,'run',return_value=subprocess.CompletedProcess([],0,raw,'')):
                with self.assertRaises(ValueError):
                    b.get_request(0)

    def test_target_change_and_check_only_never_execute(self):
        data={'tag_name':'v0.13.18','draft':False,'prerelease':False,
              'assets':[{'name':'LiftControl-v0.13.18-update.zip'+suffix,'state':'uploaded','size':100}
                        for suffix in ('','.sha256','.intoto.jsonl')]}
        import tempfile
        with tempfile.TemporaryDirectory() as temp,patch.multiple(b.u,STATE=Path(temp),
                health=lambda:'0.13.17',get_json=lambda *args:data):
            with patch.object(b.u,'run') as run:
                self.assertEqual(b.u.update(check_only=True),('available','0.13.18'))
                self.assertEqual(b.u.update(expected_target='0.13.19'),('changed','0.13.18'))
                run.assert_not_called()
