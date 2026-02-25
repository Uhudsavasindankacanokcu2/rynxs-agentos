"""
CLI bootstrap to reduce noisy Python/CLT cache warnings on macOS.
"""

import os
import tempfile


def _is_writable(path: str) -> bool:
    try:
        test_path = os.path.join(path, ".rynxs_write_test")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        return True
    except Exception:
        return False


def bootstrap() -> None:
    """
    Set conservative env defaults for clean CLI output.
    """
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    os.environ.setdefault("PYTHONNOUSERSITE", "1")

    tmp = os.environ.get("TMPDIR")
    if not tmp or not _is_writable(tmp):
        base = "/tmp"
        if not os.path.isdir(base):
            os.makedirs(base, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="rynxs-tmp-", dir=base)
        os.environ["TMPDIR"] = tmp
