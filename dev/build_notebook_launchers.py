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


def install_windows(root, destination, *, replace=False, portable=False):
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
    source = template.replace('__CHECKOUT_ROOT__', literal('' if portable else root)).replace('__PYTHON_EXECUTABLE__', literal('' if portable else pythonw))
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


def launcher_source(root, *, portable=False):
    return f'''use framework "Foundation"
use scripting additions

on environmentValue(variableName)
  set processEnvironment to current application's NSProcessInfo's processInfo()'s environment()
  set variableValue to processEnvironment's objectForKey:variableName
  if variableValue is missing value then return ""
  return variableValue as text
end environmentValue

on toolsFolderIsValid(folderPath)
  if folderPath is "" then return false
  try
    do shell script "/bin/test -f " & quoted form of (folderPath & "/notebook_launcher.py") & " && /bin/test -f " & quoted form of (folderPath & "/app/launch_notebook.sh") & " && /bin/test -f " & quoted form of (folderPath & "/app/launcher.py") & " && /bin/test -f " & quoted form of (folderPath & "/create_journal_analysis.ipynb") & " && /bin/test -f " & quoted form of (folderPath & "/clean_and_count_text.ipynb")
    return true
  on error
    return false
  end try
end toolsFolderIsValid

on findToolsFolder(appPath, configuredFolder)
  set appFolder to do shell script "/usr/bin/dirname " & quoted form of appPath
  if my toolsFolderIsValid(appFolder) then return appFolder
  if my toolsFolderIsValid(configuredFolder) then return configuredFolder
  return ""
end findToolsFolder

on run
  set toolsFolder to ""
  set embeddedFolder to (POSIX path of (path to me)) & "/Contents/Resources/JournalTools"
  if my toolsFolderIsValid(embeddedFolder) then
    set toolsFolder to embeddedFolder
  else
    set toolsFolder to my findToolsFolder(POSIX path of (path to me), {applescript_string('' if portable else root)})
  end if
  set checkOnly to false
  try
    set checkOnly to ((my environmentValue("JOURNAL_TOOLS_APP_CHECK")) is "1")
  end try
  if toolsFolder is "" and checkOnly then error "Tools folder not found beside this app. Open it normally to choose the extracted release folder."
  repeat while toolsFolder is ""
    try
      set selectedFolder to POSIX path of (choose folder with prompt "Choose the extracted Journal Analysis Tools folder containing notebook_launcher.py and app. macOS may hide these neighboring files when opening a downloaded app.")
    on error number -128
      return
    end try
    if my toolsFolderIsValid(selectedFolder) then
      set toolsFolder to selectedFolder
    else
      display alert "Choose the complete tools folder" message "Extract the complete release and select its folder containing notebook_launcher.py, app and both notebooks."
    end if
  end repeat
  set embeddedFolder to (POSIX path of (path to me)) & "/Contents/Resources/JournalTools"
  if my toolsFolderIsValid(embeddedFolder) then
    set pythonExecutable to embeddedFolder & "/app/python/bin/python3"
    set requestedPython to my environmentValue("JOURNAL_TOOLS_PYTHON")
    if requestedPython is not "" then set pythonExecutable to requestedPython
    set commandLine to "/usr/bin/env PYTHONDONTWRITEBYTECODE=1 " & quoted form of pythonExecutable & " -I -B " & quoted form of (embeddedFolder & "/app/macos_bootstrap.py") & " " & quoted form of embeddedFolder
  else
    set commandLine to "/usr/bin/env JOURNAL_TOOLS_BUILD_PYTHON=" & quoted form of {applescript_string('' if portable else sys.executable)} & " /bin/bash " & quoted form of (toolsFolder & "/app/launch_notebook.sh") & " " & quoted form of toolsFolder
  end if
  repeat with envName in {{"JOURNAL_TOOLS_PYTHON", "JOURNAL_TOOLS_NO_DIALOG", "JOURNAL_TOOLS_WORKSPACE", "JOURNAL_TOOLS_PROJECTS_ROOT"}}
    set envValue to my environmentValue(envName as text)
    if envValue is not "" then set commandLine to "/usr/bin/env " & (envName as text) & "=" & quoted form of envValue & " " & commandLine
  end repeat
  if checkOnly then
    do shell script commandLine & " --check"
    return
  end if
  set logFolder to (POSIX path of (path to library folder from user domain)) & "Logs/Journal Analysis Tools"
  do shell script "/bin/mkdir -p " & quoted form of logFolder
  set logFile to logFolder & "/launcher.log"
  do shell script "umask 077; /usr/bin/nohup " & commandLine & " </dev/null >>" & quoted form of logFile & " 2>&1 &"
end run
'''


