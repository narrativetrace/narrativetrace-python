# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Scores the naming clarity of a trace tree across five weighted dimensions.

``ClarityAnalyzer`` — the canonical scoring engine. Dimensions and weights: method
names 0.30, class names 0.20, parameter names 0.25, structural 0.15, cohesion 0.10. Structural
penalises >4 parameters (0.10 each) and call depth >5 (0.05 each). Issues are score-band
classified, deduplicated by ``category|element`` with summed occurrences, and ranked by impact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from narrativetrace.tree_walk import TreeWalk
from narrativetrace_clarity import scorers
from narrativetrace_clarity.models import ClarityIssue, ClarityResult, Severity
from narrativetrace_clarity.tokenizer import tokenize
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

if TYPE_CHECKING:
    from narrativetrace.nodes import TraceNode
    from narrativetrace.tree import TraceTree

_METHOD_WEIGHT = 0.30
_CLASS_WEIGHT = 0.20
_PARAM_WEIGHT = 0.25
_STRUCTURAL_WEIGHT = 0.15
_COHESION_WEIGHT = 0.10

_HIGH_SEVERITY_THRESHOLD = 0.20
_MEDIUM_SEVERITY_THRESHOLD = 0.50


def analyze(tree: TraceTree, vocabulary: DomainVocabulary = EMPTY) -> ClarityResult:
    """Analyzes one trace tree, producing weighted scores plus ranked issues.

    ``vocabulary`` is the project's committed glossary vocabulary (ADR-012), which extends every
    built-in dictionary without overriding any of them. Omit it to score with the built-in
    dictionaries alone — what a project with no glossary gets.
    """
    nodes = _flatten(tree.roots)

    method_score = _average_method_score(nodes, vocabulary)
    class_score = _average_class_score(nodes, vocabulary)
    param_score = _average_param_score(nodes, vocabulary)
    structural_score = _structural_factor(nodes, tree)
    cohesion_score = _cohesion_score(nodes)

    overall = (
        method_score * _METHOD_WEIGHT
        + class_score * _CLASS_WEIGHT
        + param_score * _PARAM_WEIGHT
        + structural_score * _STRUCTURAL_WEIGHT
        + cohesion_score * _COHESION_WEIGHT
    )
    issues = _collect_and_deduplicate_issues(nodes, vocabulary)
    return ClarityResult(
        overall, method_score, class_score, param_score, structural_score, cohesion_score, issues
    )


def _average_method_score(nodes: list[TraceNode], vocabulary: DomainVocabulary) -> float:
    if not nodes:
        return 0.0
    return sum(scorers.score_method_name(n.signature.method_name, vocabulary) for n in nodes) / len(
        nodes
    )


def _average_class_score(nodes: list[TraceNode], vocabulary: DomainVocabulary) -> float:
    unique = list(dict.fromkeys(n.signature.class_name for n in nodes))
    if not unique:
        return 0.0
    return sum(scorers.score_class_name(name, vocabulary) for name in unique) / len(unique)


def _average_param_score(nodes: list[TraceNode], vocabulary: DomainVocabulary) -> float:
    params = [p for n in nodes for p in n.signature.parameters]
    if not params:
        return 1.0
    return sum(scorers.score_parameter_name(p.name, vocabulary) for p in params) / len(params)


def _structural_factor(nodes: list[TraceNode], tree: TraceTree) -> float:
    max_params = max((len(n.signature.parameters) for n in nodes), default=0)
    depth = _max_depth(tree.roots, 1)
    penalty = 0.0
    if max_params > 4:
        penalty += 0.1 * (max_params - 4)
    if depth > 5:
        penalty += 0.05 * (depth - 5)
    return max(0.0, 1.0 - penalty)


def _cohesion_score(nodes: list[TraceNode]) -> float:
    if not nodes:
        return 0.7
    class_methods: dict[str, list[str]] = {}
    for node in nodes:
        class_methods.setdefault(node.signature.class_name, []).append(node.signature.method_name)
    return scorers.score_cohesion_trace(class_methods)


def _max_depth(nodes: list[TraceNode], current_depth: int, walk: TreeWalk | None = None) -> int:
    walk = walk if walk is not None else TreeWalk()
    if not nodes:
        return current_depth - 1
    depths = []
    for node in nodes:
        if walk.stop_reason(node) is not None:
            depths.append(current_depth)
            continue
        walk.enter(node)
        try:
            depths.append(_max_depth(node.children, current_depth + 1, walk))
        finally:
            walk.exit(node)
    return max(depths)


