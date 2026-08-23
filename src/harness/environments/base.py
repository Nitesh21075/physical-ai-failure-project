from __future__ import annotations

from abc import ABC, abstractmethod

from harness.schemas import Action, Observation, Scenario, StepResult


class Environment(ABC):
    """Backend-neutral environment interface.

    Implementations may be Isaac Sim, a neural world model, or a test/mock
    environment. Keep the core harness independent of any backend.
    """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Stable name recorded with every experiment."""
        raise NotImplementedError

    @abstractmethod
    def reset(self, scenario: Scenario) -> Observation:
        """Reset to the scenario and return the initial observation."""
        raise NotImplementedError

    @abstractmethod
    def step(self, action: Action) -> StepResult:
        """Apply one action and return the resulting observation/result."""
        raise NotImplementedError

    @abstractmethod
    def observe(self) -> Observation:
        """Return the current observation."""
        raise NotImplementedError

    def close(self) -> None:
        """Release backend resources."""
        return None
