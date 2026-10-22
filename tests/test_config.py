"""Exercise the documented .env workflow in fresh, isolated Python processes."""
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class DotenvSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'extracted-app'
        (self.repo / 'app').mkdir(parents=True)
        (self.repo / 'app' / '__init__.py').write_text('')
        for filename in ('config.py', 'clients.py'):
            shutil.copyfile(ROOT / 'app' / filename, self.repo / 'app' / filename)
        self.other = Path(self.temp.name) / 'different-working-directory'
        self.other.mkdir()
        (self.other / '.env').write_text('AIJ_API_KEY=wrong-directory-value\n')
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith('AIJ_') and k not in ('PYTHONPATH', 'PYTHON_DOTENV_DISABLED')}
        self.env['PYTHONPATH'] = str(self.repo)
        self.env['PYTHONPYCACHEPREFIX'] = str(Path(self.temp.name) / 'pycache')

    def write_template(self):
        template = (ROOT / '.env.example').read_text()
        template = template.replace('your-class-api-key-here', 'isolated-file-test-value')
        for name, port in (('CHAT', 19001), ('ART', 19006), ('MUSIC', 19007), ('TTS', 19008)):
            template = re.sub(rf'^# AIJ_{name}_BASE_URL=.*$',
                              f'AIJ_{name}_BASE_URL=http://127.0.0.1:{port}', template, flags=re.M)
        (self.repo / '.env').write_text(template)

    def run_fresh(self, code):
        result = subprocess.run([sys.executable, '-c', code], cwd=self.other,
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_filled_template_loads_without_exported_variables_from_another_directory(self):
        self.write_template()
        self.run_fresh('''
from app import config, clients
assert config.API_KEY == 'isolated-file-test-value'
assert clients.SESSION.headers['Authorization'] == 'Bearer isolated-file-test-value'
assert config.CHAT_BASE_URL == 'http://127.0.0.1:19001'
assert config.ART_BASE_URL == 'http://127.0.0.1:19006'
assert config.MUSIC_BASE_URL == 'http://127.0.0.1:19007'
assert config.TTS_BASE_URL == 'http://127.0.0.1:19008'
''')

    def test_existing_environment_variables_take_precedence(self):
        self.write_template()
        self.env['AIJ_API_KEY'] = 'isolated-exported-test-value'
        self.env['AIJ_CHAT_BASE_URL'] = 'http://127.0.0.1:29001'
        self.run_fresh('''
from app import config, clients
assert config.API_KEY == 'isolated-exported-test-value'
assert clients.SESSION.headers['Authorization'] == 'Bearer isolated-exported-test-value'
assert config.CHAT_BASE_URL == 'http://127.0.0.1:29001'
assert config.ART_BASE_URL == 'http://127.0.0.1:19006'
''')

    def test_missing_repo_env_does_not_load_unrelated_working_directory_env(self):
        self.run_fresh('''
from app import config
assert config.API_KEY == ''
assert config.CHAT_BASE_URL == 'http://dobolyi.com:9001/v1'
''')
