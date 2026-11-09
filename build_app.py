"""Build a self-contained desktop app using the active Python environment.

Build on the target operating system/architecture. No user data is bundled.
"""
import argparse
from pathlib import Path
import platform
import subprocess
import sys

from app_support import APP_NAME


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'dist')
    parser.add_argument('--work', type=Path, default=Path(__file__).resolve().parent / 'build')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
               '--name', APP_NAME, '--distpath', str(args.output.resolve()),
               '--workpath', str(args.work.resolve()), '--specpath', str(args.work.resolve()),
               '--add-data', f'{root / "clean_and_count_text.ipynb"}:.',
               '--collect-data', 'certifi', '--collect-data', 'tzdata',
               '--exclude-module', 'IPython', '--exclude-module', 'ipywidgets',
               '--exclude-module', 'notebook', '--exclude-module', 'nbformat', '--exclude-module', 'PIL']
    if sys.platform == 'darwin':
        command += ['--osx-bundle-identifier', 'com.github.moritzwanzenboeck.journal-analysis-tools',
                    '--icon', str(root / 'assets' / 'app.icns')]
    command.append(str(root / 'desktop_app.py'))
    subprocess.run(command, check=True, cwd=root)
    if sys.platform == 'darwin':
        app = args.output.resolve() / f'{APP_NAME}.app'
        zip_path = args.output.resolve() / f'Journal-Analysis-Tools-macOS-{platform.machine()}.zip'
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(zip_path)], check=True)
        print(f'App: {app}')
        print(f'Download archive: {zip_path}')
    else:
        print(f'App folder: {args.output.resolve() / APP_NAME}')


if __name__ == '__main__':
    main()
