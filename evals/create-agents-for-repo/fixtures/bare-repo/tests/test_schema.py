"""Tests for widgetly.schema."""

import pytest

from widgetly.schema import ValidationError, validate


def test_valid_minimal():
    result = validate({"name": "btn", "width": 100, "height": 40})
    assert result.name == "btn"
    assert result.width == 100
    assert result.height == 40
    assert result.fill == "#ffffff"


def test_valid_full():
    result = validate(
        {
            "name": "card",
            "width": 200,
            "height": 120,
            "fill": "#f0f0f0",
            "stroke": "#333",
            "stroke_width": 2.0,
            "border_radius": 8.0,
            "label": "Hello",
        }
    )
    assert result.label == "Hello"
    assert result.border_radius == 8.0


def test_missing_name():
    with pytest.raises(ValidationError, match="missing required fields"):
        validate({"width": 100, "height": 40})


def test_negative_width():
    with pytest.raises(ValidationError, match="positive integer"):
        validate({"name": "x", "width": -1, "height": 40})


def test_empty_name():
    with pytest.raises(ValidationError, match="non-empty string"):
        validate({"name": "  ", "width": 100, "height": 40})
