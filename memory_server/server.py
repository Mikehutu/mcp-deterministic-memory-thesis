"""
Deterministic Statistical Memory MCP Server.

This server provides AI agents with access to structured statistical data
through the Model Context Protocol (MCP).

KEY DESIGN PRINCIPLE:
- The LLM is the semantic layer (understands natural language)
- This server is the data layer (returns exact values)
- No embeddings, no vector search, no hallucination risk

Tool Categories:
1. DISCOVERY - What data exists? (list_entities, get_entity_schema, list_metrics)
2. QUERY     - Get exact values  (get_statistic, compare_entities)
3. INGEST    - Store new data    (ingest_knowledge)
4. AUDIT     - Track lineage     (get_data_lineage, retrieve_recent)
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import structlog
from mcp.server.fastmcp import FastMCP

from .graphiti_client import GraphitiClient
from .models import DataPoint
from .extractors import get_extractor, extract_entities_and_facts

logger = structlog.get_logger(__name__)

# Global state
graphiti_client: Optional[GraphitiClient] = None


@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Manage server lifecycle."""
    global graphiti_client

    logger.info("Initializing Deterministic Statistical Memory Server...")

    try:
        graphiti_client = GraphitiClient()
        await graphiti_client.initialize()
        logger.info("Server initialized successfully - deterministic mode")
        yield
    except Exception as e:
        logger.error("Failed to initialize server", error=str(e))
        raise
    finally:
        logger.info("Server shutting down")


mcp = FastMCP("Statistical Memory Server", lifespan=server_lifespan)


# =============================================================================
# DISCOVERY TOOLS - What data exists?
# =============================================================================

@mcp.tool()
async def list_entities(entity_type: str = None) -> str:
    """
    List all entities stored in memory, optionally filtered by type.
    Use this first to discover what data is available.

    Args:
        entity_type: Optional filter (e.g., "City", "Region", "Municipality").
                     Leave empty to list all entities.

    Returns:
        List of entity names with their types.

    Example:
        list_entities() → All entities
        list_entities("City") → Only cities
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        entities = await graphiti_client.list_entities(entity_type)

        if not entities:
            return f"No entities found" + (f" of type '{entity_type}'" if entity_type else "")

        return json.dumps(entities, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("List entities failed", error=str(e))
        return f"Error: {str(e)}"


@mcp.tool()
async def get_entity_schema(entity_name: str) -> str:
    """
    Get all available data for a specific entity.
    This shows what metrics/statistics exist for the entity.

    IMPORTANT: Call this before querying to see what data is available!

    Args:
        entity_name: Exact name of the entity (e.g., "Helsinki", "Vantaa").

    Returns:
        All properties with values, plus any relationships.

    Example:
        get_entity_schema("Helsinki") →
        {
            "entity": "Helsinki",
            "properties": {
                "population_2024": 684018,
                "population_2023": 670000,
                "unemployment_rate": 8.5
            },
            "labels": ["Entity", "City"]
        }
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        schema = await graphiti_client.get_entity_schema(entity_name)

        if not schema.get("properties") and not schema.get("relationships"):
            return f"Entity '{entity_name}' not found or has no data."

        return json.dumps(schema, indent=2, ensure_ascii=False, default=str)

    except Exception as e:
        logger.error("Get entity schema failed", error=str(e))
        return f"Error: {str(e)}"


@mcp.tool()
async def list_available_metrics() -> str:
    """
    List all unique metrics/statistics stored across all entities.
    Helps understand what can be queried.

    Returns:
        List of metric names with counts of how many entities have each.

    Example:
        list_available_metrics() →
        [
            {"metric": "population_2024", "entity_count": 5},
            {"metric": "unemployment_rate", "entity_count": 3}
        ]
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        metrics = await graphiti_client.list_available_metrics()

        if not metrics:
            return "No metrics found in memory."

        return json.dumps(metrics, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("List metrics failed", error=str(e))
        return f"Error: {str(e)}"


# =============================================================================
# QUERY TOOLS - Get exact values (deterministic)
# =============================================================================

@mcp.tool()
async def get_statistic(entity: str, metric: str, year: int = None) -> str:
    """
    Get exact statistic value for an entity.
    Returns the precise stored value - no approximation or inference.

    Args:
        entity: Entity name (e.g., "Helsinki", "Espoo").
        metric: Metric name (e.g., "population", "unemployment_rate").
        year: Optional year for time-series data.

    Returns:
        Exact value with metadata.

    Examples:
        get_statistic("Helsinki", "population", 2024) → {"value": 684018}
        get_statistic("Vantaa", "unemployment_rate") → {"value": 7.2}
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        result = await graphiti_client.get_statistic(entity, metric, year)
        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("Get statistic failed", error=str(e))
        return f"Error: {str(e)}"


@mcp.tool()
async def compare_entities(entity_names: List[str], metric: str, year: int = None) -> str:
    """
    Compare a specific metric across multiple entities.
    Returns exact values for each entity, sorted by value.

    Args:
        entity_names: List of entity names to compare.
        metric: The metric to compare (e.g., "population", "income").
        year: Optional year for time-series data.

    Returns:
        List of entity-value pairs, sorted descending.

    Example:
        compare_entities(["Helsinki", "Vantaa", "Espoo"], "population", 2024) →
        [
            {"entity": "Helsinki", "value": 684018},
            {"entity": "Espoo", "value": 300000},
            {"entity": "Vantaa", "value": 245000}
        ]
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        comparisons = await graphiti_client.compare_entities(entity_names, metric, year)

        if not comparisons:
            return f"No data found for metric '{metric}' on specified entities."

        return json.dumps(comparisons, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("Compare entities failed", error=str(e))
        return f"Error: {str(e)}"


@mcp.tool()
async def get_all_entity_data(entity: str) -> str:
    """
    Get ALL stored statistics for an entity at once.
    Useful for comprehensive analysis of a single entity.

    Args:
        entity: Entity name.

    Returns:
        All statistics stored for the entity.

    Example:
        get_all_entity_data("Helsinki") →
        {
            "entity": "Helsinki",
            "labels": ["Entity", "City"],
            "statistics": {
                "population_2024": 684018,
                "population_2023": 670000,
                "area_km2": 214.0,
                "unemployment_rate": 8.5
            }
        }
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        data = await graphiti_client.get_all_statistics_for_entity(entity)
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)

    except Exception as e:
        logger.error("Get all entity data failed", error=str(e))
        return f"Error: {str(e)}"


