import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import run_local


class LauncherPDFTests(TestCase):
    def test_matching_reader_needs_no_install(self):
        version=(run_local.ROOT/'requirements-local.txt').read_text().strip().split('==')[1]
        with patch.dict(sys.modules,{'pypdf':SimpleNamespace(__version__=version)}),patch.object(run_local.subprocess,'run') as install:
            run_local.prepare_pdf_reader()
            install.assert_not_called()

    def test_reader_installs_only_into_app_local_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=Path(directory)/'cache'
            with patch.object(run_local,'CACHE',cache),patch.dict(sys.modules,{'pypdf':SimpleNamespace(__version__='0')}),patch('venv.EnvBuilder') as builder,patch.object(run_local.subprocess,'run') as install,patch.object(run_local.os,'execv') as restart:
                run_local.prepare_pdf_reader()
                builder.return_value.create.assert_called_once_with(cache/'python')
                command=install.call_args.args[0]
                self.assertTrue(command[0].startswith(str(cache)))
                self.assertIn(str(run_local.ROOT/'requirements-local.txt'),command)
                self.assertTrue(restart.call_args.args[0].startswith(str(cache)))