def validate_macos_app(bundle):
    """Reject a destination that strips executable bits or adds signing metadata."""
    hint = ('Install the launcher on a local disk instead: '
            '--destination "~/Applications" --replace. The notebooks can stay in the shared folder.')
    if not os.access(bundle / 'Contents' / 'MacOS' / 'applet', os.X_OK):
        raise OSError(f'This destination does not preserve macOS app executable permissions. {hint}')
    result = subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(bundle)],
                            capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip() or 'App signature validation failed.'
        raise OSError(f'This destination cannot preserve a valid macOS app: {detail}\n{hint}')



def embed_macos_tools(root, bundle):
    """Keep downloaded code/runtime inside the signed app, visible during translocation."""
    payload = bundle / 'Contents/Resources/JournalTools'
    payload.mkdir(parents=True)
    for name in ('notebook_launcher.py', 'requirements.txt', 'create_journal_analysis.ipynb', 'clean_and_count_text.ipynb'):
        shutil.copyfile(root / name, payload / name)
    if (root / 'RELEASE.json').is_file():
        shutil.copyfile(root / 'RELEASE.json', payload / 'RELEASE.json')
    # The release root is already populated from the package source whitelist.
    shutil.copytree(root / 'app', payload / 'app', copy_function=shutil.copy,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
    if not (payload / 'app/macos_bootstrap.py').is_file():
        raise FileNotFoundError('Missing Mac bootstrap in the release payload.')
    # Python-build-standalone ships unsigned executables. Sign all Mach-O helpers
    # and extensions before sealing the outer app; never strip quarantine on startup.
    magic = {bytes.fromhex(value) for value in ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe',
                                               'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}
    for binary in sorted((payload / 'app/python').rglob('*')):
        if binary.is_file():
            with binary.open('rb') as stream:
                is_macho = stream.read(4) in magic
            if is_macho:
                subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(binary)],
                               check=True, capture_output=True, text=True)
    return payload

def install(root, destination, *, replace=False, portable=False):
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
    # Compiling/signing on SMB/FAT-style destinations can introduce Finder or
    # resource-fork metadata. Keep the compiler and its working directory local.
    with tempfile.TemporaryDirectory(prefix='journal-notebook-compile-', dir='/private/tmp') as temporary:
        script = Path(temporary)/'launcher.applescript'
        script.write_text(launcher_source(root, portable=portable), encoding='utf-8')
        compiled = Path(temporary) / APP_NAME
        subprocess.run(['/usr/bin/osacompile', '-o', str(compiled), str(script)],
                       cwd=temporary, check=True)
        icon = root/'app'/'assets'/'app.icns'
        if icon.is_file():
            shutil.copyfile(icon, compiled/'Contents'/'Resources'/'applet.icns')
        if portable and (root / 'app/python').is_dir():
            embed_macos_tools(root, compiled)
        # Sign after embedding the runtime and setting all resources.
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(compiled)],
                       check=True, capture_output=True, text=True)
        # Publication still stages on the destination filesystem, preserving the
        # existing rollback/rename guarantees even when compilation was elsewhere.
        with tempfile.TemporaryDirectory(prefix='.journal-notebook-launcher-', dir=destination) as publication:
            built = Path(publication) / APP_NAME
            shutil.copytree(compiled, built, copy_function=shutil.copy)
            validate_macos_app(built)
            publish_app(built, output, replace=replace)
    print('Installed Finder launcher:', output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent.parent
    parser.add_argument('--destination', type=Path, default=root)
    parser.add_argument('--portable', action='store_true', help='Build for a release: locate tools and Python on the recipient computer')
    parser.add_argument('--replace', action='store_true', help='Rebuild and replace an existing launcher after a successful build')
    args = parser.parse_args()
    try:
        if sys.platform == 'win32':
            install_windows(root, args.destination, replace=args.replace, portable=args.portable)
        elif sys.platform == 'darwin':
            install(root, args.destination, replace=args.replace, portable=args.portable)
        else:
            parser.error('App building is supported on Windows and macOS. Run python notebook_launcher.py on Linux.')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Could not build launcher: {error}\n')


if __name__ == '__main__':
    main()
