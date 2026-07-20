#!/usr/bin/env python

import subprocess
import sys
from typing import List

def run_command(command: List[str]) -> None:
    """Run a shell command and print its output."""
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {e.stderr}", file=sys.stderr)
        sys.exit(1)

def run_pytest() -> None:
    """Run pytest to execute integration tests."""
    print("Running pytest...")
    run_command(["pytest", "tests"])

def run_github_actions() -> None:
    """Trigger GitHub Actions using the gh CLI."""
    print("Triggering GitHub Actions...")
    run_command(["gh", "workflow", "run", "ci.yml"])

def main() -> None:
    """Main function to provide a menu for running tests and actions."""
    while True:
        print("\nSelect an action:")
        print("1. Run integration tests")
        print("2. Trigger GitHub Actions")
        print("3. Exit")

        choice = input("Enter your choice (1/2/3): ")

        if choice == "1":
            run_pytest()
        elif choice == "2":
            run_github_actions()
        elif choice == "3":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please select a valid option.")

if __name__ == "__main__":
    main()
```

### Explanation:

1. **run_command**: A helper function to execute shell commands and handle errors.
2. **run_pytest**: Executes `pytest` to run integration tests.
3. **run_github_actions**: Uses the `gh` CLI to trigger GitHub Actions.
4. **main**: Provides a menu for users to select actions to execute.

### Usage:

1. Ensure you have `pytest` and `gh` installed on your system.
2. Run the script using Python:
   ```bash
   python scripts/developer_tools/run_tests_and_actions.py
   ```
3. Follow the prompts to run integration tests or trigger GitHub Actions.

This script provides a simple and user-friendly interface for automating integration tests and GitHub Actions, making it easier to ensure comprehensive testing before committing code.