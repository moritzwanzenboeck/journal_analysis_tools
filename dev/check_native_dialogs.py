"""Check real macOS chooser visibility/independence and cancel only the test panels."""
from argparse import ArgumentParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile

# Runs inside the chooser process. Cocoa timers work while its native panel is
# modal; ordinary Tk after callbacks do not run consistently in that state.
_PROBE = r'''
    import ctypes
    import platform
    objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    def send(obj, name, *args):
        signature = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                     *([ctypes.c_void_p] * len(args)))
        return signature(('objc_msgSend', objc))(obj, objc.sel_registerName(name.encode()), *args)
    class Point(ctypes.Structure):
        _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_double)]
    class Size(ctypes.Structure):
        _fields_ = [('width', ctypes.c_double), ('height', ctypes.c_double)]
    class Rect(ctypes.Structure):
        _fields_ = [('origin', Point), ('size', Size)]
    def frame(obj, name):
        selector = objc.sel_registerName(name.encode())
        if platform.machine() == 'x86_64':
            result = Rect()
            call = ctypes.CFUNCTYPE(None, ctypes.POINTER(Rect), ctypes.c_void_p, ctypes.c_void_p)(
                ('objc_msgSend_stret', objc))
            call(ctypes.byref(result), obj, selector)
        else:
            call = ctypes.CFUNCTYPE(Rect, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))
            result = call(obj, selector)
        return [result.origin.x, result.origin.y, result.size.width, result.size.height]
    observed = False
    def inspect_panel():
        global observed
        if observed:
            return
        app = send(objc.objc_getClass(b'NSApplication'), 'sharedApplication')
        windows = send(app, 'windows')
        for index in range(send(windows, 'count') or 0):
            panel = send(windows, 'objectAtIndex:', index)
            if not send(panel, 'isKindOfClass:', objc.objc_getClass(b'NSOpenPanel')) or not send(panel, 'isVisible'):
                continue
            observed = True
            screens = send(objc.objc_getClass(b'NSScreen'), 'screens')
            visible = [frame(send(screens, 'objectAtIndex:', i), 'visibleFrame')
                       for i in range(send(screens, 'count') or 0)]
            metrics = dict(sheet=bool(send(panel, 'isSheet')),
                           frame=frame(panel, 'frame'), screens=visible)
            print('NATIVE_GEOMETRY ' + json.dumps(metrics), file=sys.stderr, flush=True)
            send(panel, 'cancel:', None)
            return
    core = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cocoa = ctypes.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
    core.CFAbsoluteTimeGetCurrent.restype = ctypes.c_double
    core.CFRunLoopGetMain.restype = ctypes.c_void_p
    TimerCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
    @TimerCallback
    def timer_callback(timer, context):
        inspect_panel()
    core.CFRunLoopTimerCreate.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double,
        ctypes.c_ulong, ctypes.c_long, TimerCallback, ctypes.c_void_p]
    core.CFRunLoopTimerCreate.restype = ctypes.c_void_p
    core.CFRunLoopAddTimer.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    timer = core.CFRunLoopTimerCreate(None, core.CFAbsoluteTimeGetCurrent() + 1, 0.3, 0, 0, timer_callback, None)
    for owner, name in ((core, 'kCFRunLoopCommonModes'), (cocoa, 'NSModalPanelRunLoopMode')):
        core.CFRunLoopAddTimer(core.CFRunLoopGetMain(), timer, ctypes.c_void_p.in_dll(owner, name))
'''


def probe_dialog(python, worker, mode, directory):
    marker = '    options = dict('
    if marker not in worker:
        raise ValueError('Cannot instrument the dialog worker.')
    script = worker.replace(marker, _PROBE + marker, 1)
    try:
        result = subprocess.run([str(python), '-I', '-B', '-c', script],
                                input=json.dumps(dict(mode=mode, title='Journal Tools dialog check', initialdir=str(directory))),
                                text=True, capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        raise RuntimeError('The test chooser did not open and cancel within 20 seconds.') from None
    if result.returncode or json.loads(result.stdout) != {'path': ''}:
        raise RuntimeError('Native chooser cancellation failed: ' + result.stderr)
    prefix = 'NATIVE_GEOMETRY '
    return next(json.loads(line[len(prefix):]) for line in result.stderr.splitlines() if line.startswith(prefix))


def assert_visible_and_independent(metrics):
    assert not metrics['sheet'], metrics
    x, y, width, height = metrics['frame']
    assert width > 0 and height > 0, metrics
    assert any(x >= sx - 2 and y >= sy - 2 and
               x + width <= sx + sw + 2 and y + height <= sy + sh + 2
               for sx, sy, sw, sh in metrics['screens']), metrics


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable, help='Use an app-bundled interpreter if desired')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This Cocoa geometry check requires a macOS desktop.')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.file_selectors import _NATIVE_PATH_DIALOG
    with tempfile.TemporaryDirectory(prefix='native chooser ü ') as temporary:
        for mode in ('folder', 'json'):
            metrics = probe_dialog(args.python, _NATIVE_PATH_DIALOG, mode, temporary)
            assert_visible_and_independent(metrics)
            print(mode + ': fully visible, independent panel; Cancel verified.')


if __name__ == '__main__':
    main()
