"""Abstract base class for prompt generation providers."""

from abc import ABC, abstractmethod
from typing import List

from prompt_generator.models import Batch, Scene


class PromptProvider(ABC):
    """Abstract base class for all prompt generation providers."""

    @abstractmethod
    def generate_batch(self, batch: Batch, instruction_text: str) -> List[Scene]:
        """Generate prompts for a single batch of scenes.

        Must return a list of Scene objects with generated_prompt populated.
        """
        pass

    @abstractmethod
    def check_availability(self) -> bool:
        """Check provider availability and model status."""
        pass
