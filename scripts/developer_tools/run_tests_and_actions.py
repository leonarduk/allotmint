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
