#!/usr/bin/env python
"""
Lens registry — the single place that knows which lenses exist.

To add a lens: import it and add an instance to LENSES. The runner and CLI
pick it up automatically.
"""
from __future__ import annotations

from insight_engine.lenses.base import Lens
from insight_engine.lenses.influence import InfluenceLens
from insight_engine.lenses.spending import SpendingLens
from insight_engine.lenses.topics import TopicsLens
from insight_engine.lenses.votes import VotesLens

LENSES: list[Lens] = [
    InfluenceLens(),
    SpendingLens(),
    TopicsLens(),
    VotesLens(),
]


def get_lenses(names: list[str] | None = None) -> list[Lens]:
    if not names:
        return LENSES
    wanted = {n.strip().lower() for n in names}
    return [lens for lens in LENSES if lens.name in wanted]


def lens_names() -> list[str]:
    return [lens.name for lens in LENSES]
