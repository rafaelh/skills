"""Tests for widgetly.render."""

from widgetly.render import render_batch, render_widget
from widgetly.schema import WidgetConfig


def test_basic_svg():
    cfg = WidgetConfig(name="box", width=80, height=60)
    svg = render_widget(cfg)
    assert 'width="80"' in svg
    assert 'height="60"' in svg
    assert "<svg" in svg


def test_label_included():
    cfg = WidgetConfig(name="lbl", width=100, height=50, label="Click")
    svg = render_widget(cfg)
    assert "<text" in svg
    assert "Click" in svg


def test_no_label_no_text_element():
    cfg = WidgetConfig(name="plain", width=100, height=50)
    svg = render_widget(cfg)
    assert "<text" not in svg


def test_batch_returns_list():
    configs = [
        WidgetConfig(name="a", width=10, height=10),
        WidgetConfig(name="b", width=20, height=20),
    ]
    results = render_batch(configs)
    assert len(results) == 2
    assert all("<svg" in r for r in results)
