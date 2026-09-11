from app.prompt import parse_label


def test_parses_strict_json():
    assert parse_label('{"label": "bug"}') == "bug"


def test_parses_json_with_surrounding_text():
    assert parse_label('Sure, here you go: {"label": "security"} — hope that helps!') == "security"


def test_parses_bare_word_fallback():
    assert parse_label("I'd classify this as a question.") == "question"


def test_rejects_invalid_label():
    assert parse_label('{"label": "not_a_real_label"}') is None


def test_rejects_empty_output():
    assert parse_label("") is None


def test_case_insensitive():
    assert parse_label('{"label": "BUG"}') == "bug"
