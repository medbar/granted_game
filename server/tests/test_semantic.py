from unittest.mock import Mock, patch

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


def test_aitunnel_backend_batches_and_uses_remote_embeddings(monkeypatch) -> None:
    monkeypatch.setenv("GRANTED_SEMANTIC_BACKEND", "aitunnel")
    monkeypatch.setenv("AITUNNEL_API_KEY", "test-key")
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = lambda: {
        "data": [
            {"index": index, "embedding": [1.0, float(index % 2)]}
            for index in range(len(response.request_payload["input"]))
        ]
    }

    def fake_post(*_args, **kwargs):
        response.request_payload = kwargs["json"]
        return response

    client = Mock()
    client.post.side_effect = fake_post
    with patch("app.semantic.httpx.Client", return_value=client):
        resolver = SemanticResolver()
        assert resolver.backend == "aitunnel"
        assert resolver.model_name == "pplx-embed-v1-0.6b"
        resolver.resolve("толкни врага")

    assert client.post.call_count >= 2
    assert client.post.call_args_list[0].kwargs["headers"] == {
        "Authorization": "Bearer test-key"
    }
    assert len(client.post.call_args_list[0].kwargs["json"]["input"]) == 128
    assert client.post.call_args_list[-1].kwargs["json"]["input"]


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


def test_kill_phrase_activates_destroy_anchor() -> None:
    assert scores("убей врага").get("DESTROY", 0.0) > 0.9


def test_unknown_text_is_low_coherence_but_valid() -> None:
    _, coherence = SemanticResolver().resolve("абракадабра курица великолепие")
    assert 0.05 <= coherence < 0.6


def test_logic_words_are_deterministic() -> None:
    result = scores("подожги всех врагов вокруг меня кроме меня")
    assert result["ALL"] > 0.9
    assert result["EXCEPT"] > 0.9
