import asyncio
import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase

async def clear_database():
    load_dotenv()
    
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password123")
    
    print(f"Connecting to Neo4j at {uri}...")
    
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        def delete_all(tx):
            result = tx.run("MATCH (n) DETACH DELETE n")
            summary = result.consume()
            return summary.counters.nodes_deleted, summary.counters.relationships_deleted

        with driver.session() as session:
            nodes_deleted, rels_deleted = session.execute_write(delete_all)
            print(f"Deleted {nodes_deleted} nodes and {rels_deleted} relationships.")
            
        driver.close()
        print("Database cleared successfully.")
        
    except Exception as e:
        print(f"Error clearing database: {e}")

if __name__ == "__main__":
    asyncio.run(clear_database())
