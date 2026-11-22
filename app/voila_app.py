"""Serve the two notebook views and their shared navigation with Voilà."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from jupyter_server.base.handlers import APIHandler, JupyterHandler
from tornado import web
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.netutil import bind_sockets
from traitlets.config import Config
from voila.app import Voila
from voila.tornado.contentshandler import VoilaContentsHandler
from voila.tornado.handler import TornadoVoilaHandler
from voila.tornado.treehandler import TornadoVoilaTreeHandler

from .notebook_services import SERVICES

DASHBOARD_PAGE = Path(__file__).with_name('assets') / 'dashboard.html'
NOTEBOOK_TEMPLATE = DASHBOARD_PAGE.with_name('journal_notebook.html.j2')


class DashboardHandler(JupyterHandler):
    @web.authenticated
    def get(self):
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        self.set_header('Cache-Control', 'no-store')
        self.finish(DASHBOARD_PAGE.read_text(encoding='utf-8'))


class KernelListHandler(APIHandler):
    @web.authenticated
    def get(self):
        self.finish(json.dumps(self.kernel_manager.list_kernels()))


class ShutdownHandler(APIHandler):
    @web.authenticated
    def post(self):
        self.set_status(204)
        self.finish()
        self.settings['voila'].ioloop.add_callback(self.settings['voila'].ioloop.stop)


class JournalVoila(Voila):
    def init_handlers(self):
        notebooks = '|'.join(re.escape(spec.notebook) for spec in SERVICES)
        handlers = [('/', DashboardHandler), ('/api/kernels', KernelListHandler),
                    ('/api/shutdown', ShutdownHandler)]
        for route in super().init_handlers():
            if route[1] in (TornadoVoilaTreeHandler, VoilaContentsHandler):
                continue
            if route[1] is TornadoVoilaHandler:
                route = (rf'/voila/render/(?P<path>{notebooks})', *route[1:])
            handlers.append(route)
        return handlers

    def listen(self):
        # The OS picks a free port and keeps it reserved for this server.
        sockets = bind_sockets(0, address='127.0.0.1')
        server = HTTPServer(self.app)
        server.add_sockets(sockets)
        self.ioloop = IOLoop.current()
        try:
            ready = Path(os.environ['JUPYTER_RUNTIME_DIR']) / 'dashboard-server.json'
            ready.write_text(json.dumps({'port': sockets[0].getsockname()[1]}), encoding='utf-8')
            self.ioloop.start()
        finally:
            server.stop()
            self.stop()


def main():
    config = Config()
    config.VoilaConfiguration.strip_sources = True
    config.VoilaConfiguration.file_allowlist = []
    config.VoilaConfiguration.allow_template_override = 'NO'
    config.VoilaExporter.template_file = NOTEBOOK_TEMPLATE.name
    config.VoilaExporter.exclude_markdown = True
    config.Voila.tornado_settings = {'allow_remote_access': False}
    app = JournalVoila(config=config, config_file_paths=[], token=os.environ.pop('JUPYTER_TOKEN'),
                       root_dir=sys.argv[1], connection_dir_root=os.environ['JUPYTER_RUNTIME_DIR'])
    app.initialize([])
    app.template_paths.insert(0, str(DASHBOARD_PAGE.parent))
    app.start()


if __name__ == '__main__':
    main()
