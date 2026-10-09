"""This EXE stays installed while app payloads are updated independently."""
import importlib.util, multiprocessing, os, runpy, sys
from pathlib import Path
import runtime

if __name__=='__main__':
    multiprocessing.freeze_support()
    if sys.stdout is None:sys.stdout=open(os.devnull,'w')
    if sys.stderr is None:sys.stderr=open(os.devnull,'w')
    if '--self-test' not in sys.argv and '--payload-probe' not in sys.argv:runtime.install_launcher()
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'payload'
    data=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'AmazonVariationMonitor'
    selected=runtime.active_payload(data/'updates',base)
    sys.path.insert(0,str(selected))
    for name in ('core','updater','selftest'):
        spec=importlib.util.spec_from_file_location(name,selected/(name+'.py'))
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    runpy.run_path(str(selected/'app.py'),run_name='__main__')
