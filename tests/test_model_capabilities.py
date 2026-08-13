from lcycode.config.model_capabilities import lookup


def test_lookup_known_good_model():
    assert lookup("qwen2.5-coder:7b") == "good"


def test_lookup_known_limited_model():
    assert lookup("deepseek-coder:1.3b") == "limited"


def test_lookup_unknown_model():
    assert lookup("some-brand-new-model:9000b") == "unknown"


def test_lookup_is_case_insensitive_on_base_name():
    assert lookup("Qwen2.5-Coder:7B".lower()) == "good"


def test_lookup_newer_recommended_models():
    assert lookup("qwen3-coder:latest") == "good"
    assert lookup("glm-4.7-flash") == "good"


def test_lookup_unconfirmed_model_is_unknown_not_assumed_good():
    assert lookup("gpt-oss:20b") == "unknown"
