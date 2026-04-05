"""
Comparative Memory System Benchmark.

This module provides a unified framework for comparing three memory systems:
1. Deterministic Memory (Current implementation - Neo4j with Cypher)
2. Mem0 (Semantic memory with vector store)
3. Graphiti by Zep (Temporal knowledge graph with embeddings)

Each system is tested with identical data and queries to provide fair comparison
across speed, accuracy, cost, and traceability metrics.
"""

import asyncio
import json
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple
from statistics import mean, stdev

import structlog
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()
logger = structlog.get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class IngestionResult:
    """Result of ingesting data into a memory system."""
    success: bool
    entity_name: str
    metrics_ingested: int
    time_ms: float
    tokens_used: int = 0
    error: Optional[str] = None


@dataclass
class RetrievalResult:
    """Result of retrieving data from a memory system."""
    success: bool
    query: str
    value: Any
    time_ms: float
    tokens_used: int = 0
    exact_match: bool = False
    source: Optional[str] = None
    error: Optional[str] = None


@dataclass
class BenchmarkMetrics:
    """Aggregated metrics for a memory system."""
    system_name: str
    
    # Ingestion metrics
    total_ingestion_time_ms: float = 0.0
    avg_ingestion_time_ms: float = 0.0
    entities_ingested: int = 0
    metrics_ingested: int = 0
    
    # Retrieval metrics
    retrieval_times_ms: List[float] = field(default_factory=list)
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    
    # Accuracy metrics
    queries_total: int = 0
    queries_exact_match: int = 0
    exact_match_rate: float = 0.0
    queries_semantic_match: int = 0  # Value contained in response (text parsing)
    semantic_match_rate: float = 0.0
    
    # Cost metrics
    total_tokens: int = 0
    embedding_tokens: int = 0
    llm_tokens: int = 0
    estimated_cost_usd: float = 0.0
    
    # Traceability
    lineage_available: bool = False
    source_attribution_rate: float = 0.0


# =============================================================================
# MEMORY SYSTEM PROTOCOL
# =============================================================================

class MemorySystem(Protocol):
    """Protocol defining the interface for all memory systems."""
    
    @property
    def name(self) -> str:
        """Return the name of the memory system."""
        ...
    
    async def initialize(self) -> None:
        """Initialize the memory system (create indices, etc.)."""
        ...
    
    async def clear(self) -> None:
        """Clear all data from the memory system."""
        ...
    
    async def ingest(
        self, 
        entity_name: str, 
        data: Dict[str, Any],
        source: str = "StatFin"
    ) -> IngestionResult:
        """Ingest structured data for an entity."""
        ...
    
    async def search(
        self, 
        query: str,
        entity_name: Optional[str] = None,
        metric: Optional[str] = None,
        year: Optional[int] = None
    ) -> RetrievalResult:
        """Search for data matching the query."""
        ...
    
    async def get_lineage(self, entity_name: str) -> Dict[str, Any]:
        """Get data lineage/provenance for an entity."""
        ...
    
    async def close(self) -> None:
        """Close connections and cleanup."""
        ...


# =============================================================================
# DETERMINISTIC MEMORY ADAPTER (Current Implementation)
# =============================================================================

