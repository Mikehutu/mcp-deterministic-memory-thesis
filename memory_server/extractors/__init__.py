"""
Entity and Fact Extractors for Universal Memory System.

This module provides pattern-based extraction of entities and facts
from various data sources.
"""

from .base import BaseExtractor
from .statfin import StatFinExtractor
from .registry import get_extractor, register_extractor, extract_entities_and_facts

__all__ = [
    "BaseExtractor",
    "StatFinExtractor",
    "get_extractor",
    "register_extractor",
    "extract_entities_and_facts",
]
