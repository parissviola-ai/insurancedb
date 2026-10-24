"""Start the local dashboard; install its pinned browser dependencies on first run."""
import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import webbrowser

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.local-cache'


def require_tools():
    if sys.version_info < (3, 12):
        raise RuntimeError('Install Python 3.12 or newer from https://www.python.org/downloads/macos/ and reopen the launcher.')
    node = shutil.which('node')
    npm = shutil.which('npm')
    if not node or not npm:
        raise RuntimeError('Install the free Node.js LTS release from https://nodejs.org/en/download and reopen the launcher.')
    version = subprocess.check_output([node, '--version'], text=True).strip()
    if int(version.lstrip('v').split('.')[0]) < 20:
        raise RuntimeError('Update Node.js to the current LTS release (version 20 or newer), then reopen the launcher.')
    return node, npm


def prepare_pdf_reader():
    """Install into an app-local virtual environment, never system Python."""
    requirements = ROOT / 'requirements-local.txt'
    wanted = requirements.read_text().strip().split('==')[1]
    try:
        import pypdf
        if pypdf.__version__ == wanted:
            return
    except ImportError:
        pass
    import venv
    environment = CACHE / 'python'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Setting up the free PDF reader in this application folder…', flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--cache-dir', str(CACHE / 'pip'), '-r', str(requirements)], cwd=ROOT, check=True)
    os.execv(str(python), [str(python), str(ROOT / 'run_local.py'), *sys.argv[1:]])


def prepare_browser(node, npm):
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(CACHE / 'browsers')
    installed = ROOT / 'node_modules' / 'playwright' / 'package.json'
    wanted = json.loads((ROOT / 'package.json').read_text())['dependencies']['playwright']
    if not installed.exists() or json.loads(installed.read_text()).get('version') != wanted:
        print('First-run setup: downloading the free search software. This may take a few minutes.', flush=True)
        subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--cache', str(CACHE / 'npm')], cwd=ROOT, check=True)
    configured = os.environ.get('SHOPPING_CHROMIUM_PATH')
    browser_path = configured or subprocess.check_output(
        [node, '-e', "process.stdout.write(require('playwright').chromium.executablePath())"], cwd=ROOT, text=True).strip()
    if configured and not Path(configured).is_file():
        raise RuntimeError('The configured Chromium path was not found. Remove SHOPPING_CHROMIUM_PATH or correct it.')
    if not Path(browser_path).is_file():
        print('Downloading the free Chromium browser used for carrier searches…', flush=True)
        subprocess.run([node, str(ROOT / 'node_modules' / 'playwright' / 'cli.js'), 'install', 'chromium'], cwd=ROOT, check=True)
        if not Path(browser_path).is_file():
            raise RuntimeError('Chromium installation did not finish. Check the internet connection and reopen the launcher.')


def main():
    parser = argparse.ArgumentParser(description='Run Plan Finder on this computer only.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check', action='store_true', help='Check Python/Node without downloading or starting anything.')
    args = parser.parse_args()
    try:
        node, npm = require_tools()
        if args.check:
            print('Python and Node.js are ready. The first launch will set up the free PDF reader and search browser if needed.')
            return 0
        prepare_pdf_reader()
        prepare_browser(node, npm)
        import app
        from http.server import ThreadingHTTPServer
        app.initialize()
        try:
            server = ThreadingHTTPServer(('127.0.0.1', args.port), app.Handler)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            # Bind first, then open this server's URL. An occupied port may
            # belong to an older extracted copy or an unrelated application.
            server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
            print(f'Port {args.port} is in use. This copy will use port {server.server_port}.', flush=True)
        url = f'http://127.0.0.1:{server.server_port}/dashboard/'
        print('Application folder: ' + str(ROOT), flush=True)
        print('Version: ZIP-based plan details v5', flush=True)
        print('\nPlan Finder is running on this Mac only.', flush=True)
        print('Open: ' + url, flush=True)
        print('Keep this Terminal window open. Press Control+C here to stop.\n', flush=True)
        if not args.no_browser:
            threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        with server:
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print('\nPlan Finder stopped.')
        return 0
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        print('\nSetup could not finish: ' + str(error), file=sys.stderr)
        print('No hosting service or subscription was created.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
