from __future__ import annotations

import json

import pytest

from neocortex.config import (
    _ENC_PREFIX,
    _decrypt,
    _encrypt,
    load_config,
    load_profile,
    save_config,
    save_profile,
    get_data_dir,
    get_notes_dir,
)
from neocortex.i18n import t
from neocortex.llm import create_provider
from neocortex.llm.anthropic import AnthropicProvider
from neocortex.llm.google import GoogleProvider
from neocortex.llm.openai_compat import OpenAICompatProvider
from neocortex.models import (
    AppConfig,
    Language,
    Persona,
    Profile,
    ProviderType,
    Role,
    Skills,
)


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)


# ── Config roundtrip ──


class TestConfigRoundtrip:
    def test_save_and_load_preserves_values(self):
        cfg = AppConfig(
            provider=ProviderType.OPENAI,
            api_key="sk-test-key-12345",
            model="gpt-4o",
        )
        save_config(cfg)
        loaded = load_config()
        assert loaded.provider == ProviderType.OPENAI
        assert loaded.api_key == "sk-test-key-12345"
        assert loaded.model == "gpt-4o"

    def test_api_key_stored_encrypted(self, tmp_path):
        cfg = AppConfig(provider=ProviderType.OPENAI, api_key="sk-secret")
        save_config(cfg)
        raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert raw["api_key"].startswith(_ENC_PREFIX)
        assert "sk-secret" not in raw["api_key"]

    def test_api_key_decrypted_on_load(self):
        cfg = AppConfig(provider=ProviderType.OPENAI, api_key="sk-roundtrip")
        save_config(cfg)
        loaded = load_config()
        assert loaded.api_key == "sk-roundtrip"

    def test_no_api_key(self):
        cfg = AppConfig(provider=ProviderType.CLAUDE)
        save_config(cfg)
        loaded = load_config()
        assert loaded.provider == ProviderType.CLAUDE
        assert loaded.api_key is None

    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "my-super-secret-key"
        encrypted = _encrypt(plaintext)
        assert encrypted.startswith(_ENC_PREFIX)
        assert _decrypt(encrypted) == plaintext


# ── Profile roundtrip ──


class TestProfileRoundtrip:
    def test_save_and_load_preserves_values(self):
        profile = Profile(
            persona=Persona(role=Role.BACKEND, language=Language.ZH),
            skills=Skills(languages={}),
        )
        save_profile(profile)
        loaded = load_profile()
        assert loaded.persona.role == Role.BACKEND
        assert loaded.persona.language == Language.ZH

    def test_empty_profile(self):
        profile = Profile()
        save_profile(profile)
        loaded = load_profile()
        assert loaded.persona.role is None
        assert loaded.skills.languages == {}


# ── Directory creation ──


class TestDirectories:
    def test_get_data_dir_creates_directory(self, tmp_path, monkeypatch):
        target = tmp_path / "custom_data"
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: _ensure_dir(target))
        d = get_data_dir()
        assert d.exists()
        assert d.is_dir()

    def test_get_notes_dir_creates_directory(self, tmp_path, monkeypatch):
        # With no config file, get_notes_dir falls back to ~/Documents/Neocortex
        monkeypatch.setattr("neocortex.config._config_path", lambda: tmp_path / "nonexistent.json")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        notes = get_notes_dir()
        assert notes.exists()
        assert notes.is_dir()
        assert notes == tmp_path / "Documents" / "Neocortex"

    def test_get_notes_dir_uses_config(self, tmp_path, monkeypatch):
        # When config has a custom notes_dir, use it
        import json
        custom_dir = tmp_path / "my_notes"
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "output_settings": {"notes_dir": str(custom_dir)}
        }), encoding="utf-8")
        monkeypatch.setattr("neocortex.config._config_path", lambda: config_file)
        notes = get_notes_dir()
        assert notes.exists()
        assert notes.is_dir()
        assert notes == custom_dir


def _ensure_dir(p):
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── LLM factory ──


class TestCreateProvider:
    def test_claude_provider(self):
        cfg = AppConfig(provider=ProviderType.CLAUDE, api_key="sk-ant-test")
        provider = create_provider(cfg)
        assert isinstance(provider, AnthropicProvider)

    def test_openai_provider(self):
        cfg = AppConfig(provider=ProviderType.OPENAI, api_key="sk-openai-test")
        provider = create_provider(cfg)
        assert isinstance(provider, OpenAICompatProvider)

    def test_gemini_provider(self):
        cfg = AppConfig(provider=ProviderType.GEMINI, api_key="gemini-key-test")
        provider = create_provider(cfg)
        assert isinstance(provider, GoogleProvider)

    def test_openai_compat_provider(self):
        cfg = AppConfig(
            provider=ProviderType.OPENAI_COMPAT,
            api_key="key-test",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
        )
        provider = create_provider(cfg)
        assert isinstance(provider, OpenAICompatProvider)

    def test_no_provider_raises(self):
        cfg = AppConfig()
        with pytest.raises(ValueError, match="No LLM provider configured"):
            create_provider(cfg)

    def test_no_api_key_raises(self):
        cfg = AppConfig(provider=ProviderType.CLAUDE)
        with pytest.raises(ValueError, match="No API key configured"):
            create_provider(cfg)

    def test_openai_compat_no_base_url_raises(self):
        cfg = AppConfig(
            provider=ProviderType.OPENAI_COMPAT,
            api_key="key-test",
            model="some-model",
        )
        with pytest.raises(ValueError, match="base_url is required"):
            create_provider(cfg)

    def test_openai_compat_no_model_raises(self):
        cfg = AppConfig(
            provider=ProviderType.OPENAI_COMPAT,
            api_key="key-test",
            base_url="https://example.com/v1",
        )
        with pytest.raises(ValueError, match="model is required"):
            create_provider(cfg)


# ── i18n ──


class TestI18n:
    def test_english_string(self):
        assert t("done", Language.EN) == "Done!"

    def test_chinese_string(self):
        assert t("done", Language.ZH) == "完成！"

    def test_format_kwargs(self):
        result = t("scan_not_found", Language.EN, path="/tmp/foo")
        assert result == "Project path not found: /tmp/foo"

    def test_format_kwargs_zh(self):
        result = t("scan_not_found", Language.ZH, path="/tmp/bar")
        assert result == "项目路径不存在：/tmp/bar"

    def test_missing_key_returns_key(self):
        assert t("this_key_does_not_exist", Language.EN) == "this_key_does_not_exist"

    def test_missing_key_returns_key_zh(self):
        assert t("nonexistent_key_abc", Language.ZH) == "nonexistent_key_abc"
