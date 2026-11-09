"""Build a Windows or macOS app for both notebook services (Python required)."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

APP_NAME = 'Journal Notebook Launcher.app'
WINDOWS_APP_NAME = 'Journal Notebook Launcher.exe'


def install_windows(root, destination):
    root = Path(root).resolve()
    destination = Path(destination).expanduser().resolve()
    output = destination / WINDOWS_APP_NAME
    if output.exists():
        raise FileExistsError(output)
    # Verify the real entry point and its environment before producing an app.
    subprocess.run([sys.executable, str(root / 'notebook_launcher.py'), '--check'], check=True)
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    if not pythonw.is_file():
        raise FileNotFoundError(f'Windowed Python executable not found: {pythonw}')
    framework = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET'
    compiler = next((path for path in (
        framework / 'Framework64/v4.0.30319/csc.exe',
        framework / 'Framework/v4.0.30319/csc.exe',
    ) if path.is_file()), None)
    if compiler is None:
        raise FileNotFoundError('The Windows app builder needs the .NET Framework C# compiler (csc.exe).')
    template = Path(__file__).with_name('windows_launcher.cs').read_text(encoding='utf-8')
    literal = lambda value: '@"' + str(value).replace('"', '""') + '"'
    source = template.replace('__CHECKOUT_ROOT__', literal(root)).replace('__PYTHON_EXECUTABLE__', literal(pythonw))
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='journal-windows-launcher-') as temporary:
        script = Path(temporary) / 'launcher.cs'
        script.write_text(source, encoding='utf-8-sig')
        built = Path(temporary) / WINDOWS_APP_NAME
        subprocess.run([str(compiler), '/nologo', '/target:winexe', '/optimize+',
                        '/reference:System.Windows.Forms.dll', f'/out:{built}', str(script)], check=True)
        # Exclusive creation preserves an existing app even if another build races.
        with built.open('rb') as reader, output.open('xb') as writer:
            shutil.copyfileobj(reader, writer)
    print('Built Windows launcher:', output)
    return output


def applescript_string(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def launcher_source(root):
    return f'''on run
  set toolsFolder to {applescript_string(root)}
  set appFolder to do shell script "/usr/bin/dirname " & quoted form of (POSIX path of (path to me))
  try
    do shell script "/usr/bin/test -f " & quoted form of (appFolder & "/notebook_launcher.py")
    set toolsFolder to appFolder
  end try
  set logFolder to (POSIX path of (path to library folder from user domain)) & "Logs/Journal Analysis Tools"
  do shell script "/bin/mkdir -p " & quoted form of logFolder
  set logFile to logFolder & "/launcher.log"
  set commandLine to "/usr/bin/env JOURNAL_TOOLS_BUILD_PYTHON=" & quoted form of {applescript_string(sys.executable)} & " /bin/bash " & quoted form of (toolsFolder & "/app/launch_notebook.sh") & " " & quoted form of toolsFolder
  do shell script "umask 077; /usr/bin/nohup " & commandLine & " </dev/null >>" & quoted form of logFile & " 2>&1 &"
end run
'''


def install(root, destination):
    root = Path(root).resolve()
    destination = Path(destination).expanduser()
    # Validate everything before creating anything; existing apps are not replaced.
    for name in ('notebook_launcher.py', 'app/__init__.py', 'app/launcher.py',
                 'app/notebook_services.py', 'app/launch_notebook.sh',
                 'create_journal_analysis.ipynb', 'clean_and_count_text.ipynb'):
        if not (root/name).is_file():
            raise FileNotFoundError(root/name)
    if (destination/APP_NAME).exists():
        raise FileExistsError(destination/APP_NAME)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='journal-notebook-launcher-') as temporary:
        script = Path(temporary)/'launcher.applescript'
        script.write_text(launcher_source(root), encoding='utf-8')
        subprocess.run(['/usr/bin/osacompile', '-o', str(destination/APP_NAME), str(script)], check=True)
    icon = root/'app'/'assets'/'app.icns'
    if icon.is_file():
        shutil.copyfile(icon, destination/APP_NAME/'Contents'/'Resources'/'applet.icns')
    print('Installed Finder launcher:', destination/APP_NAME)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent.parent
    parser.add_argument('--destination', type=Path, default=root)
    args = parser.parse_args()
    if sys.platform == 'win32':
        install_windows(root, args.destination)
    elif sys.platform == 'darwin':
        install(root, args.destination)
    else:
        parser.error('App building is supported on Windows and macOS. Run python notebook_launcher.py on Linux.')


if __name__ == '__main__':
    main()
