from dataclasses import dataclass


@dataclass(frozen=True)
class Holding:
    code: str
    name: str
    shares: float
    cost_nav: float


@dataclass(frozen=True)
class WatchItem:
    code: str
    name: str
    category: str
    note: str
    focus: bool
