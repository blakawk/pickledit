from distutils.core import setup
from os.path import join, abspath, dirname
import py2exe
import sys

sys.argv.append('py2exe')

TOP = abspath(dirname(__file__))
SCRIPT = join(TOP, 'src', 'pickledit.py')
ICON = join(TOP, 'img', 'favicon.ico')

setup(
    options = {"py2exe": {"compressed": 1, "optimize": 2, "bundle_files": 1, "dll_excludes": ["mswsock.dll", "MSWSOCK.dll"]}},
    zipfile = None, 
    description = "Python pickle editor",
    windows = [{"script": SCRIPT, "icon_resources": [(0, ICON)]}],
    console = [{"script": SCRIPT, "icon_resources": [(0, ICON)]}],
)