def _classify_severity(score: float) -> Severity:
    if score <= _HIGH_SEVERITY_THRESHOLD:
        return Severity.HIGH
    if score <= _MEDIUM_SEVERITY_THRESHOLD:
        return Severity.MEDIUM
    return Severity.LOW


def _collect_and_deduplicate_issues(
    nodes: list[TraceNode], vocabulary: DomainVocabulary
) -> list[ClarityIssue]:
    raw: list[ClarityIssue] = []
    raw.extend(_find_method_name_issues(nodes, vocabulary))
    raw.extend(_find_class_name_issues(nodes, vocabulary))
    raw.extend(_find_param_name_issues(nodes, vocabulary))
    raw.extend(_find_collocation_issues(nodes))
    return _deduplicate_and_rank(raw)


def _deduplicate_and_rank(issues: list[ClarityIssue]) -> list[ClarityIssue]:
    grouped: dict[str, list[ClarityIssue]] = {}
    for issue in issues:
        grouped.setdefault(f"{issue.category}|{issue.element}", []).append(issue)
    merged = [group[0].with_occurrences(len(group)) for group in grouped.values()]
    return sorted(merged, key=lambda i: i.impact_score, reverse=True)


def _issue(category: str, element: str, suggestion: str, severity: Severity) -> ClarityIssue:
    return ClarityIssue(category, element, suggestion, severity, 1, float(severity.weight))


def _find_method_name_issues(
    nodes: list[TraceNode], vocabulary: DomainVocabulary
) -> list[ClarityIssue]:
    issues = []
    for node in nodes:
        sig = node.signature
        score = scorers.score_method_name(sig.method_name, vocabulary)
        if score < _MEDIUM_SEVERITY_THRESHOLD:
            issues.append(
                _issue(
                    "method-name",
                    f"{sig.class_name}.{sig.method_name}",
                    "Use a domain-specific verb+noun (e.g., calculateTotal, reserveInventory)",
                    _classify_severity(score),
                )
            )
    return issues


def _find_class_name_issues(
    nodes: list[TraceNode], vocabulary: DomainVocabulary
) -> list[ClarityIssue]:
    issues = []
    seen: set[str] = set()
    for node in nodes:
        class_name = node.signature.class_name
        if class_name in seen:
            continue
        seen.add(class_name)
        score = scorers.score_class_name(class_name, vocabulary)
        if score < _MEDIUM_SEVERITY_THRESHOLD:
            issues.append(
                _issue(
                    "class-name",
                    class_name,
                    "Use a domain-specific name or a recognized pattern suffix "
                    "(e.g., OrderService, PaymentGateway)",
                    _classify_severity(score),
                )
            )
    return issues


def _find_param_name_issues(
    nodes: list[TraceNode], vocabulary: DomainVocabulary
) -> list[ClarityIssue]:
    issues = []
    for node in nodes:
        for param in node.signature.parameters:
            score = scorers.score_parameter_name(param.name, vocabulary)
            if score < _MEDIUM_SEVERITY_THRESHOLD:
                issues.append(
                    _issue(
                        "param-name",
                        param.name,
                        "Use a domain-specific name (e.g., customerId, orderAmount)",
                        _classify_severity(score),
                    )
                )
    return issues


def _find_collocation_issues(nodes: list[TraceNode]) -> list[ClarityIssue]:
    issues = []
    for node in nodes:
        sig = node.signature
        tokens = tokenize(sig.method_name)
        if len(tokens) < 2:
            continue
        verb = tokens[0].lower()
        noun = tokens[-1].lower()
        preferred = scorers.preferred_verbs(noun)
        if not preferred or verb in preferred:
            continue
        capital_noun = noun[0].upper() + noun[1:]
        suggestion = ", ".join(f"{v}{capital_noun}" for v in sorted(preferred))
        issues.append(
            _issue(
                "collocation",
                f"{sig.class_name}.{sig.method_name}",
                f"Consider: {suggestion}",
                Severity.LOW,
            )
        )
    return issues


def _flatten(nodes: list[TraceNode], walk: TreeWalk | None = None) -> list[TraceNode]:
    walk = walk if walk is not None else TreeWalk()
    result: list[TraceNode] = []
    for node in nodes:
        result.append(node)
        if walk.stop_reason(node) is None:
            walk.enter(node)
            try:
                result.extend(_flatten(node.children, walk))
            finally:
                walk.exit(node)
    return result
