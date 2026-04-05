#!/usr/bin/env python
"""
Neo4j setup script for Graphiti knowledge graph.

This script initializes the Neo4j database with the necessary indices and constraints
required by Graphiti for efficient knowledge graph operations.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

try:
    from graphiti_core import Graphiti
except ImportError:
    print("Error: graphiti_core package not found. Please install it with:")
    print("pip install graphiti_core")
    sys.exit(1)


async def setup_neo4j():
    """Initialize Neo4j database with Graphiti indices and constraints."""
    load_dotenv()

    # Get Neo4j connection parameters from environment variables or use defaults
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password123")

    print(f"Connecting to Neo4j at {neo4j_uri}...")
    
    try:
        # Initialize Graphiti with Neo4j connection
        graphiti = Graphiti(neo4j_uri, neo4j_user, neo4j_password)
        
        # Build indices and constraints
        print("Building Graphiti indices and constraints...")
        await graphiti.build_indices_and_constraints()
        
        print("Neo4j setup completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error setting up Neo4j: {str(e)}")
        return False


if __name__ == "__main__":
    if sys.platform == "win32":
        # Windows-specific event loop policy
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    success = asyncio.run(setup_neo4j())
    sys.exit(0 if success else 1)
