#!/usr/bin/env python3
"""Run a command and record stderr error lines to error_summary.log.

Usage:
    python run_with_error_summary.py [<command> [args...]]

When called without a command, the script loads a default command from
``config.yaml`` under ``error_summary.default_command``. Explicit CLI arguments
always override the configured default.

The script streams the command's output to the console while capturing any
stderr lines containing the word "error". These lines are appended to
``error_summary.log`` and a frequency summary is written at the end.

Example ``config.yaml``::

    error_summary:
      default_command: ["pytest"]
"""

import sys
import subprocess
import threading
import pathlib
import datetime
import re
from collections import Counter
from typing import List, Optional

import yaml

def stream_reader(stream, callback):
    for line in iter(stream.readline, ''):
        callback(line)
    stream.close()

def load_default_command() -> Optional[List[str]]:
    """Return default command from config.yaml if available."""
    config_path = pathlib.Path("config.yaml")
    if not config_path.exists():
        return None
    try:
        with config_path.open() as f:
            data = yaml.safe_load(f) or {}
        cmd = data.get("error_summary", {}).get("default_command")
        if isinstance(cmd, list) and all(isinstance(item, str) for item in cmd):
            return cmd
    except Exception:
        pass
    return None
def main() -> int:
    if len(sys.argv) < 2:
        default_cmd = load_default_command()
        if not default_cmd:
            print(__doc__)
            return 1
        cmd = default_cmd
    else:
        cmd = sys.argv[1:]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    logfile = pathlib.Path("error_summary.log")
    if logfile.exists():
        logfile.unlink()
    error_counter: Counter[str] = Counter()

    def handle_stdout(line: str) -> None:
        sys.stdout.write(line)

    def handle_stderr(line: str) -> None:
        sys.stderr.write(line)
        if re.search("error", line, re.IGNORECASE):
            msg = line.strip()
            error_counter[msg] += 1
            with logfile.open("a") as f:
                f.write(msg + "\n")

    threads = [
        threading.Thread(target=stream_reader, args=(proc.stdout, handle_stdout)),
        threading.Thread(target=stream_reader, args=(proc.stderr, handle_stderr)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    returncode = proc.wait()

    timestamp = datetime.datetime.now().isoformat()
    with logfile.open("a") as f:
        f.write("\nSummary generated at " + timestamp + "\n")
        if error_counter:
            for msg, count in error_counter.items():
                f.write(f"{msg} x{count}\n")
        else:
            f.write("No errors captured.\n")

    return returncode

if __name__ == "__main__":
    sys.exit(main())
