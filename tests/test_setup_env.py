import py_compile
from pathlib import Path

def test_setup_env_compiles():
    script = Path(__file__).resolve().parents[1] / "scripts" / "setup_env.py"
    py_compile.compile(str(script), doraise=True)
