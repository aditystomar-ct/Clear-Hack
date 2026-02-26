#!/usr/bin/env python3
"""
DPA Contract Review Tool — CLI entry point.

Usage:
    python main.py <input_doc_url_or_docx_path> [--playbook <path_or_url>]

Compares incoming DPA against ClearTax standard using Claude.
"""

import sys


def main():
    import argparse

    parser = argparse.ArgumentParser(description="DPA Contract Review Tool")
    parser.add_argument("input", help="Input DPA: .docx file path or Google Doc URL/ID")
    parser.add_argument("--playbook", default=None, help="Playbook: .docx/.md path or Google Doc URL/ID")
    parser.add_argument("--reviewer", default="", help="Reviewer name")
    args = parser.parse_args()

    from contract_review.pipeline import run_pipeline

    result = run_pipeline(
        input_source=args.input,
        playbook_source=args.playbook,
        reviewer=args.reviewer,
    )

    print(f"\nReview ID: #{result['review_id']}")


if __name__ == "__main__":
    main()
