"""
Generic Data Models for Universal Memory System.

These models define the standard interface between Data Drivers (e.g., StatFin)
and the Memory Core (Neo4j).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Entity(BaseModel):
    """
    Represents a distinct entity (Node) in the knowledge graph.

    Examples:
        - Place: Helsinki
        - Time: 2023-Q1
        - Concept: Housing Price
    """
    name: str = Field(..., description="Unique name/identifier of the entity")
    type: str = Field(..., description="Type of the entity (e.g., 'Place', 'Time', 'Metric')")
    description: Optional[str] = Field(None, description="Human-readable description")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional properties")

    @field_validator('name')
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Entity name must not be empty')
        return v.strip()


class Fact(BaseModel):
    """
    Represents a relationship (Edge) between two entities or an entity and a value.

    Examples:
        - Helsinki (Subject) -> HAS_POPULATION (Predicate) -> 684018 (Object)
    """
    subject: Entity = Field(..., description="The source entity")
    predicate: str = Field(..., description="The relationship type (e.g., 'HAS_POPULATION')")
    object: Union[Entity, str, float, int] = Field(..., description="The target entity or literal value")

    valid_at: Optional[datetime] = Field(None, description="When this fact is/was true")
    invalid_at: Optional[datetime] = Field(None, description="When this fact ceased to be true")

    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")


class DatasetMetadata(BaseModel):
    """Metadata for a discoverable dataset from a driver."""
    id: str = Field(..., description="Unique identifier for the dataset within the driver")
    name: str = Field(..., description="Human-readable name of the dataset")
    description: Optional[str] = Field(None, description="Description of the dataset content")
    path: Optional[str] = Field(None, description="API path or resource location")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Query parameters schema")


class DataPoint(BaseModel):
    """
    A container for knowledge extracted from a single source record.

    Contains the raw content (for lineage) and structured Facts (for the graph).
    """
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique ID for this data point")
    source_name: str = Field(..., description="Name of the data source (e.g., 'StatFin')")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Ingestion time")

    raw_content: Dict[str, Any] = Field(..., description="The original raw data record")
    entities: List[Entity] = Field(default_factory=list, description="Entities identified in this point")
    facts: List[Fact] = Field(default_factory=list, description="Facts extracted from this point")


class IngestionResult(BaseModel):
    """Result of an ingestion operation."""
    success: bool
    message: str
    processed_count: int
    error_details: Optional[Dict[str, Any]] = None
