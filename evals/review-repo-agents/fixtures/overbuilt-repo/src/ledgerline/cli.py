"""Command-line entry point."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog="ledgerline")
    parser.add_argument("command", choices=["reconcile"])
    parser.add_argument("export")
    parser.parse_args()
    return 0
