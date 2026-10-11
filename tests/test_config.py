"""Settings from the environment and from ``.env`` in the working directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from matricula_mcp.config import ConfigError, load_config

VARIABLES = (
    "MATRICULA_CACHE_DIR",
    "MATRICULA_TIMEOUT",
    "MATRICULA_MIN_INTERVAL",
    "MATRICULA_SEARCH_INTERVAL",
    "MATRICULA_CONTACT",
    "MATRICULA_DOWNLOAD_DIR",
    "MATRICULA_IMAGE_ACCESS",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_nothing_is_required_and_images_are_off():
    cfg = load_config()
    assert cfg.timeout == 30.0 and cfg.min_interval == 2.0 and cfg.search_interval == 10.0
    assert cfg.cache_dir == Path.home() / ".cache" / "matricula-mcp"
    assert cfg.contact == "" and cfg.download_dir is None and cfg.image_access is False


def test_every_setting_is_read(monkeypatch, tmp_path):
    monkeypatch.setenv("MATRICULA_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("MATRICULA_TIMEOUT", "15")
    monkeypatch.setenv("MATRICULA_MIN_INTERVAL", "3")
    monkeypatch.setenv("MATRICULA_SEARCH_INTERVAL", "20")
    monkeypatch.setenv("MATRICULA_CONTACT", "me@example.org")
    monkeypatch.setenv("MATRICULA_DOWNLOAD_DIR", str(tmp_path))
    cfg = load_config()
    assert cfg.cache_dir == tmp_path / "c" and cfg.download_dir == tmp_path
    assert (cfg.timeout, cfg.min_interval, cfg.search_interval) == (15.0, 3.0, 20.0)
    assert cfg.contact == "me@example.org"


@pytest.mark.parametrize("raw", ["thirty", "0", "-5", "nan", "inf"])
def test_an_unusable_timeout_names_the_variable(monkeypatch, raw):
    monkeypatch.setenv("MATRICULA_TIMEOUT", raw)
    with pytest.raises(ConfigError, match="MATRICULA_TIMEOUT"):
        load_config()


@pytest.mark.parametrize(
    ("name", "raw", "floor"),
    [("MATRICULA_MIN_INTERVAL", "1", "2"), ("MATRICULA_SEARCH_INTERVAL", "5", "10")],
)
def test_the_intervals_have_floors(monkeypatch, name, raw, floor):
    monkeypatch.setenv(name, raw)
    with pytest.raises(ConfigError, match=f"{name} must be at least {floor}"):
        load_config()


@pytest.mark.parametrize("raw", ["me@example.org\r\nX-Evil: 1", "me (home)"])
def test_a_contact_that_could_break_the_header_is_refused(monkeypatch, raw):
    monkeypatch.setenv("MATRICULA_CONTACT", raw)
    with pytest.raises(ConfigError, match="MATRICULA_CONTACT"):
        load_config()


def test_dot_env_in_the_working_directory_is_read(tmp_path):
    (tmp_path / ".env").write_text("MATRICULA_TIMEOUT=7\n")
    assert load_config().timeout == 7.0


def test_the_environment_wins_over_dot_env(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("MATRICULA_TIMEOUT=7\n")
    monkeypatch.setenv("MATRICULA_TIMEOUT", "9")
    assert load_config().timeout == 9.0


@pytest.mark.parametrize("make", ["missing", "a file", "relative"])
def test_an_unusable_download_folder_names_the_variable(monkeypatch, tmp_path, make):
    raw = {
        "missing": str(tmp_path / "missing"),
        "a file": str(tmp_path / "file.txt"),
        "relative": "downloads",
    }[make]
    (tmp_path / "file.txt").write_text("x")
    (tmp_path / "downloads").mkdir()
    monkeypatch.setenv("MATRICULA_DOWNLOAD_DIR", raw)
    with pytest.raises(ConfigError, match="MATRICULA_DOWNLOAD_DIR"):
        load_config()


# --------------------------------------------------------------------------- #
# The image gate
# --------------------------------------------------------------------------- #
def test_image_access_is_granted_only_by_the_word_and_a_contact(monkeypatch):
    monkeypatch.setenv("MATRICULA_CONTACT", "me@example.org")
    monkeypatch.setenv("MATRICULA_IMAGE_ACCESS", "granted")
    assert load_config().image_access is True


def test_an_empty_image_setting_leaves_images_off(monkeypatch):
    monkeypatch.setenv("MATRICULA_IMAGE_ACCESS", "")
    assert load_config().image_access is False


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "enabled", "please"])
def test_any_other_value_is_refused_rather_than_read_as_yes(monkeypatch, raw):
    monkeypatch.setenv("MATRICULA_CONTACT", "me@example.org")
    monkeypatch.setenv("MATRICULA_IMAGE_ACCESS", raw)
    with pytest.raises(ConfigError, match="MATRICULA_IMAGE_ACCESS"):
        load_config()


def test_image_access_without_a_contact_is_refused(monkeypatch):
    """Access is granted to an identified client; the contact is what identifies it."""
    monkeypatch.setenv("MATRICULA_IMAGE_ACCESS", "granted")
    with pytest.raises(ConfigError, match="needs MATRICULA_CONTACT"):
        load_config()
