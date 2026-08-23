from __future__ import annotations

from pathlib import Path

import pytest

from toolkit import retry, text
from toolkit.paths import ensure_dir, newest, relative_to_root
from toolkit.retry import with_retry
from toolkit.text import collapse_whitespace, slugify, title_words, truncate


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """The backoff seam is stubbed so the retry tests do not actually wait."""
    slept: list[float] = []
    monkeypatch.setattr(retry, "_sleep", slept.append)
    return slept


def test_returns_the_first_success_without_sleeping(no_real_sleep):
    assert with_retry(lambda: "ok") == "ok"
    assert no_real_sleep == []


def test_retries_until_it_succeeds(no_real_sleep):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("boom")
        return "ok"

    assert with_retry(flaky) == "ok"
    assert calls["n"] == 3
    assert no_real_sleep == [0.5, 1.0]


def test_reraises_after_the_last_attempt(no_real_sleep):
    def always_fails():
        raise OSError("boom")

    with pytest.raises(OSError, match="boom"):
        with_retry(always_fails, attempts=2)
    assert no_real_sleep == [0.5]


def test_an_unlisted_exception_is_not_retried(no_real_sleep):
    def wrong_error():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        with_retry(wrong_error)
    assert no_real_sleep == []


def test_zero_attempts_is_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        with_retry(lambda: "ok", attempts=0)


def test_ensure_dir_is_idempotent(tmp_path: Path):
    target = tmp_path / "a" / "b"
    assert ensure_dir(target) == target
    assert ensure_dir(target).is_dir()


def test_relative_to_root_strips_the_root(tmp_path: Path):
    inner = ensure_dir(tmp_path / "pkg" / "mod")
    assert relative_to_root(inner, tmp_path) == Path("pkg/mod")


def test_relative_to_root_leaves_outside_paths_alone(tmp_path: Path):
    outside = tmp_path.parent / "elsewhere"
    assert relative_to_root(outside, tmp_path) == outside


def test_newest_of_nothing_is_none():
    assert newest([]) is None


def test_newest_ignores_paths_that_do_not_exist(tmp_path: Path):
    real = tmp_path / "real.txt"
    real.write_text("x")
    assert newest([tmp_path / "ghost.txt", real]) == real


def test_collapse_whitespace():
    assert collapse_whitespace("  a \n\t b  ") == "a b"


def test_slugify_folds_accents_and_punctuation():
    assert slugify("Crème Brûlée, please!") == "creme-brulee-please"


def test_truncate_leaves_short_text_alone():
    assert truncate("abc", 10) == "abc"


def test_truncate_marks_the_cut():
    assert truncate("abcdefgh", 5) == "ab..."


def test_truncate_rejects_a_limit_with_no_room():
    with pytest.raises(ValueError, match="room for the suffix"):
        truncate("abcdefgh", 2)


def test_title_words_collapses_and_capitalises():
    assert title_words("  the   quick brown  ") == ["The", "Quick", "Brown"]


def test_title_words_of_blank_text_is_empty():
    assert title_words("   ") == []


def test_module_exports_stay_importable():
    assert callable(text.slugify)
