"""
TradingBrain

TB001 - Strategy State Machine
"""

from __future__ import annotations

from enum import Enum, auto


class TB001State(Enum):
    """
    Runtime states of the TB001 strategy.
    """

    INITIALIZED = auto()

    WAITING_FOR_MARKET = auto()

    PRE_MARKET = auto()

    WAITING_FOR_ENTRY = auto()

    OPENING_POSITION = auto()

    MANAGING_POSITION = auto()

    SHIFTING_STRIKE = auto()

    MEAN_REVERSION = auto()

    TACTICAL_MODE = auto()

    EXITING_POSITION = auto()

    POST_MARKET = auto()

    COMPLETED = auto()


class StateMachine:
    """
    TB001 strategy state machine.

    Responsible only for maintaining the
    current execution state.
    """

    def __init__(self) -> None:
        self._state = TB001State.INITIALIZED

    @property
    def current_state(self) -> TB001State:
        return self._state

    def transition(self, new_state: TB001State) -> None:
        """
        Transition to another state.
        """
        self._state = new_state

    def reset(self) -> None:
        """
        Reset the strategy lifecycle.
        """
        self._state = TB001State.INITIALIZED