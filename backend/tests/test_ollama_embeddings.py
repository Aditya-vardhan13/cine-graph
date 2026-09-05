from app.services.ollama_embeddings import OllamaEmbeddingProfile


def test_qwen_query_instruction_is_explicit_and_does_not_rewrite_the_question() -> None:
    question = "How does Get Out turn social discomfort into story pressure?"

    rendered = OllamaEmbeddingProfile().query_input(question)

    assert rendered.endswith(f"Query: {question}")
    assert "source-backed passage" in rendered
