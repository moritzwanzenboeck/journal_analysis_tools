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


def existing_app_error(output):
    return FileExistsError(f'App already exists: {output}. Close the launcher and rerun with --replace to rebuild it.')


def publish_app(built, output, *, replace=False):
    """Publish a completed build, retaining the old app until the build succeeds."""
    if output.is_symlink():
        raise ValueError(f'Refusing to replace a symbolic link: {output}')
    if not output.exists():
        if built.is_file():
            with built.open('rb') as reader, output.open('xb') as writer:
                shutil.copyfileobj(reader, writer)
        else:
            built.rename(output)
        return
    if not replace:
        raise existing_app_error(output)
    if built.is_dir() != output.is_dir():
        raise ValueError(f'The existing app has the wrong file type: {output}')
    if built.is_file():
        # On Windows a running executable cannot be replaced; failure leaves it intact.
        try:
            built.replace(output)
        except PermissionError as error:
            raise PermissionError('Close Journal Notebook Launcher, then run the build again with --replace.') from error
        return
    # macOS bundles are directories. Keep the previous bundle outside the build
    # temporary directory so even a failed rollback cannot delete the old app.
    backup = Path(tempfile.mkdtemp(prefix=f'.{output.name}.previous-', dir=output.parent))
    previous = backup / output.name
    try:
        output.rename(previous)
    except BaseException:
        backup.rmdir()
        raise
    try:
        built.rename(output)
    except BaseException:
        try:
            previous.rename(output)
        except OSError as error:
            raise RuntimeError(f'Could not restore the previous app; it is preserved at {previous}') from error
        backup.rmdir()
        raise
    shutil.rmtree(backup)


def install_windows(root, destination, *, replace=False):
    root = Path(root).resolve()
    destination = Path(destination).expanduser().resolve()
    output = destination / WINDOWS_APP_NAME
    if output.exists() and not replace:
        raise existing_app_error(output)
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
    # Staging on the destination filesystem permits an atomic executable replacement.
    with tempfile.TemporaryDirectory(prefix='.journal-windows-launcher-', dir=destination) as temporary:
        script = Path(temporary) / 'launcher.cs'
        script.write_text(source, encoding='utf-8-sig')
        built = Path(temporary) / WINDOWS_APP_NAME
        subprocess.run([str(compiler), '/nologo', '/target:winexe', '/optimize+',
                        '/reference:System.Windows.Forms.dll', f'/out:{built}', str(script)], check=True)
        publish_app(built, output, replace=replace)
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


def install(root, destination, *, replace=False):
    root = Path(root).resolve()
    destination = Path(destination).expanduser().resolve()
    # Validate everything before creating anything.
    for name in ('notebook_launcher.py', 'app/__init__.py', 'app/launcher.py',
                 'app/notebook_services.py', 'app/launch_notebook.sh',
                 'create_journal_analysis.ipynb', 'clean_and_count_text.ipynb'):
        if not (root/name).is_file():
            raise FileNotFoundError(root/name)
    output = destination / APP_NAME
    if output.exists() and not replace:
        raise existing_app_error(output)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.journal-notebook-launcher-', dir=destination) as temporary:
        script = Path(temporary)/'launcher.applescript'
        script.write_text(launcher_source(root), encoding='utf-8')
        built = Path(temporary) / APP_NAME
        subprocess.run(['/usr/bin/osacompile', '-o', str(built), str(script)], check=True)
        icon = root/'app'/'assets'/'app.icns'
        if icon.is_file():
            shutil.copyfile(icon, built/'Contents'/'Resources'/'applet.icns')
        publish_app(built, output, replace=replace)
    print('Installed Finder launcher:', output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent.parent
    parser.add_argument('--destination', type=Path, default=root)
    parser.add_argument('--replace', action='store_true', help='Rebuild and replace an existing launcher after a successful build')
    args = parser.parse_args()
    try:
        if sys.platform == 'win32':
            install_windows(root, args.destination, replace=args.replace)
        elif sys.platform == 'darwin':
            install(root, args.destination, replace=args.replace)
        else:
            parser.error('App building is supported on Windows and macOS. Run python notebook_launcher.py on Linux.')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Could not build launcher: {error}\n')


if __name__ == '__main__':
    main()
