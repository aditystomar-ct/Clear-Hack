"""Embeddings, clause matching, and rule matching."""

import math
import re
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from .config import (
    EMBED_MODEL, EMBED_MODEL_FALLBACK, MATCH_THRESHOLD_STRONG,
    MATCH_THRESHOLD_PARTIAL, RULE_MATCH_THRESHOLD, KEYWORD_BOOST,
)
from .models import Clause, Rule


_model: Optional[SentenceTransformer] = None
_active_model_name: str = ""


def get_model() -> SentenceTransformer:
    global _model, _active_model_name
    if _model is None:
        try:
            print(f"  Loading embedding model: {EMBED_MODEL}...")
            _model = SentenceTransformer(EMBED_MODEL)
            _active_model_name = EMBED_MODEL
        except Exception as e:
            print(f"  Could not load {EMBED_MODEL}: {e}")
            print(f"  Falling back to {EMBED_MODEL_FALLBACK}...")
            _model = SentenceTransformer(EMBED_MODEL_FALLBACK)
            _active_model_name = EMBED_MODEL_FALLBACK
    return _model


def get_active_model_name() -> str:
    get_model()
    return _active_model_name


def embed_texts(texts: list[str]) -> np.ndarray:
    return get_model().encode(texts, show_progress_bar=False, convert_to_numpy=True)


def match_clauses(
    input_clauses: list[Clause],
    playbook_clauses: list[Clause],
) -> list[tuple[Clause, Clause, float, str]]:
    """For each input clause, find the best-matching playbook clause."""
    print("  Computing embeddings...")
    inp_emb = embed_texts([c.text for c in input_clauses])
    pb_emb = embed_texts([c.text for c in playbook_clauses])
    sim_matrix = cosine_similarity(inp_emb, pb_emb)

    results = []
    for i, ic in enumerate(input_clauses):
        j = int(np.argmax(sim_matrix[i]))
        score = float(sim_matrix[i][j])
        if score >= MATCH_THRESHOLD_STRONG:
            mt = "strong"
        elif score >= MATCH_THRESHOLD_PARTIAL:
            mt = "partial"
        else:
            mt = "new_clause"
        results.append((ic, playbook_clauses[j], score, mt))
    return results


def match_rules(clause: Clause, rules: list[Rule]) -> list[tuple[Rule, float]]:
    """Find applicable rules for a clause (semantic similarity + keyword boost)."""
    clause_emb = embed_texts([clause.text])
    rule_texts = [f"{r.clause}: {r.subclause}" for r in rules]
    rule_emb = embed_texts(rule_texts)
    sims = cosine_similarity(clause_emb, rule_emb)[0]

    clause_low = clause.text.lower()
    matched: list[tuple[Rule, float]] = []
    for j, rule in enumerate(rules):
        score = float(sims[j])
        rule_keywords = set(re.findall(r"[a-z]{4,}", rule.clause.lower()))
        clause_words = set(re.findall(r"[a-z]{4,}", clause_low))
        overlap = rule_keywords & clause_words
        if len(overlap) >= 2:
            score = min(score + KEYWORD_BOOST, 1.0)
        if score >= RULE_MATCH_THRESHOLD:
            matched.append((rule, score))

    matched.sort(key=lambda x: -x[1])
    return matched[:5]


def apply_rule_specificity(
    all_clause_rules: list[list[tuple[Rule, float]]],
) -> list[list[tuple[Rule, float]]]:
    """
    Penalize broad rules that match too many clauses.
    specificity = 1.0 / log(1 + num_clauses_matched)
    """
    rule_trigger_count: dict[str, int] = {}
    for clause_rules in all_clause_rules:
        for rule, _ in clause_rules:
            rule_trigger_count[rule.rule_id] = rule_trigger_count.get(rule.rule_id, 0) + 1

    adjusted: list[list[tuple[Rule, float]]] = []
    for clause_rules in all_clause_rules:
        new_rules: list[tuple[Rule, float]] = []
        for rule, score in clause_rules:
            count = rule_trigger_count[rule.rule_id]
            specificity = 1.0 / math.log(1 + count)
            adjusted_score = score * specificity
            if adjusted_score >= RULE_MATCH_THRESHOLD:
                new_rules.append((rule, adjusted_score))
        new_rules.sort(key=lambda x: -x[1])
        adjusted.append(new_rules[:5])
    return adjusted
