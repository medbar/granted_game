from app.semantic import SemanticResolver


def scores(text: str) -> dict[str, float]:
    resolver = SemanticResolver()
    anchors, _ = resolver.resolve(text)
    return {anchor.id: anchor.score for anchor in anchors}


def test_anchor_catalog_has_exactly_one_hundred_entries() -> None:
    assert len(SemanticResolver().anchors) == 100


def test_anchor_embeddings_are_cached_in_memory() -> None:
    assert SemanticResolver().anchors is SemanticResolver().anchors


def test_semantic_backend_is_configurable_and_reported() -> None:
    resolver = SemanticResolver()
    assert resolver.backend == "char_ngram"
    assert resolver.model_name == "deterministic-multilingual-char-ngram-v1"


def test_golden_anchor_phrases() -> None:
    cases = {
        "зажги его": {"IGNITE", "FIRE"},
        "отшвырни его": {"PUSH"},
        "притяни камень ко мне": {"PULL", "STONE", "SELF"},
        "заморозь воду": {"FREEZE", "WATER"},
    }
    for phrase, expected in cases.items():
        assert expected <= scores(phrase).keys(), (phrase, scores(phrase))


def test_push_synonyms_share_the_same_anchor() -> None:
    for phrase in ("толкни", "отбрось", "отшвырни", "пни магией", "заставь отлететь"):
        assert scores(phrase).get("PUSH", 0.0) > 0.7


def test_unknown_text_is_low_coherence_but_valid() -> None:
    _, coherence = SemanticResolver().resolve("абракадабра курица великолепие")
    assert 0.05 <= coherence < 0.6


def test_logic_words_are_deterministic() -> None:
    result = scores("подожги всех врагов вокруг меня кроме меня")
    assert result["ALL"] > 0.9
    assert result["EXCEPT"] > 0.9
