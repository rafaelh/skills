"""Name normalisation shared by the importers."""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")
_SUFFIX = re.compile(r"\s*\b(?:ltd|limited|inc|plc|gmbh)\.?$", re.IGNORECASE)


def normalize_name(name):
    collapsed = _WHITESPACE.sub(" ", name).strip()
    return _SUFFIX.sub("", collapsed).strip().title()
