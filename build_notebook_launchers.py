"""Install small Finder apps that start Jupyter and open either notebook.

These launchers use an existing Python/Jupyter installation. They do not bundle
Python. The standalone desktop app remains available for users without Python.
"""
import argparse
from pathlib import Path
import shlex
import subprocess
import tempfile

LAUNCHERS = (
    ('Open project notebook.app', 'create_journal_analysis.ipynb'),
    ('Open text notebook.app', 'clean_and_count_text.ipynb'),
)


def applescript_string(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def launcher_source(root, notebook):
    command = shlex.join(['/bin/bash', str(root/'launch_notebook.sh'), str(root), notebook])
    return f'''on run
  set logFolder to (POSIX path of (path to library folder from user domain)) & "Logs/Journal Analysis Tools"
  do shell script "/bin/mkdir -p " & quoted form of logFolder
  set logFile to logFolder & "/{Path(notebook).stem}.log"
  set commandLine to {applescript_string(command)}
  do shell script "/usr/bin/nohup " & commandLine & " </dev/null >" & quoted form of logFile & " 2>&1 &"
end run
'''


def install(root, destination):
    root = Path(root).resolve()
    destination = Path(destination).expanduser()
    if not (root/'launch_notebook.sh').is_file():
        raise FileNotFoundError('Keep this builder alongside launch_notebook.sh.')
    # Validate both outputs before creating anything; existing apps are not replaced.
    for name, notebook in LAUNCHERS:
        if not (root/notebook).is_file():
            raise FileNotFoundError(root/notebook)
        if (destination/name).exists():
            raise FileExistsError(destination/name)
    destination.mkdir(parents=True, exist_ok=True)
    for name, notebook in LAUNCHERS:
        with tempfile.TemporaryDirectory(prefix='journal-notebook-launcher-') as temporary:
            script = Path(temporary)/'launcher.applescript'
            script.write_text(launcher_source(root, notebook))
            subprocess.run(['/usr/bin/osacompile', '-o', str(destination/name), str(script)], check=True)
        print('Installed Finder launcher:', destination/name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=Path.home()/'Applications')
    args = parser.parse_args()
    install(Path(__file__).resolve().parent, args.destination)


if __name__ == '__main__':
    main()
