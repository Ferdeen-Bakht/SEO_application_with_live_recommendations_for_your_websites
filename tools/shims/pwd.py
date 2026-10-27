"""Windows stand-in for the Unix-only `pwd` module, used by SearXNG only to word an error message."""
import getpass
import os
from types import SimpleNamespace

if not hasattr(os, "getuid"):
    os.getuid = lambda: 0


def getpwuid(_uid):
    return SimpleNamespace(pw_name=getpass.getuser())