# =============================================================================
# INGEST TOOLS - Store new data
# =============================================================================

@mcp.tool()
async def ingest_knowledge(source: str, content: Dict[str, Any]) -> str:
    """
    Ingest structured knowledge into the memory system.
    Data is stored deterministically and can be retrieved exactly.

    Args:
        source: Name of the data source (e.g., "StatFin", "User", "API").
        content: The data to ingest as a dictionary.

    Returns:
        Confirmation with ingestion details.

    Example:
        ingest_knowledge("StatFin", {
            "city": "Helsinki",
            "year": 2024,
            "population": 684018
        })
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        entities, facts = extract_entities_and_facts(source, content)

        data_point = DataPoint(
            source_name=source,
            raw_content=content,
            entities=entities,
            facts=facts
        )

        episode_id = await graphiti_client.ingest_data_point(data_point)

        summary = f"Successfully ingested data from {source}.\n"
        summary += f"  • Episode ID: {episode_id}\n"
        summary += f"  • Entities created: {len(data_point.entities)}\n"
        summary += f"  • Facts stored: {len(data_point.facts)}"

        if data_point.entities:
            names = [e.name for e in data_point.entities[:5]]
            summary += f"\n  • Entities: {', '.join(names)}"

        if data_point.facts:
            fact_examples = [f"{f.predicate}={f.object}" for f in data_point.facts[:3]]
            summary += f"\n  • Sample facts: {', '.join(fact_examples)}"

        return summary

    except Exception as e:
        logger.error("Ingestion failed", error=str(e))
        return f"Error ingesting data: {str(e)}"


@mcp.tool()
async def preview_extraction(source: str, content: Dict[str, Any]) -> str:
    """
    Preview what would be extracted from data WITHOUT storing it.
    Use this to validate data structure before ingesting.

    Args:
        source: Data source name.
        content: The data to analyze.

    Returns:
        Preview of entities and facts that would be created.
    """
    try:
        extractor = get_extractor(source, content)

        if not extractor:
            return json.dumps({
                "status": "warning",
                "message": f"No specific extractor for '{source}'. Will store as raw data.",
                "entities": [],
                "facts": []
            }, indent=2)

        entities, facts = extractor.extract(content)
        warnings = extractor.get_warnings()

        return json.dumps({
            "status": "ok",
            "extractor": extractor.source_name,
            "entities": [
                {"name": e.name, "type": e.type, "description": e.description}
                for e in entities
            ],
            "facts": [
                {
                    "subject": f.subject.name,
                    "predicate": f.predicate,
                    "value": str(f.object),
                    "year": f.valid_at.year if f.valid_at else None
                }
                for f in facts
            ],
            "warnings": warnings
        }, indent=2)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=2)


# =============================================================================
# AUDIT TOOLS - Track data lineage
# =============================================================================

@mcp.tool()
async def retrieve_recent_knowledge(limit: int = 5) -> str:
    """
    Retrieve the most recently ingested data.
    Shows what was stored, when, and from which source.

    Args:
        limit: Number of recent entries to retrieve (default 5).

    Returns:
        List of recent data ingestion events with details.
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        episodes = await graphiti_client.get_recent_episodes(limit)

        if not episodes:
            return "No data has been ingested yet."

        return json.dumps(episodes, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("Retrieval failed", error=str(e))
        return f"Error: {str(e)}"


@mcp.tool()
async def get_data_lineage(entity_name: str) -> str:
    """
    Get the data lineage for an entity - track where data came from.
    Important for auditing and verifying data sources.

    Args:
        entity_name: Name of the entity to trace.

    Returns:
        List of data sources and ingestion timestamps.

    Example:
        get_data_lineage("Helsinki") →
        {
            "entity": "Helsinki",
            "sources": [
                {"source": "StatFin", "ingested_at": "2024-12-22T10:30:00"},
                {"source": "User", "ingested_at": "2024-12-21T15:45:00"}
            ]
        }
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        lineage = await graphiti_client.get_data_lineage(entity_name)
        return json.dumps(lineage, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("Get lineage failed", error=str(e))
        return f"Error: {str(e)}"


# =============================================================================
# MANAGEMENT TOOLS
# =============================================================================

@mcp.tool()
async def delete_knowledge(entity_name: str) -> str:
    """
    Delete a specific entity and its relationships from memory.
    Use "*" to delete ALL data (use with caution!).

    Args:
        entity_name: Entity to delete, or "*" for everything.

    Returns:
        Confirmation of deletion.
    """
    global graphiti_client
    if not graphiti_client:
        return "Error: Server not initialized"

    try:
        count = await graphiti_client.delete_entity(entity_name)

        if entity_name == "*":
            return f"Deleted ALL data ({count} nodes removed)."
        elif count > 0:
            return f"Deleted entity '{entity_name}' ({count} nodes removed)."
        else:
            return f"Entity '{entity_name}' not found."

    except Exception as e:
        logger.error("Deletion failed", error=str(e))
        return f"Error: {str(e)}"


if __name__ == "__main__":
    mcp.run()
