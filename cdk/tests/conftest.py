"""Shared CDK test bootstrap.

Individual test files import either ``from cdk.stacks...`` (needs the repo
root on ``sys.path``) or ``from stacks...`` (needs the ``cdk/`` package
directory itself) -- see issue #4929. Runs at collection time, before any
test module in this directory is imported, so both styles work without each
file repeating its own ``sys.path.insert`` boilerplate.
"""

import sys
from pathlib import Path

_CDK_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _CDK_DIR.parent

for _path in (_REPO_ROOT, _CDK_DIR):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)
