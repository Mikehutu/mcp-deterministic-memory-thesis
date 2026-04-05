"""
Fetch Expanded StatFin Data for Comprehensive Benchmark.

This script fetches data for 50 largest Finnish municipalities across multiple
metric categories for thesis benchmark comparison:
- Population (total, male, female)
- Employment and unemployment
- Income levels
- Key employment indicators (rates)

Target: ~2,500 data points for robust statistical comparison.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
import sys
from typing import Dict, List, Tuple, Any
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from statfin_server.client import StatFinClient


# Rate limiting configuration
REQUEST_DELAY_SECONDS = 1.0  # Delay between API requests to avoid rate limits
MAX_RETRIES = 5  # Number of retries on rate limit errors


async def rate_limited_fetch(client: StatFinClient, table_path: str, query: dict, retries: int = MAX_RETRIES) -> dict:
    """Fetch data with rate limiting and retry logic."""
    for attempt in range(retries):
        try:
            await asyncio.sleep(REQUEST_DELAY_SECONDS)
            result = await client.fetch_data(table_path, query)
            return result
        except Exception as e:
            if "429" in str(e):
                # Rate limited - wait longer and retry
                wait_time = (attempt + 1) * 5  # Exponential backoff: 5, 10, 15, 20, 25 seconds
                print(f"      ⏳ Rate limited, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                raise
    raise Exception(f"Failed after {retries} retries due to rate limiting")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Top 50 Finnish municipalities by population (2024 data)
# Format: (Name, Municipality Code)
TOP_50_MUNICIPALITIES: List[Tuple[str, str]] = [
    ("Helsinki", "KU091"),
    ("Espoo", "KU049"),
    ("Tampere", "KU837"),
    ("Vantaa", "KU092"),
    ("Oulu", "KU564"),
    ("Turku", "KU853"),
    ("Jyväskylä", "KU179"),
    ("Lahti", "KU398"),
    ("Kuopio", "KU297"),
    ("Pori", "KU609"),
    ("Kouvola", "KU286"),
    ("Joensuu", "KU167"),
    ("Lappeenranta", "KU405"),
    ("Hämeenlinna", "KU109"),
    ("Vaasa", "KU905"),
    ("Seinäjoki", "KU743"),
    ("Rovaniemi", "KU698"),
    ("Mikkeli", "KU491"),
    ("Kotka", "KU285"),
    ("Salo", "KU734"),
    ("Porvoo", "KU638"),
    ("Kokkola", "KU272"),
    ("Lohja", "KU444"),
    ("Hyvinkää", "KU106"),
    ("Nurmijärvi", "KU543"),
    ("Järvenpää", "KU186"),
    ("Rauma", "KU684"),
    ("Kajaani", "KU205"),
    ("Tuusula", "KU858"),
    ("Kirkkonummi", "KU257"),
    ("Kerava", "KU245"),
    ("Nokia", "KU536"),
    ("Ylöjärvi", "KU980"),
    ("Kaarina", "KU202"),
    ("Kangasala", "KU211"),
    ("Riihimäki", "KU694"),
    ("Imatra", "KU153"),
    ("Raseborg", "KU710"),
    ("Savonlinna", "KU740"),
    ("Vihti", "KU927"),
    ("Raisio", "KU680"),
    ("Sastamala", "KU790"),
    ("Tornio", "KU851"),
    ("Siilinjärvi", "KU749"),
    ("Iisalmi", "KU140"),
    ("Hollola", "KU098"),
    ("Valkeakoski", "KU908"),
    ("Mäntsälä", "KU505"),
    ("Lempäälä", "KU418"),
    ("Kemi", "KU240"),
]

# Years to fetch (5-year span for trend analysis)
YEARS = ["2020", "2021", "2022", "2023", "2024"]

# Tables configuration
TABLES = {
    "population": {
        "path": "vaerak/statfin_vaerak_pxt_11rm.px",
        "metrics": {
            "population_total": {"Sukupuoli": ["SSS"], "Kieli": ["SSS"], "Tiedot": ["vaesto"]},
            "population_male": {"Sukupuoli": ["1"], "Kieli": ["SSS"], "Tiedot": ["vaesto"]},
            "population_female": {"Sukupuoli": ["2"], "Kieli": ["SSS"], "Tiedot": ["vaesto"]},
        }
    },
    "employment": {
        "path": "tyokay/statfin_tyokay_pxt_115b.px",
        "metrics": {
            "employed": {
                "Pääasiallinen toiminta": ["11"],  # Employed
                "Sukupuoli": ["SSS"],
                "Ikä": ["SSS"]
            },
            "unemployed": {
                "Pääasiallinen toiminta": ["12"],  # Unemployed
                "Sukupuoli": ["SSS"],
                "Ikä": ["SSS"]
            },
        }
    },
    "key_indicators": {
        "path": "tyokay/statfin_tyokay_pxt_115x.px",
        "metrics": {
            "employment_rate": {"Tiedot": ["tyollisyysaste"]},
            "unemployment_rate": {"Tiedot": ["tyottomyysaste"]},
            "dependency_ratio": {"Tiedot": ["taloudellinenhuoltosuhde"]},
        }
    },
    "income": {
        "path": "tjt/statfin_tjt_pxt_14ww.px",
        "metrics": {
            "median_income": {"Tiedot": ["ekvikturaha_med"]},
            "gini_coefficient": {"Tiedot": ["gini"]},
        }
    },
}


# =============================================================================
# DATA FETCHING FUNCTIONS
# =============================================================================

async def fetch_population_data(
    client: StatFinClient,
    municipalities: List[Tuple[str, str]],
    years: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Fetch population data for all municipalities."""
    print("\n📊 Fetching population data...")
    table_path = TABLES["population"]["path"]
    data = {}
    
    # Fetch for each municipality
    for city, code in municipalities:
        if city not in data:
            data[city] = {"code": code, "type": "municipality", "metrics": {}}
        
        # Total population
        query = {
            "query": [
                {"code": "Alue", "selection": {"filter": "item", "values": [code]}},
                {"code": "Vuosi", "selection": {"filter": "item", "values": years}},
                {"code": "Sukupuoli", "selection": {"filter": "item", "values": ["SSS"]}},
                {"code": "Kieli", "selection": {"filter": "item", "values": ["SSS"]}},
                {"code": "Tiedot", "selection": {"filter": "item", "values": ["vaesto"]}}
            ],
            "response": {"format": "json-stat2"}
        }
        
        try:
            result = await rate_limited_fetch(client, table_path, query)
            values = result.get("value", [])
            dimensions = result.get("dimension", {})
            year_dim = dimensions.get("Vuosi", {}).get("category", {}).get("index", {})
            
            for year, idx in year_dim.items():
                if idx < len(values) and values[idx] is not None:
                    data[city]["metrics"][f"population_{year}"] = int(values[idx])
            
            print(f"   ✓ {city}: {len(year_dim)} years")
        except Exception as e:
            print(f"   ✗ {city}: {e}")
    
    return data


