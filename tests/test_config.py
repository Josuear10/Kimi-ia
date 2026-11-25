from config import load_settings


def test_reads_api_key_and_serves_frontend_locally() -> None:
    settings = load_settings({"ANTHROPIC_API_KEY": "sk-test"})

    assert settings.anthropic_api_key == "sk-test"
    assert settings.serve_frontend is True
    assert settings.model == "claude-opus-5-5"


def test_empty_api_key_is_treated_as_missing() -> None:
    assert load_settings({"ANTHROPIC_API_KEY": ""}).anthropic_api_key is None


def test_frontend_is_not_served_on_vercel() -> None:
    assert load_settings({"VERCEL": "1"}).serve_frontend is False


def test_reads_supabase_settings_and_strips_trailing_slash() -> None:
    settings = load_settings(
        {"SUPABASE_URL": "https://abc.supabase.co/", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_x"}
    )

    assert settings.supabase_url == "https://abc.supabase.co"
    assert settings.supabase_publishable_key == "sb_publishable_x"
    assert settings.supabase_configured is True


def test_supabase_is_not_configured_without_both_values() -> None:
    assert load_settings({"SUPABASE_URL": "https://abc.supabase.co"}).supabase_configured is False


def test_supabase_url_pasted_with_rest_suffix_is_normalized() -> None:
    settings = load_settings({"SUPABASE_URL": "https://abc.supabase.co/rest/v1/"})
    assert settings.supabase_url == "https://abc.supabase.co"
