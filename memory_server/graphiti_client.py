"""
Deterministic Knowledge Store Client.

This module provides direct Neo4j access for storing and retrieving
structured statistical data. No embeddings, no semantic search.
The LLM acts as the semantic layer.

Architecture:
- All queries are deterministic Cypher queries
- Entities stored with clear labels and properties
- Facts stored as properties or relationships
- Full auditability and reproducibility
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from neo4j import GraphDatabase

from .models import DataPoint, Entity, Fact

logger = structlog.get_logger(__name__)


class GraphitiClient:
    """
    Deterministic knowledge store using Neo4j.

    Stores structured statistical data in a graph database
    with exact retrieval via Cypher queries. No vector/semantic search.
    """

    def __init__(
        self,
        neo4j_uri: str = None,
        neo4j_user: str = None,
        neo4j_password: str = None
    ):
        """
        Initialize the knowledge store client.

        Credentials are read from environment variables by default.
        Never hardcode credentials.

        Args:
            neo4j_uri: Neo4j connection URI (default: NEO4J_URI env var)
            neo4j_user: Neo4j username (default: NEO4J_USER env var)
            neo4j_password: Neo4j password (default: NEO4J_PASSWORD env var)
        """
        self.neo4j_uri = neo4j_uri or os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        self.neo4j_user = neo4j_user or os.environ.get('NEO4J_USER', 'neo4j')
        self.neo4j_password = neo4j_password or os.environ.get('NEO4J_PASSWORD', '')

        logger.info("Knowledge store client initialized", uri=self.neo4j_uri)

    def _get_driver(self):
        """Create a Neo4j driver connection."""
        return GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password)
        )

    async def initialize(self):
        """Initialize database indices for optimal query performance."""
        driver = self._get_driver()
        try:
            with driver.session() as session:
                indices = [
                    "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)",
                    "CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.type)",
                    "CREATE INDEX episode_created IF NOT EXISTS FOR (n:Episode) ON (n.created_at)",
                    "CREATE INDEX statistic_year IF NOT EXISTS FOR (n:Statistic) ON (n.year)",
                ]
                for idx in indices:
                    try:
                        session.run(idx)
                    except Exception:
                        pass  # Index may already exist
            logger.info("Database indices initialized")
        finally:
            driver.close()

    # =========================================================================
    # INGESTION - Store structured data
    # =========================================================================

    async def ingest_data_point(self, data_point: DataPoint) -> str:
        """
        Ingest a structured DataPoint into the knowledge store.

        Creates:
        - Entity nodes with appropriate labels
        - Property values for numeric facts
        - Relationships for entity-to-entity facts
        - Episode node for audit trail

        Returns:
            Episode UUID for tracking
        """
        driver = self._get_driver()
        episode_id = str(uuid4())

        try:
            with driver.session() as session:
                # 1. Create Episode node for audit trail
                episode_content = {
                    "source": data_point.source_name,
                    "timestamp": data_point.timestamp.isoformat(),
                    "raw_data": data_point.raw_content,
                    "entities": [e.name for e in data_point.entities],
                    "facts_count": len(data_point.facts)
                }

                session.run("""
                    CREATE (e:Episode {
                        uuid: $uuid,
                        source: $source,
                        created_at: datetime(),
                        content: $content
                    })
                """, uuid=episode_id, source=data_point.source_name,
                   content=json.dumps(episode_content))

                # 2. Create/Merge Entities with labels and link to Episode
                for entity in data_point.entities:
                    label = self._sanitize_label(entity.type) if entity.type else "Entity"

                    query = f"""
                    MERGE (n:Entity {{name: $name}})
                    SET n:{label}
                    SET n.type = $type
                    SET n.description = $description
                    SET n.updated_at = datetime()
                    """
                    session.run(query,
                               name=entity.name,
                               type=entity.type,
                               description=entity.description)

                    session.run("""
                        MATCH (e:Episode {uuid: $episode_id})
                        MATCH (n:Entity {name: $name})
                        MERGE (n)-[r:SOURCED_FROM]->(e)
                        SET r.timestamp = datetime()
                    """, episode_id=episode_id, name=entity.name)

                    if entity.metadata:
                        for key, value in entity.metadata.items():
                            prop_key = self._sanitize_property(key)
                            session.run(f"""
                                MATCH (n:Entity {{name: $name}})
                                SET n.{prop_key} = $value
                            """, name=entity.name, value=value)

                # 3. Create Facts (properties or relationships)
                for fact in data_point.facts:
                    subject_name = fact.subject.name
                    predicate = self._sanitize_property(fact.predicate)
                    year = None

                    if isinstance(fact.object, (int, float, str, bool)):
                        if fact.valid_at:
                            year = fact.valid_at.year
                            prop_name = f"{predicate}_{year}"
                        else:
                            prop_name = predicate

                        session.run(f"""
                            MATCH (n:Entity {{name: $name}})
                            SET n.{prop_name} = $value
                        """, name=subject_name, value=fact.object)

                        metric_name = self._predicate_to_metric_name(predicate)
                        rel_type = predicate.upper().replace('HAS_', 'MEASURED_')

                        session.run(f"""
                            MATCH (s:Entity {{name: $subject}})
                            MATCH (m:Entity:Metric {{name: $metric}})
                            MERGE (s)-[r:{rel_type}]->(m)
                            SET r.value = $value
                            SET r.year = $year
                        """, subject=subject_name, metric=metric_name,
                           value=fact.object, year=year)

                        if fact.valid_at:
                            year_str = str(fact.valid_at.year)
                            session.run("""
                                MATCH (s:Entity {name: $subject})
                                MERGE (y:Entity:TimePeriod {name: $year})
                                SET y.type = 'Year'
                                MERGE (s)-[r:HAS_DATA_FOR]->(y)
                            """, subject=subject_name, year=year_str)

                    elif hasattr(fact.object, 'name'):
                        rel_type = predicate.upper()
                        session.run(f"""
                            MATCH (s:Entity {{name: $subject}})
                            MERGE (o:Entity {{name: $object}})
                            MERGE (s)-[r:{rel_type}]->(o)
                            SET r.confidence = $confidence
                            SET r.valid_at = $valid_at
                        """, subject=subject_name,
                           object=fact.object.name,
                           confidence=fact.confidence,
                           valid_at=fact.valid_at.isoformat() if fact.valid_at else None)

                logger.info("Ingested DataPoint",
                           episode_id=episode_id,
                           entities=len(data_point.entities),
                           facts=len(data_point.facts))

        except Exception as e:
            logger.error("Failed to ingest DataPoint", error=str(e))
            raise
        finally:
            driver.close()

        return episode_id

    # =========================================================================
    # DISCOVERY - What data exists?
    # =========================================================================

    async def list_entities(self, entity_type: str = None) -> List[Dict[str, Any]]:
        """List all entities, optionally filtered by type."""
        driver = self._get_driver()
        entities = []

        try:
            with driver.session() as session:
                if entity_type:
                    query = f"""
                    MATCH (n:{self._sanitize_label(entity_type)})
                    RETURN n.name as name, n.type as type, n.description as description
                    ORDER BY n.name
                    """
                else:
                    query = """
                    MATCH (n:Entity)
                    RETURN n.name as name, n.type as type, n.description as description
                    ORDER BY n.name
                    """
                result = session.run(query)

                for record in result:
                    entities.append({
                        "name": record["name"],
                        "type": record["type"],
                        "description": record["description"]
                    })
        finally:
            driver.close()

        return entities

    async def get_entity_schema(self, entity_name: str) -> Dict[str, Any]:
        """Get all available metrics/properties for an entity."""
        driver = self._get_driver()
        schema = {"entity": entity_name, "properties": {}, "relationships": []}

        try:
            with driver.session() as session:
                result = session.run("""
                    MATCH (n:Entity {name: $name})
                    RETURN properties(n) as props, labels(n) as labels
                """, name=entity_name)

                record = result.single()
                if record:
                    props = dict(record["props"])
                    internal = ['name', 'uuid', 'created_at', 'updated_at', 'name_embedding']
                    schema["properties"] = {
                        k: v for k, v in props.items() if k not in internal
                    }
                    schema["labels"] = list(record["labels"])

                rel_result = session.run("""
                    MATCH (n:Entity {name: $name})-[r]->(m)
                    RETURN type(r) as rel_type, m.name as target, properties(r) as props
                """, name=entity_name)

                for rec in rel_result:
                    schema["relationships"].append({
                        "type": rec["rel_type"],
                        "target": rec["target"],
                        "properties": dict(rec["props"]) if rec["props"] else {}
                    })
        finally:
            driver.close()

        return schema

    async def list_available_metrics(self) -> List[Dict[str, Any]]:
        """List all unique metrics/properties stored across all entities."""
        driver = self._get_driver()
        metrics = []

        try:
            with driver.session() as session:
                result = session.run("""
                    MATCH (n:Entity)
                    WITH n, [k IN keys(n) WHERE NOT k IN ['name', 'type', 'description', 'uuid',
                                      'created_at', 'updated_at', 'name_embedding',
                                      'summary', 'group_id']] as filtered_keys
                    UNWIND filtered_keys as key
                    RETURN key as metric,
                           collect(DISTINCT n.name)[0..3] as example_entities,
                           count(*) as entity_count
                    ORDER BY entity_count DESC
                """)

                for record in result:
                    metrics.append({
                        "metric": record["metric"],
                        "entity_count": record["entity_count"],
                        "example_entities": list(record["example_entities"])
                    })
        finally:
            driver.close()

        return metrics

    # =========================================================================
    # QUERY - Get exact values (deterministic)
    # =========================================================================

    async def get_statistic(
        self,
        entity: str,
        metric: str,
        year: int = None
    ) -> Dict[str, Any]:
        """
        Get exact statistic value for an entity.

        Tries multiple property name variations:
        - Direct name (e.g., "population")
        - With has_ prefix (e.g., "has_population")
        - With year suffix (e.g., "population_2024")
        - Uppercase variants
        """
        driver = self._get_driver()

        try:
            with driver.session() as session:
                prop_name = self._sanitize_property(metric)

                property_variants = []
                if year:
                    property_variants.extend([
                        f"{prop_name}_{year}",
                        f"has_{prop_name}_{year}",
                        f"HAS_{prop_name.upper()}_{year}",
                    ])
                property_variants.extend([
                    prop_name,
                    f"has_{prop_name}",
                    f"HAS_{prop_name.upper()}",
                ])

                result = session.run("""
                    MATCH (n:Entity {name: $name})
                    RETURN properties(n) as props, n.type as type
                """, name=entity)

                record = result.single()
                if record and record["props"]:
                    props = dict(record["props"])
                    entity_type = record["type"]

                    for variant in property_variants:
                        if variant in props:
                            return {
                                "entity": entity,
                                "metric": metric,
                                "year": year,
                                "value": props[variant],
                                "entity_type": entity_type,
                                "matched_property": variant
                            }

                    props_lower = {k.lower(): (k, v) for k, v in props.items()}
                    for variant in property_variants:
                        if variant.lower() in props_lower:
                            orig_key, value = props_lower[variant.lower()]
                            return {
                                "entity": entity,
                                "metric": metric,
                                "year": year,
                                "value": value,
                                "entity_type": entity_type,
                                "matched_property": orig_key
                            }

                return {
                    "entity": entity,
                    "metric": metric,
                    "year": year,
                    "value": None,
                    "error": "Statistic not found",
                    "tried_properties": property_variants[:5]
                }

        finally:
            driver.close()

    async def compare_entities(
        self,
        entities: List[str],
        metric: str,
        year: int = None
    ) -> List[Dict[str, Any]]:
        """Compare a specific metric across multiple entities."""
        driver = self._get_driver()
        comparisons = []

        try:
            with driver.session() as session:
                prop_name = self._sanitize_property(metric)

                property_variants = []
                if year:
                    property_variants.extend([
                        f"{prop_name}_{year}",
                        f"has_{prop_name}_{year}",
                        f"HAS_{prop_name.upper()}_{year}",
                    ])
                property_variants.extend([
                    prop_name,
                    f"has_{prop_name}",
                    f"HAS_{prop_name.upper()}",
                ])

                result = session.run("""
                    UNWIND $entities as entity_name
                    MATCH (n:Entity {name: entity_name})
                    WITH n, [p in keys(n) WHERE p IN $variants] as matching_keys
                    RETURN n.name as entity, n[matching_keys[0]] as value, n.type as type
                    ORDER BY value DESC
                """, entities=entities, variants=property_variants)

                for record in result:
                    comparisons.append({
                        "entity": record["entity"],
                        "metric": metric,
                        "year": year,
                        "value": record["value"],
                        "entity_type": record["type"]
                    })
        finally:
            driver.close()

        return comparisons

    async def get_all_statistics_for_entity(self, entity: str) -> Dict[str, Any]:
        """Get ALL stored statistics for an entity."""
        driver = self._get_driver()

        try:
            with driver.session() as session:
                result = session.run("""
                    MATCH (n:Entity {name: $name})
                    RETURN properties(n) as props, labels(n) as labels
                """, name=entity)

                record = result.single()
                if record:
                    props = dict(record["props"])
                    internal = ['name', 'uuid', 'created_at', 'updated_at',
                               'name_embedding', 'summary', 'group_id']
                    statistics = {k: v for k, v in props.items() if k not in internal}

                    return {
                        "entity": entity,
                        "labels": list(record["labels"]),
                        "statistics": statistics
                    }

                return {"entity": entity, "error": "Entity not found"}
        finally:
            driver.close()

    # =========================================================================
    # AUDIT - Track data lineage
    # =========================================================================

    async def get_recent_episodes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve the most recent data ingestion events."""
        driver = self._get_driver()
        episodes = []

        try:
            with driver.session() as session:
                result = session.run("""
                    MATCH (e:Episode)
                    RETURN e.uuid as uuid, e.source as source,
                           e.created_at as created_at, e.content as content
                    ORDER BY e.created_at DESC
                    LIMIT $limit
                """, limit=limit)

                for record in result:
                    try:
                        content = json.loads(record["content"]) if record["content"] else {}
                        episodes.append({
                            "uuid": record["uuid"],
                            "source": record["source"],
                            "created_at": str(record["created_at"]),
                            "content": content
                        })
                    except Exception:
                        pass
        finally:
            driver.close()

        return episodes

    async def get_data_lineage(self, entity_name: str) -> Dict[str, Any]:
        """Get the data lineage for an entity."""
        driver = self._get_driver()

        try:
            with driver.session() as session:
                result = session.run("""
                    MATCH (e:Episode)
                    WHERE e.content CONTAINS $name
                    RETURN e.source as source, e.created_at as created_at,
                           e.uuid as episode_id
                    ORDER BY e.created_at DESC
                """, name=entity_name)

                sources = []
                for record in result:
                    sources.append({
                        "source": record["source"],
                        "ingested_at": str(record["created_at"]),
                        "episode_id": record["episode_id"]
                    })

                return {
                    "entity": entity_name,
                    "sources": sources,
                    "source_count": len(sources)
                }
        finally:
            driver.close()

    # =========================================================================
    # MANAGEMENT - Delete, clear
    # =========================================================================

    async def delete_entity(self, name: str) -> int:
        """Delete an entity and its relationships."""
        driver = self._get_driver()
        nodes_deleted = 0

        try:
            with driver.session() as session:
                if name == "*":
                    result = session.run("MATCH (n) DETACH DELETE n")
                else:
                    result = session.run("""
                        MATCH (n:Entity {name: $name})
                        DETACH DELETE n
                    """, name=name)

                summary = result.consume()
                nodes_deleted = summary.counters.nodes_deleted
                logger.info("Deleted entity", name=name, nodes_deleted=nodes_deleted)
        finally:
            driver.close()

        return nodes_deleted

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _sanitize_label(self, label: str) -> str:
        """Sanitize a string to be a valid Neo4j label."""
        if not label:
            return "Entity"
        clean = ''.join(c for c in label if c.isalnum() or c == '_')
        return clean.title().replace('_', '') if clean else "Entity"

    def _sanitize_property(self, prop: str) -> str:
        """Sanitize a string to be a valid Neo4j property name."""
        if not prop:
            return "value"
        clean = prop.lower().replace(' ', '_').replace('-', '_')
        return ''.join(c for c in clean if c.isalnum() or c == '_')

    def _predicate_to_metric_name(self, predicate: str) -> str:
        """Convert a predicate to a display metric name."""
        name = predicate.lower()
        if name.startswith('has_'):
            name = name[4:]
        name = re.sub(r'_[0-9]{4}$', '', name)
        return name.replace('_', ' ').title()