class DeterministicMemoryAdapter:
    """
    Adapter for the current deterministic memory system.
    Uses direct Neo4j queries with no embeddings.
    """
    
    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = os.environ.get("NEO4J_PASSWORD", "password123")
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self._client = None
    
    @property
    def name(self) -> str:
        return "Deterministic (Cypher)"
    
    async def initialize(self) -> None:
        from memory_server.graphiti_client import GraphitiClient
        self._client = GraphitiClient(
            neo4j_uri=self.neo4j_uri,
            neo4j_user=self.neo4j_user,
            neo4j_password=self.neo4j_password
        )
        await self._client.initialize()
        logger.info("Deterministic memory initialized", uri=self.neo4j_uri)
    
    async def clear(self) -> None:
        if self._client:
            await self._client.delete_entity("*")  # Delete all entities
            logger.info("Deterministic memory cleared")
    
    async def ingest(
        self, 
        entity_name: str, 
        data: Dict[str, Any],
        source: str = "StatFin"
    ) -> IngestionResult:
        start_time = time.perf_counter()
        try:
            from memory_server.models import DataPoint, Entity, Fact
            
            # Build entities and facts from the data
            entity = Entity(name=entity_name, type="municipality")
            entities = [entity]
            facts = []
            for key, value in data.items():
                facts.append(Fact(
                    subject=entity,
                    predicate=key,
                    object=value if isinstance(value, (str, int, float)) else str(value)
                ))
            
            data_point = DataPoint(
                source_name=source,
                raw_content={entity_name: data},
                entities=entities,
                facts=facts
            )
            
            await self._client.ingest_data_point(data_point)
            elapsed = (time.perf_counter() - start_time) * 1000
            return IngestionResult(
                success=True,
                entity_name=entity_name,
                metrics_ingested=len(data),
                time_ms=elapsed,
                tokens_used=0  # No tokens for deterministic
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return IngestionResult(
                success=False,
                entity_name=entity_name,
                metrics_ingested=0,
                time_ms=elapsed,
                error=str(e)
            )
    
    async def search(
        self, 
        query: str,
        entity_name: Optional[str] = None,
        metric: Optional[str] = None,
        year: Optional[int] = None
    ) -> RetrievalResult:
        start_time = time.perf_counter()
        try:
            if entity_name and metric:
                result = await self._client.get_statistic(entity_name, metric, year)
                elapsed = (time.perf_counter() - start_time) * 1000
                return RetrievalResult(
                    success=True,
                    query=query,
                    value=result.get("value"),
                    time_ms=elapsed,
                    tokens_used=0,
                    exact_match=True,  # Deterministic is always exact
                    source=result.get("source")
                )
            else:
                elapsed = (time.perf_counter() - start_time) * 1000
                return RetrievalResult(
                    success=False,
                    query=query,
                    value=None,
                    time_ms=elapsed,
                    error="Entity and metric required for deterministic search"
                )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return RetrievalResult(
                success=False,
                query=query,
                value=None,
                time_ms=elapsed,
                error=str(e)
            )
    
    async def get_lineage(self, entity_name: str) -> Dict[str, Any]:
        if self._client:
            return await self._client.get_data_lineage(entity_name)
        return {}
    
    async def close(self) -> None:
        # Neo4j driver cleanup handled by client
        pass


# =============================================================================
# MEM0 MEMORY ADAPTER
# =============================================================================

class Mem0MemoryAdapter:
    """
    Adapter for Mem0 semantic memory system.
    Uses vector store (Qdrant) + OpenAI embeddings.
    User-level memory for entity-based storage.
    """
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        openai_api_key: Optional[str] = None
    ):
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self._memory = None
        self._total_tokens = 0
    
    @property
    def name(self) -> str:
        return "Mem0 (Semantic)"
    
    async def initialize(self) -> None:
        try:
            from mem0 import Memory
            
            config = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "host": self.qdrant_host,
                        "port": self.qdrant_port,
                    }
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": "gpt-4o-mini",
                        "api_key": self.openai_api_key
                    }
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": "text-embedding-3-small",
                        "api_key": self.openai_api_key
                    }
                }
            }
            
            self._memory = Memory.from_config(config)
            logger.info("Mem0 memory initialized", qdrant_host=self.qdrant_host)
        except ImportError:
            logger.error("mem0ai not installed. Run: pip install mem0ai")
            raise
    
    async def clear(self) -> None:
        if self._memory:
            # Delete memories by user_id for all known municipalities
            # (Don't use reset() as it can hang on locks)
            entities = ["helsinki", "espoo", "vantaa", "tampere", "oulu", 
                        "turku", "jyvaskyla", "kuopio", "lahti", "kouvola",
                        "pori", "joensuu", "vaasa", "lappeenranta", "hameenlinna",
                        "rovaniemi", "seinajoki", "mikkeli", "kotka", "salo"]
            for entity in entities:
                try:
                    self._memory.delete_all(user_id=entity)
                except Exception:
                    pass
            logger.info("Mem0 memory cleared for known entities")
    
    async def ingest(
        self, 
        entity_name: str, 
        data: Dict[str, Any],
        source: str = "StatFin"
    ) -> IngestionResult:
        start_time = time.perf_counter()
        try:
            # Convert structured data to personal-style facts for Mem0
            # Mem0 is designed for personal memory, so we need to phrase data
            # as user preferences/interests to trigger fact extraction
            facts_added = 0
            for key, value in data.items():
                # Phrase as personal preference to trigger Mem0's fact extraction
                # e.g., "I am tracking Helsinki population_2024 which is 684018"
                content = f"I am tracking {entity_name} {key} which is exactly {value}."
                
                result = self._memory.add(
                    content,
                    user_id=entity_name.lower(),
                    metadata={"source": source, "entity": entity_name, "metric": key}
                )
                
                # Check if any facts were added
                if result.get("results"):
                    facts_added += len(result["results"])
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            # Estimate tokens (rough: 4 chars = 1 token for embedding + LLM calls)
            # Each metric uses ~100 tokens for extraction + storage
            tokens_used = len(data) * 150
            self._total_tokens += tokens_used
            
            logger.info(f"Mem0 ingested {entity_name}: {facts_added} facts from {len(data)} metrics")
            
            return IngestionResult(
                success=facts_added > 0,
                entity_name=entity_name,
                metrics_ingested=facts_added,
                time_ms=elapsed,
                tokens_used=tokens_used
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return IngestionResult(
                success=False,
                entity_name=entity_name,
                metrics_ingested=0,
                time_ms=elapsed,
                error=str(e)
            )
    
    async def search(
        self, 
        query: str,
        entity_name: Optional[str] = None,
        metric: Optional[str] = None,
        year: Optional[int] = None
    ) -> RetrievalResult:
        start_time = time.perf_counter()
        try:
            # Search with user_id scope if entity provided
            user_id = entity_name.lower() if entity_name else None
            
            results = self._memory.search(
                query=query,
                user_id=user_id,
                limit=5
            )
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            # Estimate tokens for search
            tokens_used = len(query) // 4 + 50
            self._total_tokens += tokens_used
            
            # Mem0 returns {'results': [...]} - extract the list
            result_list = results.get("results", []) if isinstance(results, dict) else results
            
            if result_list and len(result_list) > 0:
                # Extract value from first result
                top_result = result_list[0]
                memory_content = top_result.get("memory", str(top_result))
                
                # Try to extract numeric value - use the LARGEST number (skip years like 2024)
                # This is more likely to be the actual statistical value
                import re
                numbers = re.findall(r'\d+\.?\d*', memory_content)
                if numbers:
                    # Filter out likely years (4-digit numbers between 1900-2100)
                    data_values = [float(n) for n in numbers if not (1900 <= float(n) <= 2100 and len(n) == 4)]
                    if data_values:
                        value = max(data_values)  # Take largest non-year number
                    else:
                        value = memory_content  # Return full text if only years found
                else:
                    value = memory_content
                
                return RetrievalResult(
                    success=True,
                    query=query,
                    value=value,
                    time_ms=elapsed,
                    tokens_used=tokens_used,
                    exact_match=False,  # Semantic search is approximate
                    source=top_result.get("metadata", {}).get("source") if top_result.get("metadata") else None
                )
            else:
                return RetrievalResult(
                    success=False,
                    query=query,
                    value=None,
                    time_ms=elapsed,
                    tokens_used=tokens_used,
                    error="No results found"
                )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return RetrievalResult(
                success=False,
                query=query,
                value=None,
                time_ms=elapsed,
                error=str(e)
            )
    
    async def get_lineage(self, entity_name: str) -> Dict[str, Any]:
        # Mem0 stores metadata but doesn't have explicit lineage
        try:
            memories = self._memory.get_all(user_id=entity_name.lower())
            sources = set()
            for m in memories:
                if "metadata" in m and "source" in m["metadata"]:
                    sources.add(m["metadata"]["source"])
            return {
                "entity": entity_name,
                "sources": list(sources),
                "memory_count": len(memories)
            }
        except Exception:
            return {"entity": entity_name, "sources": [], "memory_count": 0}
    
    async def close(self) -> None:
        pass


# =============================================================================
# GRAPHITI BY ZEP MEMORY ADAPTER
# =============================================================================

class GraphitiZepMemoryAdapter:
    """
    Adapter for Graphiti by Zep temporal knowledge graph.
    Uses Neo4j + OpenAI for entity extraction and embeddings.
    """
    
    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7689",
        neo4j_user: str = "neo4j",
        neo4j_password: str = os.environ.get("NEO4J_GRAPHITI_PASSWORD", "graphiti123"),
        openai_api_key: Optional[str] = None
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self._graphiti = None
        self._total_tokens = 0
    
    @property
    def name(self) -> str:
        return "Graphiti (Zep)"
    
    async def initialize(self) -> None:
        try:
            from graphiti_core import Graphiti
            
            self._graphiti = Graphiti(
                self.neo4j_uri,
                self.neo4j_user,
                self.neo4j_password
            )
            
            await self._graphiti.build_indices_and_constraints()
            logger.info("Graphiti memory initialized", uri=self.neo4j_uri)
        except ImportError:
            logger.error("graphiti-core not installed. Run: pip install graphiti-core")
            raise
    
    async def clear(self) -> None:
        # Clear all data from Graphiti's Neo4j instance
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password)
        )
        try:
            with driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            logger.info("Graphiti memory cleared")
        finally:
            driver.close()
        
        # Re-initialize indices
        if self._graphiti:
            await self._graphiti.build_indices_and_constraints()
    
    async def ingest(
        self, 
        entity_name: str, 
        data: Dict[str, Any],
        source: str = "StatFin"
    ) -> IngestionResult:
        start_time = time.perf_counter()
        try:
            from graphiti_core.nodes import EpisodeType
            
            # Convert data to episode text
            episode_content = f"Statistical data for {entity_name} from {source}:\n"
            for key, value in data.items():
                episode_content += f"- {key}: {value}\n"
            
            await self._graphiti.add_episode(
                name=f"{entity_name}_{source}_{datetime.now().isoformat()}",
                episode_body=episode_content,
                source=EpisodeType.text,
                reference_time=datetime.now(timezone.utc),
                source_description=source
            )
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            # Estimate tokens (LLM extraction + embedding)
            tokens_used = len(episode_content) // 4 + 500  # LLM extraction overhead
            self._total_tokens += tokens_used
            
            return IngestionResult(
                success=True,
                entity_name=entity_name,
                metrics_ingested=len(data),
                time_ms=elapsed,
                tokens_used=tokens_used
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return IngestionResult(
                success=False,
                entity_name=entity_name,
                metrics_ingested=0,
                time_ms=elapsed,
                error=str(e)
            )
    
    async def search(
        self, 
        query: str,
        entity_name: Optional[str] = None,
        metric: Optional[str] = None,
        year: Optional[int] = None
    ) -> RetrievalResult:
        start_time = time.perf_counter()
        try:
            # Graphiti uses hybrid search (semantic + BM25 + graph)
            results = await self._graphiti.search(query)
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            # Estimate tokens for search
            tokens_used = len(query) // 4 + 100
            self._total_tokens += tokens_used
            
            if results and len(results) > 0:
                # Extract from first result
                top_result = results[0]
                
                # Try to extract numeric value from fact - skip years
                import re
                fact_text = str(top_result.fact) if hasattr(top_result, 'fact') else str(top_result)
                numbers = re.findall(r'\d+\.?\d*', fact_text)
                if numbers:
                    # Filter out likely years (4-digit numbers between 1900-2100)
                    data_values = [float(n) for n in numbers if not (1900 <= float(n) <= 2100 and len(n) == 4)]
                    if data_values:
                        value = max(data_values)  # Take largest non-year number
                    else:
                        value = fact_text  # Return full text if only years found
                else:
                    value = fact_text
                
                return RetrievalResult(
                    success=True,
                    query=query,
                    value=value,
                    time_ms=elapsed,
                    tokens_used=tokens_used,
                    exact_match=False,  # Hybrid search is approximate
                    source=getattr(top_result, 'source_description', None)
                )
            else:
                return RetrievalResult(
                    success=False,
                    query=query,
                    value=None,
                    time_ms=elapsed,
                    tokens_used=tokens_used,
                    error="No results found"
                )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return RetrievalResult(
                success=False,
                query=query,
                value=None,
                time_ms=elapsed,
                error=str(e)
            )
    
    async def get_lineage(self, entity_name: str) -> Dict[str, Any]:
        # Query Graphiti's Neo4j for episodic node relationships
        # Note: Graphiti uses 'Episodic' nodes, not 'Episode'
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password)
        )
        try:
            with driver.session() as session:
                # Try multiple label patterns that Graphiti might use
                result = session.run(
                    """
                    MATCH (n)
                    WHERE (n:Episodic OR n:Entity OR n:EpisodicNode)
                    AND (n.name CONTAINS $entity_name OR n.content CONTAINS $entity_name)
                    RETURN labels(n) as labels, n.name as name, n.created_at as created_at
                    LIMIT 10
                    """,
                    entity_name=entity_name
                )
                sources = []
                for record in result:
                    sources.append({
                        "labels": record["labels"],
                        "name": record["name"],
                        "created_at": record["created_at"]
                    })
                return {
                    "entity": entity_name,
                    "sources": sources,
                    "episode_count": len(sources)
                }
        except Exception as e:
            logger.warning(f"Lineage query failed: {e}")
            return {"entity": entity_name, "sources": [], "episode_count": 0}
        finally:
            driver.close()
    
    async def close(self) -> None:
        if self._graphiti:
            await self._graphiti.close()


