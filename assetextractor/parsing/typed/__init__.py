import importlib
import pkgutil
from pathlib import Path

for _finder, _modname, _ispkg in pkgutil.iter_modules([str(Path(__file__).parent)]):
    importlib.import_module(f"{__name__}.{_modname}")
