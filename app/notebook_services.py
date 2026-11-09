"""Manage only the Jupyter servers started by the notebook launcher."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import ProxyHandler, Request, build_opener

import psutil


@dataclass(frozen=True)
class ServiceSpec:
    key: str
    title: str
    notebook: str
    preferred_port: int


SERVICES = (
    ServiceSpec('project', 'Create journal project', 'create_journal_analysis.ipynb', 8888),
    ServiceSpec('text', 'Clean and count text', 'clean_and_count_text.ipynb', 8889),
)


def logs_directory():
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Logs' / 'Journal Analysis Tools'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Journal Analysis Tools' / 'Logs'
    return Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state')) / 'journal-analysis-tools'


class NotebookService:
    def __init__(self, spec, root, *, log_dir=None, python=None):
        self.spec = spec
        self.root = Path(root).resolve()
        self.python = str(python or sys.executable)
        self.log_path = Path(log_dir or logs_directory()) / f'{spec.key}.log'
        self.process = None
        self.port = None
        self.token = None
        self._runtime = None
        self._log = None
        self._children = set()
        self._opener = build_opener(ProxyHandler({}))

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    @property
    def base_url(self):
        return f'http://127.0.0.1:{self.port}/' if self.port else None

    @property
    def url(self):
        if not self.base_url:
            return None
        relative = (self.root / self.spec.notebook).relative_to(self.root.parent).as_posix()
        return self.base_url + 'notebooks/' + quote(relative, safe='/') + '?' + urlencode({'token': self.token})

    def request(self, path, method='GET', *, timeout=3):
        if not self.base_url:
            raise RuntimeError('The notebook service is not ready.')
        request = Request(self.base_url + path, method=method,
                          headers={'Authorization': f'token {self.token}'},
                          data=b'' if method == 'POST' else None)
        with self._opener.open(request, timeout=timeout) as response:
            body = response.read()
            return json.loads(body) if body else None

    def track_children(self):
        """Retain process identities so a server crash cannot hide its kernels."""
        if self.running:
            try:
                self._children.update(psutil.Process(self.process.pid).children(recursive=True))
            except psutil.NoSuchProcess:
                pass

    def start(self, *, timeout=60):
        if self.running:
            return
        self.force_stop()
        notebook = self.root / self.spec.notebook
        if not notebook.is_file():
            raise FileNotFoundError(f'Notebook not found: {notebook}')
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._runtime = tempfile.TemporaryDirectory(prefix='journal-jupyter-')
        runtime = Path(self._runtime.name)
        self.token = secrets.token_urlsafe(32)
        environment = dict(os.environ, JUPYTER_RUNTIME_DIR=str(runtime),
                           JUPYTER_CONFIG_DIR=str(runtime / 'config'), JUPYTER_TOKEN=self.token)
        environment.pop('JUPYTER_TOKEN_FILE', None)
        command = [self.python, '-m', 'notebook', '--no-browser',
                   '--ServerApp.ip=127.0.0.1', f'--ServerApp.port={self.spec.preferred_port}',
                   '--ServerApp.port_retries=100', '--ServerApp.base_url=/',
                   f'--ServerApp.root_dir={self.root.parent}', '--ServerApp.allow_remote_access=False']
        options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                   if os.name == 'nt' else {'start_new_session': True})
        try:
            self._log = self.log_path.open('w', encoding='utf-8')
            if os.name != 'nt':
                self.log_path.chmod(0o600)
            self.process = subprocess.Popen(command, cwd=self.root, env=environment,
                                            stdin=subprocess.DEVNULL, stdout=self._log,
                                            stderr=subprocess.STDOUT, **options)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if not self.running:
                    raise RuntimeError(f'Jupyter exited with code {self.process.returncode}. See {self.log_path}')
                self.track_children()
                try:
                    # Windows venv executables can spawn a child interpreter, so
                    # Jupyter's PID need not match Popen.pid. This runtime folder
                    # is private to this service and contains no other servers.
                    info_file = next(runtime.glob('jpserver-*.json'), None)
                    if info_file:
                        info = json.loads(info_file.read_text(encoding='utf-8'))
                        self.port = int(info['port'])
                        self.request('api/kernels', timeout=0.5)
                        return
                except (OSError, ValueError, KeyError):
                    self.port = None
                time.sleep(0.1)
            raise TimeoutError(f'Jupyter did not become ready within {timeout:g} seconds. See {self.log_path}')
        except BaseException:
            self.force_stop()
            raise

    def kill_kernels(self):
        """Delete every kernel belonging to this service; leave its server available."""
        kernels = self.request('api/kernels')
        for kernel in kernels:
            try:
                self.request('api/kernels/' + quote(kernel['id'], safe=''), 'DELETE', timeout=10)
            except HTTPError as error:
                if error.code != 404:
                    raise
        return len(kernels)

    def stop(self):
        self.track_children()
        if self.running and self.port:
            try:
                self.request('api/shutdown', 'POST')
                self.process.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                self.force_stop()
                return
        self.force_stop()

    def force_stop(self):
        """Kill the owned process tree, including kernels, without relying on HTTP."""
        self.track_children()
        if self.process is not None:
            processes = set(self._children)
            if self.running:
                try:
                    processes.add(psutil.Process(self.process.pid))
                except psutil.NoSuchProcess:
                    pass
            for process in processes:
                try:
                    process.kill()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(processes, timeout=10)
            if alive:
                raise RuntimeError('Could not stop all owned Jupyter processes. Try Force stop again.')
            self.process.wait(timeout=10)
        self._release()

    def _release(self):
        if self._log:
            self._log.close()
            self._log = None
        if self._runtime:
            self._runtime.cleanup()
            self._runtime = None
        self.process = None
        self.port = None
        self.token = None
        self._children.clear()