# =============================================================================
# BASIC RAG ADAPTER (Simple Vector Search)
# =============================================================================

class BasicRAGAdapter:
    """
    Adapter for basic RAG (Retrieval-Augmented Generation) approach.
    Uses simple vector search with OpenAI embeddings - no entity extraction.
    
    This represents the simplest semantic memory approach:
    1. Convert data to text chunks
    2. Embed each chunk with OpenAI text-embedding-3-small
    3. Store in Qdrant vector database
    4. Retrieve by cosine similarity
    
    Key difference from Mem0:
    - No LLM-based entity extraction or memory consolidation
    - Pure vector similarity search
    - Lower cost but potentially lower accuracy for structured data
    """
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "basic_rag_benchmark",
        openai_api_key: Optional[str] = None
    ):
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.collection_name = collection_name
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self._qdrant_client = None
        self._openai_client = None
        self._total_tokens = 0
        self._embedding_dim = 1536  # text-embedding-3-small dimension
    
    @property
    def name(self) -> str:
        return "Basic RAG (Vector)"
    
    async def initialize(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            import openai
            
            self._qdrant_client = QdrantClient(
                host=self.qdrant_host, 
                port=self.qdrant_port
            )
            
            self._openai_client = openai.OpenAI(api_key=self.openai_api_key)
            
            # Create collection if not exists
            collections = self._qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                self._qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE
                    )
                )
            
            logger.info("Basic RAG initialized", 
                       qdrant_host=self.qdrant_host,
                       collection=self.collection_name)
        except ImportError as e:
            logger.error(f"Missing dependency: {e}. Run: pip install qdrant-client openai")
            raise
    
    async def clear(self) -> None:
        if self._qdrant_client:
            try:
                self._qdrant_client.delete_collection(self.collection_name)
                from qdrant_client.models import Distance, VectorParams
                self._qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info("Basic RAG collection cleared")
            except Exception as e:
                logger.warning(f"Could not clear collection: {e}")
    
    def _embed_text(self, text: str) -> List[float]:
        """Embed text using OpenAI API."""
        response = self._openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        # Track tokens
        self._total_tokens += response.usage.total_tokens
        return response.data[0].embedding
    
    async def ingest(
        self, 
        entity_name: str, 
        data: Dict[str, Any],
        source: str = "StatFin"
    ) -> IngestionResult:
        start_time = time.perf_counter()
        try:
            from qdrant_client.models import PointStruct
            
            points = []
            point_id = hash(entity_name) & 0x7FFFFFFF  # Base ID from entity name
            
            # Convert each metric to a searchable text chunk
            for key, value in data.items():
                # Create natural language text for embedding
                text = f"{entity_name} {key.replace('_', ' ')}: {value}. Source: {source}"
                
                # Embed the text
                embedding = self._embed_text(text)
                
                points.append(PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "entity": entity_name,
                        "metric": key,
                        "value": value,
                        "text": text,
                        "source": source
                    }
                ))
                point_id += 1
            
            # Upsert points to Qdrant
            self._qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            elapsed = (time.perf_counter() - start_time) * 1000
            return IngestionResult(
                success=True,
                entity_name=entity_name,
                metrics_ingested=len(data),
                time_ms=elapsed,
                tokens_used=self._total_tokens
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return IngestionResult(
                success=False,
                entity_name=entity_name,
                metrics_ingested=0,
                time_ms=elapsed,
                error=str(e)
            )
    
    async def search(
        self, 
        query: str,
        entity_name: Optional[str] = None,
        metric: Optional[str] = None,
        year: Optional[int] = None
    ) -> RetrievalResult:
        start_time = time.perf_counter()
        try:
            # Embed the query
            query_embedding = self._embed_text(query)
            
            # Build filter if entity specified
            query_filter = None
            if entity_name:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="entity",
                            match=MatchValue(value=entity_name)
                        )
                    ]
                )
            
            # Search Qdrant
            results = self._qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=5
            )
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            if results and len(results) > 0:
                top_result = results[0]
                payload = top_result.payload
                
                # Extract value from payload
                value = payload.get("value")
                
                return RetrievalResult(
                    success=True,
                    query=query,
                    value=value,
                    time_ms=elapsed,
                    tokens_used=self._total_tokens,
                    exact_match=False,  # Vector search is approximate
                    source=payload.get("source")
                )
            else:
                return RetrievalResult(
                    success=False,
                    query=query,
                    value=None,
                    time_ms=elapsed,
                    tokens_used=self._total_tokens,
                    error="No results found"
                )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return RetrievalResult(
                success=False,
                query=query,
                value=None,
                time_ms=elapsed,
                error=str(e)
            )
    
    async def get_lineage(self, entity_name: str) -> Dict[str, Any]:
        """Basic RAG has limited lineage - just source attribution."""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            results = self._qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="entity",
                            match=MatchValue(value=entity_name)
                        )
                    ]
                ),
                limit=100
            )
            
            sources = set()
            for point in results[0]:
                if point.payload and "source" in point.payload:
                    sources.add(point.payload["source"])
            
            return {
                "entity": entity_name,
                "sources": list(sources),
                "chunk_count": len(results[0])
            }
        except Exception:
            return {"entity": entity_name, "sources": [], "chunk_count": 0}
    
    async def close(self) -> None:
        # Qdrant client doesn't need explicit cleanup
        pass


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================

