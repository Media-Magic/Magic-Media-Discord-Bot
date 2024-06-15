import importlib
import inspect
import logging
import pkgutil
from typing import Generator, NoReturn

from mediamagic import exts

logger = logging.getLogger(__name__)


def unqualify(name: str) -> str:
    """Returns an unqualified name given qualified module/package name"""
    return name.rsplit(".", maxsplit=1)[-1]


def on_error(name: str) -> NoReturn:
    """Raises import error on error in extension"""
    raise ImportError(name=name)


def walk_extensions() -> Generator[str, None, None]:
    """Yeilds extension names from exts subpackage"""

    for pkg in pkgutil.walk_packages(
        exts.__path__, prefix=f"{exts.__name__}.", onerror=on_error
    ):
        if unqualify(pkg.name).startswith == "_":
            continue
        imported = importlib.import_module(pkg.name)
        if not inspect.isfunction(getattr(imported, "setup", None)):
            logger.warn(f"{pkg.name} doesn't implement setup function. Skipping it!")
            continue

        yield pkg.name
