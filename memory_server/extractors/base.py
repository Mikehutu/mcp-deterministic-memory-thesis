"""
Base extractor interface for entity and fact extraction.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from ..models import Entity, Fact


class BaseExtractor(ABC):
    """
    Abstract base class for data extractors.

    Extractors are responsible for:
    1. Recognizing patterns in raw data
    2. Extracting named entities (places, times, metrics)
    3. Creating structured facts (subject-predicate-object triples)
    """

    def __init__(self):
        self._warnings: List[str] = []

    @property
    @abstractmethod
    def source_name(self) -> str:
        """The data source this extractor handles."""
        pass

    @abstractmethod
    def can_handle(self, source: str, content: Dict[str, Any]) -> bool:
        """
        Check if this extractor can handle the given data.

        Args:
            source: The declared source name
            content: The raw content dictionary

        Returns:
            True if this extractor should process the data
        """
        pass

    @abstractmethod
    def extract(self, content: Dict[str, Any]) -> Tuple[List[Entity], List[Fact]]:
        """
        Extract entities and facts from raw content.

        Args:
            content: The raw data dictionary

        Returns:
            Tuple of (entities, facts)
        """
        pass

    def get_warnings(self) -> List[str]:
        """Get any warnings generated during extraction."""
        return self._warnings

    def _add_warning(self, message: str):
        """Add a warning message."""
        self._warnings.append(message)

    def _clear_warnings(self):
        """Clear all warnings."""
        self._warnings = []