class ComparativeBenchmark:
    """
    Runs comparative benchmarks across all memory systems.
    """
    
    def __init__(
        self, 
        ground_truth_path: str = "benchmark/ground_truth_expanded.json",
        data_path: str = "benchmark/benchmark_data_expanded.json"
    ):
        self.ground_truth_path = Path(ground_truth_path)
        self.data_path = Path(data_path)
        self.systems: List[MemorySystem] = []
        self.results: Dict[str, BenchmarkMetrics] = {}
        
    def add_system(self, system: MemorySystem) -> None:
        self.systems.append(system)
    
    def load_ground_truth(self) -> Dict[str, Any]:
        """Load ground truth queries from JSON file."""
        with open(self.ground_truth_path, "r") as f:
            return json.load(f)
    
    def calculate_percentiles(self, times: List[float]) -> Tuple[float, float, float]:
        """Calculate p50, p95, p99 from a list of times."""
        if not times:
            return 0.0, 0.0, 0.0
        sorted_times = sorted(times)
        n = len(sorted_times)
        p50 = sorted_times[int(n * 0.50)]
        p95 = sorted_times[int(n * 0.95)] if n >= 20 else sorted_times[-1]
        p99 = sorted_times[int(n * 0.99)] if n >= 100 else sorted_times[-1]
        return p50, p95, p99
    
    async def run_ingestion_benchmark(
        self, 
        system: MemorySystem,
        test_data: Dict[str, Dict[str, Any]]
    ) -> BenchmarkMetrics:
        """Run ingestion benchmark for a single system."""
        metrics = BenchmarkMetrics(system_name=system.name)
        
        logger.info(f"Running ingestion benchmark for {system.name}")
        
        total_time = 0.0
        total_metrics = 0
        
        for entity_name, data in test_data.items():
            result = await system.ingest(entity_name, data, source="StatFin")
            if result.success:
                total_time += result.time_ms
                total_metrics += result.metrics_ingested
                metrics.total_tokens += result.tokens_used
                metrics.entities_ingested += 1
        
        metrics.total_ingestion_time_ms = total_time
        metrics.avg_ingestion_time_ms = total_time / len(test_data) if test_data else 0
        metrics.metrics_ingested = total_metrics
        
        return metrics
    
    async def run_retrieval_benchmark(
        self,
        system: MemorySystem,
        queries: List[Dict[str, Any]]
    ) -> BenchmarkMetrics:
        """Run retrieval benchmark for a single system."""
        metrics = BenchmarkMetrics(system_name=system.name)
        
        logger.info(f"Running retrieval benchmark for {system.name}")
        
        retrieval_times = []
        exact_matches = 0
        semantic_matches = 0
        total_tokens = 0
        
        for q in queries:
            # Skip comparison/ranking/schema queries for now
            if q.get("category") in ["comparison", "ranking", "schema"]:
                continue
            
            result = await system.search(
                query=q["query"],
                entity_name=q.get("entity") if isinstance(q.get("entity"), str) else None,
                metric=q.get("metric"),
                year=q.get("year")
            )
            
            retrieval_times.append(result.time_ms)
            total_tokens += result.tokens_used
            metrics.queries_total += 1
            
            # Check for exact match AND semantic match
            if result.success and result.value is not None:
                expected = q.get("expected_value")
                
                # Exact match: value equals expected (for programmatic use)
                if isinstance(expected, (int, float)) and isinstance(result.value, (int, float)):
                    tolerance = 0.0001 * abs(expected) if system.name != "Deterministic (Cypher)" else 0
                    if abs(result.value - expected) <= tolerance:
                        exact_matches += 1
                        result.exact_match = True
                        # Exact match also counts as semantic match
                        semantic_matches += 1
                elif isinstance(expected, (int, float)):
                    # Semantic match: expected value appears in response (for conversational use)
                    # This is fair for text-based responses like "Helsinki population is 684018"
                    expected_int = int(expected) if expected == int(expected) else expected
                    value_str = str(result.value)
                    
                    # Check various formats
                    if str(expected_int) in value_str:
                        semantic_matches += 1
                    elif f"{expected:,.0f}" in value_str:  # Comma formatted
                        semantic_matches += 1
                    elif isinstance(result.value, (int, float)):
                        # Compare as numbers with tolerance
                        try:
                            if abs(float(result.value) - float(expected)) < 0.01 * abs(expected):
                                semantic_matches += 1
                        except (ValueError, TypeError):
                            pass
        
        # Calculate percentiles
        metrics.retrieval_times_ms = retrieval_times
        metrics.p50_latency_ms, metrics.p95_latency_ms, metrics.p99_latency_ms = \
            self.calculate_percentiles(retrieval_times)
        metrics.avg_latency_ms = mean(retrieval_times) if retrieval_times else 0
        
        # Accuracy
        metrics.queries_exact_match = exact_matches
        metrics.exact_match_rate = exact_matches / metrics.queries_total if metrics.queries_total > 0 else 0
        metrics.queries_semantic_match = semantic_matches
        metrics.semantic_match_rate = semantic_matches / metrics.queries_total if metrics.queries_total > 0 else 0
        
        # Tokens
        metrics.total_tokens += total_tokens
        
        # Estimate cost (OpenAI pricing approximation)
        # text-embedding-3-small: $0.02/1M tokens
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        if system.name != "Deterministic (Cypher)":
            metrics.estimated_cost_usd = (metrics.total_tokens / 1_000_000) * 0.20
        
        return metrics
    
    async def run_lineage_benchmark(self, system: MemorySystem, entities: List[str]) -> float:
        """Check lineage availability for a system."""
        available_count = 0
        
        for entity in entities:
            lineage = await system.get_lineage(entity)
            if lineage and lineage.get("sources"):
                available_count += 1
        
        return available_count / len(entities) if entities else 0
    
    async def run_full_benchmark(self) -> Dict[str, Any]:
        """Run complete benchmark suite across all systems."""
        ground_truth = self.load_ground_truth()
        queries = ground_truth.get("queries", [])
        
        # Load real benchmark data from StatFin
        benchmark_data_path = self.data_path
        if benchmark_data_path.exists():
            with open(benchmark_data_path) as f:
                benchmark_json = json.load(f)
            
            # Convert benchmark data format to test_data format
            test_data = {}
            entities_list = []
            for entity_name, entity_data in benchmark_json.get("entities", {}).items():
                entities_list.append(entity_name)
                test_data[entity_name] = entity_data.get("metrics", {})
            
            logger.info(
                "Loaded real StatFin data",
                entities=len(test_data),
                total_metrics=sum(len(m) for m in test_data.values()),
                source=str(benchmark_data_path)
            )
        else:
            # Fallback to placeholder data if no benchmark data file exists
            logger.warning("No benchmark_data.json found, using placeholder data")
            entities_list = ["Helsinki", "Espoo", "Vantaa"]
            test_data = {
                "Helsinki": {
                    "population_2024": 684018,
                    "employed_2024": 326112,
                    "unemployed_2024": 44735
                },
                "Espoo": {
                    "population_2024": 320931,
                    "employed_2024": 151301,
                    "unemployed_2024": 17255
                },
                "Vantaa": {
                    "population_2024": 251269,
                    "employed_2024": 117082,
                    "unemployed_2024": 17717
                }
            }
        
        all_results = {}
        
        for system in self.systems:
            logger.info(f"\n{'='*60}")
            logger.info(f"Benchmarking: {system.name}")
            logger.info(f"{'='*60}")
            
            try:
                # Initialize
                await system.initialize()
                
                # Clear previous data
                await system.clear()
                
                # Run ingestion benchmark
                ingestion_metrics = await self.run_ingestion_benchmark(system, test_data)
                
                # Run retrieval benchmark
                retrieval_metrics = await self.run_retrieval_benchmark(system, queries)
                
                # Check lineage
                lineage_rate = await self.run_lineage_benchmark(system, entities_list)
                
                # Combine metrics
                combined = BenchmarkMetrics(system_name=system.name)
                combined.total_ingestion_time_ms = ingestion_metrics.total_ingestion_time_ms
                combined.avg_ingestion_time_ms = ingestion_metrics.avg_ingestion_time_ms
                combined.entities_ingested = ingestion_metrics.entities_ingested
                combined.metrics_ingested = ingestion_metrics.metrics_ingested
                combined.retrieval_times_ms = retrieval_metrics.retrieval_times_ms
                combined.p50_latency_ms = retrieval_metrics.p50_latency_ms
                combined.p95_latency_ms = retrieval_metrics.p95_latency_ms
                combined.p99_latency_ms = retrieval_metrics.p99_latency_ms
                combined.avg_latency_ms = retrieval_metrics.avg_latency_ms
                combined.queries_total = retrieval_metrics.queries_total
                combined.queries_exact_match = retrieval_metrics.queries_exact_match
                combined.exact_match_rate = retrieval_metrics.exact_match_rate
                combined.queries_semantic_match = retrieval_metrics.queries_semantic_match
                combined.semantic_match_rate = retrieval_metrics.semantic_match_rate
                combined.total_tokens = ingestion_metrics.total_tokens + retrieval_metrics.total_tokens
                combined.estimated_cost_usd = retrieval_metrics.estimated_cost_usd
                combined.lineage_available = lineage_rate > 0
                combined.source_attribution_rate = lineage_rate
                
                all_results[system.name] = combined
                
                # Cleanup
                await system.close()
                
            except Exception as e:
                logger.error(f"Error benchmarking {system.name}: {e}")
                all_results[system.name] = BenchmarkMetrics(system_name=system.name)
        
        return self._format_results(all_results)
    
    def _format_results(self, results: Dict[str, BenchmarkMetrics]) -> Dict[str, Any]:
        """Format results for JSON output."""
        formatted = {
            "benchmark_date": datetime.now(timezone.utc).isoformat(),
            "systems": {}
        }
        
        for name, metrics in results.items():
            formatted["systems"][name] = {
                "ingestion": {
                    "total_time_ms": metrics.total_ingestion_time_ms,
                    "avg_time_ms": metrics.avg_ingestion_time_ms,
                    "entities_ingested": metrics.entities_ingested,
                    "metrics_ingested": metrics.metrics_ingested
                },
                "retrieval": {
                    "p50_latency_ms": metrics.p50_latency_ms,
                    "p95_latency_ms": metrics.p95_latency_ms,
                    "p99_latency_ms": metrics.p99_latency_ms,
                    "avg_latency_ms": metrics.avg_latency_ms
                },
                "accuracy": {
                    "queries_total": metrics.queries_total,
                    "exact_matches": metrics.queries_exact_match,
                    "exact_match_rate": f"{metrics.exact_match_rate * 100:.1f}%",
                    "semantic_matches": metrics.queries_semantic_match,
                    "semantic_match_rate": f"{metrics.semantic_match_rate * 100:.1f}%"
                },
                "cost": {
                    "total_tokens": metrics.total_tokens,
                    "estimated_cost_usd": f"${metrics.estimated_cost_usd:.4f}"
                },
                "traceability": {
                    "lineage_available": metrics.lineage_available,
                    "source_attribution_rate": f"{metrics.source_attribution_rate * 100:.1f}%"
                }
            }
        
        return formatted


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main():
    """Run the comparative benchmark."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run comparative memory benchmark")
    parser.add_argument("--expanded", action="store_true",
                        help="Use expanded benchmark data (50 municipalities)")
    parser.add_argument("--systems", nargs="+", 
                        choices=["deterministic", "mem0", "graphiti", "basicrag", "all"],
                        default=["all"],
                        help="Which systems to benchmark")
    parser.add_argument("--output", type=str, default="benchmark/results/benchmark_results_expanded.json",
                        help="Output file path")
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("COMPARATIVE MEMORY SYSTEM BENCHMARK")
    print("Deterministic vs Mem0 vs Graphiti (Zep) vs Basic RAG")
    print("=" * 70 + "\n")
    
    # Determine which ground truth to use
    if args.expanded:
        gt_path = "benchmark/ground_truth_expanded.json"
        data_path = "benchmark/benchmark_data_expanded.json"
        print("Using EXPANDED benchmark data (10 municipalities)")
    else:
        gt_path = "benchmark/ground_truth_expanded.json"
        data_path = "benchmark/benchmark_data_expanded.json"
        print("Using benchmark data (10 municipalities)")
    
    # Initialize benchmark runner
    benchmark = ComparativeBenchmark(ground_truth_path=gt_path, data_path=data_path)
    
    systems_to_run = args.systems
    if "all" in systems_to_run:
        systems_to_run = ["deterministic", "mem0", "graphiti", "basicrag"]
    
    # Add memory systems based on selection
    if "deterministic" in systems_to_run:
        benchmark.add_system(DeterministicMemoryAdapter(
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD", "password123")
        ))
    
    if "mem0" in systems_to_run:
        benchmark.add_system(Mem0MemoryAdapter(
            qdrant_host="localhost",
            qdrant_port=6333
        ))
    
    if "graphiti" in systems_to_run:
        benchmark.add_system(GraphitiZepMemoryAdapter(
            neo4j_uri=os.environ.get("NEO4J_GRAPHITI_URI", "bolt://localhost:7689"),
            neo4j_user=os.environ.get("NEO4J_GRAPHITI_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_GRAPHITI_PASSWORD", "graphiti123")
        ))
    
    if "basicrag" in systems_to_run:
        benchmark.add_system(BasicRAGAdapter(
            qdrant_host="localhost",
            qdrant_port=6333,
            collection_name="basic_rag_benchmark"
        ))
    
    print(f"Systems to benchmark: {[s.name for s in benchmark.systems]}")
    print(f"Ground truth: {gt_path}")
    print()
    
    # Run benchmarks
    results = await benchmark.run_full_benchmark()
    
    # Add metadata
    results["metadata"] = {
        "expanded_data": args.expanded,
        "ground_truth_path": gt_path,
        "data_path": data_path,
        "systems_benchmarked": [s.name for s in benchmark.systems]
    }
    
    # Save results
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to {output_path}")
    
    # Print summary table
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"{'System':<25} {'Avg Latency':<15} {'Exact Match':<15} {'Semantic Match':<15} {'Cost':<15}")
    print("-" * 100)
    
    for name, data in results.get("systems", {}).items():
        latency = f"{data['retrieval']['avg_latency_ms']:.2f}ms"
        exact = data['accuracy']['exact_match_rate']
        semantic = data['accuracy']['semantic_match_rate']
        cost = data['cost']['estimated_cost_usd']
        print(f"{name:<25} {latency:<15} {exact:<15} {semantic:<15} {cost:<15}")
    
    print("=" * 100)
    print("\nExact Match = Programmatic use (APIs, calculations)")
    print("Semantic Match = Value contained in response (conversational AI)")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())
