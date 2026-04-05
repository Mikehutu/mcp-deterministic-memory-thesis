"""
Extractor registry for selecting the right extractor based on data source.
"""

from typing import Any, Dict, List, Optional, Tuple

import structlog

from ..models import Entity, Fact
from .base import BaseExtractor

logger = structlog.get_logger(__name__)

# Global registry of extractors
_extractors: List[BaseExtractor] = []


def register_extractor(extractor: BaseExtractor) -> None:
    """Register an extractor in the global registry."""
    _extractors.append(extractor)
    logger.info(f"Registered extractor: {extractor.source_name}")


def get_extractor(source: str, content: Optional[Dict[str, Any]] = None) -> Optional[BaseExtractor]:
    """
    Get the appropriate extractor for a given source and content.

    Args:
        source: The declared data source name
        content: The raw content (optional, for pattern detection)

    Returns:
        The matching extractor, or None if no extractor matches
    """
    content = content or {}

    for extractor in _extractors:
        if extractor.can_handle(source, content):
            logger.debug(f"Selected extractor: {extractor.source_name} for source: {source}")
            return extractor

    logger.warning(f"No extractor found for source: {source}")
    return None


def extract_entities_and_facts(
    source: str, content: Dict[str, Any]
) -> Tuple[List[Entity], List[Fact]]:
    """
    Convenience function to extract entities and facts from content.

    Args:
        source: The data source name
        content: The raw content dictionary

    Returns:
        Tuple of (entities, facts), empty lists if no extractor found
    """
    extractor = get_extractor(source, content)

    if extractor:
        return extractor.extract(content)

    return [], []


def list_extractors() -> List[str]:
    """List all registered extractor names."""
    return [e.source_name for e in _extractors]


def _init_extractors():
    """Initialize built-in extractors."""
    from .statfin import StatFinExtractor

    if not any(isinstance(e, StatFinExtractor) for e in _extractors):
        register_extractor(StatFinExtractor())
