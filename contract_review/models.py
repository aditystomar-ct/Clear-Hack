"""Data classes for the review pipeline."""

from dataclasses import dataclass


@dataclass
class Clause:
    id: str
    text: str
    section: str = ""
    source: str = ""       # "input" or "playbook"
    start_index: int = 0   # Google Docs character offset (for anchoring)
    end_index: int = 0
    raw_text: str = ""     # Original paragraph text from Google Doc


@dataclass
class Rule:
    rule_id: str
    source: str       # "legal" or "infosec"
    clause: str
    subclause: str
    risk: str
    response: str
