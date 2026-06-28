#!/usr/bin/env python
"""
Lens base class.

A lens is one analytical perspective over the civic database. Each lens runs
read-only queries and returns a list of Insight objects. Lenses never write —
persistence is the writer's job — which keeps them pure, testable, and safe to
run against a production database.

Adding a new lens is the whole extensibility story of this engine:
  1. subclass Lens
  2. implement analyze(cur) -> list[Insight]
  3. register it in registry.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from insight_engine.models import Insight


class Lens(ABC):
    #: short stable identifier, also stored on every Insight it emits
    name: str = "base"
    #: one-line human description, surfaced in the CLI and manifest
    description: str = ""

    @abstractmethod
    def analyze(self, cur) -> list[Insight]:
        """
        Run read-only queries against `cur` (a RealDictCursor) and return
        Insight objects. Must not mutate the database.
        """
        raise NotImplementedError
