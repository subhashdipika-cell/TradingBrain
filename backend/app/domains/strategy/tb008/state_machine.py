"""
TradingBrain

TB008 - State Machine
"""

from __future__ import annotations

from enum import Enum, auto


class TB008State(Enum):
    INITIALIZED = auto()
    WAITING_FOR_REGIME = auto()
    WAITING_FOR_ENTRY = auto()
    STRUCTURE_OPEN = auto()
    ADJUSTING = auto()
    EXITING = auto()
    COMPLETED = auto()


class StateMachine:
    def __init__(self) -> None:
        self._state = TB008State.INITIALIZED

    @property
    def current_state(self) -> TB008State:
        return self._state

    def transition(self, new_state: TB008State) -> None:
        self._state = new_state

    def reset(self) -> None:
        self._state = TB008State.INITIALIZED