async def fetch_employment_data(
    client: StatFinClient,
    data: Dict[str, Dict[str, Any]],
    municipalities: List[Tuple[str, str]],
    years: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Fetch employment/unemployment data."""
    print("\n👔 Fetching employment data...")
    table_path = TABLES["employment"]["path"]
    
    for city, code in municipalities:
        # Employed
        query = {
            "query": [
                {"code": "Alue", "selection": {"filter": "item", "values": [code]}},
                {"code": "Vuosi", "selection": {"filter": "item", "values": years}},
                {"code": "Pääasiallinen toiminta", "selection": {"filter": "item", "values": ["11"]}},
                {"code": "Sukupuoli", "selection": {"filter": "item", "values": ["SSS"]}},
                {"code": "Ikä", "selection": {"filter": "item", "values": ["SSS"]}}
            ],
            "response": {"format": "json-stat2"}
        }
        
        try:
            result = await rate_limited_fetch(client, table_path, query)
            values = result.get("value", [])
            dimensions = result.get("dimension", {})
            year_dim = dimensions.get("Vuosi", {}).get("category", {}).get("index", {})
            
            for year, idx in year_dim.items():
                if idx < len(values) and values[idx] is not None:
                    data[city]["metrics"][f"employed_{year}"] = int(values[idx])
        except Exception as e:
            print(f"   ✗ {city} employed: {e}")
        
        # Unemployed
        query["query"][2]["selection"]["values"] = ["12"]
        try:
            result = await rate_limited_fetch(client, table_path, query)
            values = result.get("value", [])
            dimensions = result.get("dimension", {})
            year_dim = dimensions.get("Vuosi", {}).get("category", {}).get("index", {})
            
            for year, idx in year_dim.items():
                if idx < len(values) and values[idx] is not None:
                    data[city]["metrics"][f"unemployed_{year}"] = int(values[idx])
        except Exception as e:
            print(f"   ✗ {city} unemployed: {e}")
        
        metric_count = sum(1 for k in data[city]["metrics"] if "employed" in k or "unemployed" in k)
        print(f"   ✓ {city}: {metric_count} employment metrics")
    
    return data


async def fetch_key_indicators(
    client: StatFinClient,
    data: Dict[str, Dict[str, Any]],
    municipalities: List[Tuple[str, str]],
    years: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Fetch employment rate, unemployment rate, dependency ratio."""
    print("\n📈 Fetching key indicators...")
    table_path = TABLES["key_indicators"]["path"]
    
    indicators = [
        ("employment_rate", "tyollisyysaste"),
        ("unemployment_rate", "tyottomyysaste"),
        ("dependency_ratio", "taloudellinenhuoltosuhde"),
    ]
    
    for city, code in municipalities:
        for metric_name, tiedot_code in indicators:
            query = {
                "query": [
                    {"code": "Alue", "selection": {"filter": "item", "values": [code]}},
                    {"code": "Vuosi", "selection": {"filter": "item", "values": years}},
                    {"code": "Tiedot", "selection": {"filter": "item", "values": [tiedot_code]}}
                ],
                "response": {"format": "json-stat2"}
            }
            
            try:
                result = await rate_limited_fetch(client, table_path, query)
                values = result.get("value", [])
                dimensions = result.get("dimension", {})
                year_dim = dimensions.get("Vuosi", {}).get("category", {}).get("index", {})
                
                for year, idx in year_dim.items():
                    if idx < len(values) and values[idx] is not None:
                        # Store as float for rates/ratios
                        data[city]["metrics"][f"{metric_name}_{year}"] = round(float(values[idx]), 2)
            except Exception as e:
                print(f"   ✗ {city} {metric_name}: {e}")
        
        print(f"   ✓ {city}: indicators fetched")
    
    return data


async def fetch_income_data(
    client: StatFinClient,
    data: Dict[str, Dict[str, Any]],
    municipalities: List[Tuple[str, str]],
    years: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Fetch income data (median income, Gini coefficient)."""
    print("\n💰 Fetching income data...")
    table_path = TABLES["income"]["path"]
    
    metrics_to_fetch = [
        ("median_income", "ekvikturaha_med"),
    ]
    
    for city, code in municipalities:
        for metric_name, tiedot_code in metrics_to_fetch:
            query = {
                "query": [
                    {"code": "Alue", "selection": {"filter": "item", "values": [code]}},
                    {"code": "Vuosi", "selection": {"filter": "item", "values": years}},
                    {"code": "Tiedot", "selection": {"filter": "item", "values": [tiedot_code]}}
                ],
                "response": {"format": "json-stat2"}
            }
            
            try:
                result = await rate_limited_fetch(client, table_path, query)
                values = result.get("value", [])
                dimensions = result.get("dimension", {})
                year_dim = dimensions.get("Vuosi", {}).get("category", {}).get("index", {})
                
                for year, idx in year_dim.items():
                    if idx < len(values) and values[idx] is not None:
                        data[city]["metrics"][f"{metric_name}_{year}"] = round(float(values[idx]), 2)
            except Exception as e:
                pass  # Income data may not be available for all municipalities
        
        income_count = sum(1 for k in data[city]["metrics"] if "income" in k)
        if income_count > 0:
            print(f"   ✓ {city}: {income_count} income metrics")
    
    return data


# =============================================================================
# GROUND TRUTH GENERATION
# =============================================================================

def generate_ground_truth(benchmark_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive ground truth queries from the dataset."""
    queries = []
    query_id = 1
    
    # Category 1: Exact Value Queries (~150)
    print("\n📝 Generating exact value queries...")
    for entity_name, entity_data in benchmark_data["entities"].items():
        for metric_name, value in entity_data.get("metrics", {}).items():
            # Parse metric name to extract year
            parts = metric_name.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                base_metric = parts[0]
                year = int(parts[1])
            else:
                base_metric = metric_name
                year = None
            
            # Create query with natural language
            metric_readable = base_metric.replace("_", " ")
            
            if year:
                query_text = f"What is {entity_name}'s {metric_readable} in {year}?"
            else:
                query_text = f"What is {entity_name}'s {metric_readable}?"
            
            queries.append({
                "id": f"Q{query_id:04d}",
                "query": query_text,
                "entity": entity_name,
                "metric": base_metric,
                "year": year,
                "expected_value": value,
                "category": "exact_match"
            })
            query_id += 1
    
    # Category 2: Comparison Queries (~30)
    print("📝 Generating comparison queries...")
    entities = list(benchmark_data["entities"].keys())
    
    # Compare largest cities
    large_cities = ["Helsinki", "Espoo", "Tampere", "Vantaa", "Oulu"]
    available_large = [c for c in large_cities if c in entities]
    
    for i in range(len(available_large)):
        for j in range(i + 1, len(available_large)):
            city1, city2 = available_large[i], available_large[j]
            
            # Population comparison
            pop1 = benchmark_data["entities"][city1]["metrics"].get("population_2024")
            pop2 = benchmark_data["entities"][city2]["metrics"].get("population_2024")
            
            if pop1 and pop2:
                queries.append({
                    "id": f"Q{query_id:04d}",
                    "query": f"Compare the population of {city1} and {city2} in 2024",
                    "entity": [city1, city2],
                    "metric": "population",
                    "year": 2024,
                    "expected_value": {city1: pop1, city2: pop2},
                    "category": "comparison"
                })
                query_id += 1
    
    # Category 3: Trend Queries (~20)
    print("📝 Generating trend queries...")
    for city in available_large[:5]:
        entity_data = benchmark_data["entities"].get(city, {})
        metrics = entity_data.get("metrics", {})
        
        # Population trend
        pop_values = {}
        for year in YEARS:
            key = f"population_{year}"
            if key in metrics:
                pop_values[year] = metrics[key]
        
        if len(pop_values) >= 3:
            queries.append({
                "id": f"Q{query_id:04d}",
                "query": f"What is the population trend for {city} from 2020 to 2024?",
                "entity": city,
                "metric": "population_trend",
                "year": None,
                "expected_value": pop_values,
                "category": "trend"
            })
            query_id += 1
    
    return {
        "description": "Comprehensive ground truth queries for expanded benchmark",
        "generated_at": datetime.now().isoformat(),
        "data_source": "benchmark/benchmark_data_expanded.json",
        "statistics": {
            "total_queries": len(queries),
            "exact_match": len([q for q in queries if q["category"] == "exact_match"]),
            "comparison": len([q for q in queries if q["category"] == "comparison"]),
            "trend": len([q for q in queries if q["category"] == "trend"]),
        },
        "queries": queries
    }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

async def fetch_all_data(limit: int = None) -> Dict[str, Any]:
    """Fetch all data for benchmark."""
    client = StatFinClient()
    
    # Use limit for testing
    municipalities = TOP_50_MUNICIPALITIES[:limit] if limit else TOP_50_MUNICIPALITIES
    years = YEARS
    
    benchmark_data = {
        "metadata": {
            "fetched_at": datetime.now().isoformat(),
            "source": "Statistics Finland (StatFin)",
            "description": "Expanded benchmark dataset for memory system comparison",
            "municipalities_count": len(municipalities),
            "years": years,
            "tables_used": [
                {"path": t["path"], "category": cat}
                for cat, t in TABLES.items()
            ]
        },
        "entities": {}
    }
    
    try:
        # Fetch population data first
        data = await fetch_population_data(client, municipalities, years)
        benchmark_data["entities"] = data
        
        # Add employment data
        data = await fetch_employment_data(client, data, municipalities, years)
        benchmark_data["entities"] = data
        
        # Add key indicators
        data = await fetch_key_indicators(client, data, municipalities, years)
        benchmark_data["entities"] = data
        
        # Add income data
        data = await fetch_income_data(client, data, municipalities, years)
        benchmark_data["entities"] = data
        
    finally:
        await client.close()
    
    return benchmark_data


async def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch expanded StatFin data")
    parser.add_argument("--limit", type=int, default=None, 
                        help="Limit number of municipalities (for testing)")
    parser.add_argument("--output", type=str, default="benchmark/benchmark_data_expanded.json",
                        help="Output file path")
    args = parser.parse_args()
    
    print("=" * 70)
    print("FETCHING EXPANDED STATFIN DATA FOR BENCHMARK")
    print("=" * 70)
    
    limit_text = f" (limited to {args.limit})" if args.limit else ""
    print(f"\nTarget: {args.limit or 50} municipalities{limit_text}")
    print(f"Years: {', '.join(YEARS)}")
    print(f"Output: {args.output}")
    
    # Fetch data
    benchmark_data = await fetch_all_data(limit=args.limit)
    
    # Calculate statistics
    total_entities = len(benchmark_data["entities"])
    total_metrics = sum(
        len(e.get("metrics", {})) 
        for e in benchmark_data["entities"].values()
    )
    
    print("\n" + "=" * 70)
    print("DATA SUMMARY")
    print("=" * 70)
    print(f"Entities (municipalities): {total_entities}")
    print(f"Total data points: {total_metrics}")
    print(f"Average metrics per entity: {total_metrics / total_entities:.1f}")
    
    # Show breakdown by metric type
    metric_types = {}
    for entity_data in benchmark_data["entities"].values():
        for metric in entity_data.get("metrics", {}).keys():
            base = metric.rsplit("_", 1)[0] if metric.rsplit("_", 1)[1].isdigit() else metric
            metric_types[base] = metric_types.get(base, 0) + 1
    
    print("\nMetric breakdown:")
    for metric, count in sorted(metric_types.items(), key=lambda x: -x[1]):
        print(f"  {metric}: {count}")
    
    # Save benchmark data
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Benchmark data saved to {output_path}")
    
    # Generate and save ground truth
    ground_truth = generate_ground_truth(benchmark_data)
    gt_path = output_path.parent / "ground_truth_expanded.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)
    print(f"✓ Ground truth queries saved to {gt_path}")
    print(f"  Total queries: {ground_truth['statistics']['total_queries']}")
    print(f"  - Exact match: {ground_truth['statistics']['exact_match']}")
    print(f"  - Comparison: {ground_truth['statistics']['comparison']}")
    print(f"  - Trend: {ground_truth['statistics']['trend']}")
    
    print("\n" + "=" * 70)
    print("DONE!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
