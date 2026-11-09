"""Persistence and input validation for the desktop interface (no GUI imports)."""
from datetime import date, datetime
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import journal_tools as tools

APP_NAME = 'Journal Analysis Tools'
VERSION = '1.0.0'


def settings_path():
    if sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return base / APP_NAME / 'settings.json'


def load_settings(path=None):
    path = Path(path) if path else settings_path()
    try:
        settings = json.loads(path.read_text(encoding='utf-8'))
        return settings if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings, path=None):
    path = Path(path) if path else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def project_options(journal, start, end, count, parent, *, basis='first', seed='', folder='', archive=''):
    """Validate form values before starting a background job."""
    if not isinstance(journal, tools.Journal):
        raise ValueError('Find and select the journal you want to analyse.')
    try:
        start, end = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        raise ValueError('Choose valid start and end dates.') from None
    tools.validate_window(start, end, basis)
    try:
        count = int(count)
        parsed_seed = int(seed.strip()) if seed.strip() else None
    except (TypeError, ValueError):
        raise ValueError('Paper count and random seed must be whole numbers.') from None
    if count < 1:
        raise ValueError('Choose at least one random paper.')
    if not parent.strip() or not Path(parent).expanduser().is_dir():
        raise ValueError('Choose an existing folder for your new project.')
    if archive.strip() and not Path(archive).expanduser().is_file():
        raise ValueError('Choose an existing archived Crossref JSON file.')
    return dict(journal=journal, start=start, end=end, count=count,
                projects_root=Path(parent).expanduser(), date_basis=basis, seed=parsed_seed,
                project_name=folder.strip() or None,
                input_json=Path(archive).expanduser() if archive.strip() else None)


def default_dates():
    today = datetime.now(ZoneInfo('Europe/Zurich')).date()
    return tools.months_before(today, 12).isoformat(), today.isoformat()
