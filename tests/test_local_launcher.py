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

    def test_busy_port_opens_new_copy_on_actual_free_port(self):
        import errno
        from unittest.mock import MagicMock
        server=MagicMock(server_port=49123)
        with patch.object(sys,'argv',['run_local.py','--no-browser']),patch.object(run_local,'require_tools',return_value=('node','npm')),patch.object(run_local,'prepare_pdf_reader'),patch.object(run_local,'prepare_browser'),patch('app.initialize'),patch('http.server.ThreadingHTTPServer',side_effect=[OSError(errno.EADDRINUSE,'busy'),server]) as bind,patch('builtins.print') as output:
            self.assertEqual(run_local.main(),0)
        self.assertEqual(bind.call_args.args[0],('127.0.0.1',0))
        server.serve_forever.assert_called_once()
        self.assertTrue(any('http://127.0.0.1:49123/dashboard/' in str(c) for c in output.call_args_list))

    def test_other_bind_errors_do_not_switch_ports(self):
        import errno
        with patch.object(sys,'argv',['run_local.py','--no-browser']),patch.object(run_local,'require_tools',return_value=('node','npm')),patch.object(run_local,'prepare_pdf_reader'),patch.object(run_local,'prepare_browser'),patch('app.initialize'),patch('http.server.ThreadingHTTPServer',side_effect=OSError(errno.EACCES,'denied')) as bind,patch('builtins.print'):
            self.assertEqual(run_local.main(),1)
        bind.assert_called_once()
