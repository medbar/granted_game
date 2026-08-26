from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from .config import anchors_config, spell_settings
from .models import AnchorScore


TOKEN_RE = re.compile(r"[a-zа-я0-9-]+", re.IGNORECASE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("ё", "е")
    return " ".join(TOKEN_RE.findall(text))


def char_vector(text: str) -> Counter[str]:
    padded = f"  {normalize(text)}  "
    vector: Counter[str] = Counter()
    for width in (2, 3, 4, 5):
        vector.update(padded[index : index + width] for index in range(len(padded) - width + 1))
    return vector


def cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = left.keys() & right.keys()
    numerator = sum(left[key] * right[key] for key in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def chunks(text: str) -> list[str]:
    normalized = normalize(text)
    tokens = normalized.split()
    values = {normalized}
    values.update(filter(None, re.split(r"[,;.!?]+|\b(?:и|но|затем)\b", text.lower())))
    for width in range(1, min(5, len(tokens) + 1)):
        for start in range(len(tokens) - width + 1):
            values.add(" ".join(tokens[start : start + width]))
    return [normalize(value) for value in values if normalize(value)]


@dataclass(frozen=True)
class Anchor:
    id: str
    family: str
    name: str
    phrases: tuple[str, ...]
    threshold: float
    weight: float
    mapping: dict[str, float]
    vectors: tuple[Counter[str], ...]


class SemanticResolver:
    """A deterministic local embedding model based on multilingual character n-grams.

    Anchor phrases provide the semantic neighbourhood (including slang and synonyms),
    while n-gram vectors make inflected Russian forms behave smoothly. The interface is
    intentionally replaceable by SentenceTransformers without changing the REST contract.
    """

    def __init__(self) -> None:
        self.settings = spell_settings()
        self.anchors = tuple(self._make_anchor(item) for item in anchors_config()["anchors"])

    @staticmethod
    def _make_anchor(item: dict[str, Any]) -> Anchor:
        phrases = tuple({item["name"], *item.get("phrases", [])})
        return Anchor(
            id=item["id"],
            family=item["family"],
            name=item["name"],
            phrases=phrases,
            threshold=float(item.get("threshold", 0.28)),
            weight=float(item.get("weight", 1.0)),
            mapping=item.get("mapping", {}),
            vectors=tuple(char_vector(phrase) for phrase in phrases),
        )

    def resolve(self, text: str) -> tuple[list[AnchorScore], float]:
        normalized = normalize(text)
        phrase_chunks = chunks(text)
        query_vectors = tuple(char_vector(value) for value in phrase_chunks)
        by_family: dict[str, list[AnchorScore]] = defaultdict(list)

        for anchor in self.anchors:
            similarity = max(
                cosine(query, candidate)
                for query in query_vectors
                for candidate in anchor.vectors
            )
            for phrase in anchor.phrases:
                candidate = normalize(phrase)
                if len(candidate) >= 3 and re.search(rf"(?:^| )({re.escape(candidate)})(?: |$)", normalized):
                    similarity = max(similarity, 0.98)
            activation = max(0.0, (similarity - anchor.threshold) / (1.0 - anchor.threshold))
            activation = min(1.0, activation * anchor.weight)
            if activation > 0.035:
                by_family[anchor.family].append(
                    AnchorScore(id=anchor.id, score=round(activation, 4), family=anchor.family)
                )

        self._apply_logic_words(normalized, by_family)
        self._apply_implications(by_family)
        top_k = self.settings["top_k"]
        selected: list[AnchorScore] = []
        for family, scores in by_family.items():
            scores.sort(key=lambda item: (-item.score, item.id))
            selected.extend(scores[: int(top_k.get(family, 2))])
        selected.sort(key=lambda item: (-item.score, item.id))

        meaningful = [score.score for score in selected if score.family not in {"logic", "timing"}]
        if not meaningful:
            coherence = 0.08
        else:
            peak = meaningful[0]
            support = sum(meaningful[:4]) / min(4, len(meaningful))
            coherence = min(1.0, 0.72 * peak + 0.28 * support)
        return selected, round(max(0.08, coherence), 4)

    @staticmethod
    def _apply_logic_words(text: str, by_family: dict[str, list[AnchorScore]]) -> None:
        patterns = {
            "NOT": (r"\b(?:не|без)\b", 0.95),
            "EXCEPT": (r"\bкроме\b", 1.0),
            "ONLY": (r"\bтолько\b", 1.0),
            "ALL": (r"\b(?:все|всех|всем|все вокруг)\b", 1.0),
            "ONE": (r"\b(?:один|одного|одну)\b", 1.0),
        }
        for anchor_id, (pattern, score) in patterns.items():
            if re.search(pattern, text):
                by_family["logic"] = [
                    item for item in by_family["logic"] if item.id != anchor_id
                ]
                by_family["logic"].append(
                    AnchorScore(id=anchor_id, score=score, family="logic")
                )

    def _apply_implications(self, by_family: dict[str, list[AnchorScore]]) -> None:
        current = {
            score.id: score
            for family_scores in by_family.values()
            for score in family_scores
        }
        anchor_by_id = {anchor.id: anchor for anchor in self.anchors}
        for source_id, targets in self.settings.get("anchor_implications", {}).items():
            source = current.get(source_id)
            if not source:
                continue
            for target_id, multiplier in targets.items():
                target_anchor = anchor_by_id[target_id]
                implied_score = round(source.score * float(multiplier), 4)
                existing = current.get(target_id)
                if existing and existing.score >= implied_score:
                    continue
                if existing:
                    by_family[existing.family].remove(existing)
                implied = AnchorScore(
                    id=target_id,
                    score=implied_score,
                    family=target_anchor.family,
                )
                by_family[target_anchor.family].append(implied)
                current[target_id] = implied

    def anchor_details(self) -> list[dict[str, Any]]:
        return [
            {
                "id": anchor.id,
                "family": anchor.family,
                "canonical_name": anchor.name,
                "threshold": anchor.threshold,
            }
            for anchor in self.anchors
        ]
