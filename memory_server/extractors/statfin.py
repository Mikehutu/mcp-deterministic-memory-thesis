"""
StatFin-specific entity and fact extraction.

This extractor understands the common patterns in Statistics Finland data
and converts them to proper graph entities and relationships.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Set

import structlog

from ..models import Entity, Fact
from .base import BaseExtractor

logger = structlog.get_logger(__name__)


# Finnish municipality codes to names
# Includes all 10 municipalities from the benchmark dataset
MUNICIPALITY_CODES = {
    # Benchmark dataset municipalities (10 largest Finnish cities by population)
    "KU091": "Helsinki",
    "KU049": "Espoo",
    "KU837": "Tampere",
    "KU092": "Vantaa",
    "KU564": "Oulu",
    "KU853": "Turku",
    "KU179": "Jyväskylä",
    "KU398": "Lahti",
    "KU297": "Kuopio",
    "KU609": "Pori",
    # Numeric aliases (for raw API responses)
    "091": "Helsinki",
    "049": "Espoo",
    "837": "Tampere",
    "092": "Vantaa",
    "564": "Oulu",
    "853": "Turku",
    "179": "Jyväskylä",
    "398": "Lahti",
    "297": "Kuopio",
    "609": "Pori",
    # Additional municipalities (extended set for broader use)
    "KU106": "Hyvinkää",
    "KU543": "Nurmijärvi",
    "KU186": "Järvenpää",
    "KU245": "Kerava",
    "KU858": "Tuusula",
    "KU753": "Sipoo",
    "KU257": "Kirkkonummi",
    "KU638": "Porvoo",
    "KU444": "Lohja",
    "KU927": "Vihti",
}

# Metric name normalization — EXACT matches only
METRIC_NORMALIZATIONS = {
    # Population
    "population": "Population",
    "population (prelim)": "Population",
    "population 31 dec": "Population",
    "total": "Population",
    "vaesto": "Population",
    # Population change — DISTINCT from population
    "population_change": "Population Change",
    "population change": "Population Change",
    "vaestonmuutos": "Population Change",
    # Growth rate
    "growth_rate": "Growth Rate",
    "growth rate": "Growth Rate",
    # Housing prices
    "old flats price (eur/m2)": "Housing Price",
    "price per square meter": "Housing Price",
    "priceperm2_old_dwellings_eur_m2": "Housing Price",
    "price": "Housing Price",
    # Rent
    "average rent": "Rent",
    "average rent 1-room": "Rent (1-room)",
    "average rent 2-room": "Rent (2-room)",
    "average rent 3+ rooms": "Rent (3+ rooms)",
    "keskivuokra": "Rent",
    # Employment
    "employment rate": "Employment Rate",
    "unemployment rate": "Unemployment Rate",
    # Demographics
    "live births": "Births",
    "births": "Births",
    "deaths": "Deaths",
    "net migration": "Net Migration",
    # Income
    "median equivalised disposable income": "Median Income",
}

# Keys that indicate city/municipality
CITY_KEYS = ["city", "Alue", "municipality", "Kunta", "alue", "region", "Region"]

# Keys that indicate time period
TIME_KEYS = ["period", "quarter", "year", "Year", "Quarter", "Vuosi", "Vuosineljännes"]


class StatFinExtractor(BaseExtractor):
    """Extractor for Statistics Finland data."""

    @property
    def source_name(self) -> str:
        return "StatFin"

    def can_handle(self, source: str, content: Dict[str, Any]) -> bool:
        """Check if this looks like StatFin data."""
        source_lower = source.lower()

        if "statfin" in source_lower or "statistics finland" in source_lower:
            return True

        if self._find_statfin_tables(content):
            return True

        for key in CITY_KEYS:
            if key in content:
                val = str(content[key])
                if val.startswith("KU") or val in MUNICIPALITY_CODES:
                    return True

        return False

    def extract(self, content: Dict[str, Any]) -> Tuple[List[Entity], List[Fact]]:
        """Extract entities and facts from StatFin data."""
        self._clear_warnings()

        entities: List[Entity] = []
        facts: List[Fact] = []
        entity_map: Dict[str, Entity] = {}
        processed_keys: Set[str] = set()

        location_entity = self._extract_location(content, entity_map)
        time_entities = self._extract_times(content, entity_map)
        metrics = self._extract_metrics(content, processed_keys)

        for metric in metrics:
            metric_name = metric.get("name", "Unknown")
            value = metric.get("value")
            unit = metric.get("unit")
            period = metric.get("period")

            if value is None:
                continue

            subject = location_entity or self._get_or_create_entity(
                entity_map, "Unknown Location", "Place"
            )

            normalized_name = self._normalize_metric_name(metric_name)
            predicate = f"HAS_{normalized_name.upper().replace(' ', '_').replace('-', '_')}"
            valid_at = self._parse_period(period) if period else None

            fact = Fact(
                subject=subject,
                predicate=predicate,
                object=value,
                valid_at=valid_at,
                confidence=1.0
            )
            facts.append(fact)

            if normalized_name not in entity_map:
                metric_entity = Entity(
                    name=normalized_name,
                    type="Metric",
                    description=f"Metric: {normalized_name}",
                    metadata={"unit": unit} if unit else {}
                )
                entity_map[normalized_name] = metric_entity

        entities = list(entity_map.values())

        logger.info(
            "StatFin extraction complete",
            entities=len(entities),
            facts=len(facts),
            warnings=len(self._warnings)
        )

        return entities, facts

    def _extract_location(
        self, content: Dict[str, Any], entity_map: Dict[str, Entity]
    ) -> Optional[Entity]:
        """Extract the primary location entity."""
        for key in CITY_KEYS:
            if key in content:
                city_name = self._resolve_municipality(str(content[key]))
                return self._get_or_create_entity(entity_map, city_name, "Municipality")

        for key, value in content.items():
            if isinstance(value, dict):
                resolved = self._resolve_municipality(key)
                if resolved != key or key in MUNICIPALITY_CODES.values():
                    return self._get_or_create_entity(entity_map, resolved, "Municipality")

        metrics = content.get("metrics", [])
        if isinstance(metrics, list):
            for m in metrics:
                if isinstance(m, dict):
                    filters = m.get("filters", {})
                    for fkey, fval in filters.items():
                        if fkey.lower() == "alue":
                            city_name = self._resolve_municipality(str(fval))
                            return self._get_or_create_entity(entity_map, city_name, "Municipality")

        raw = content.get("raw_data", {})
        if isinstance(raw, dict) and raw and raw is not content:
            return self._extract_location(raw, entity_map)

        return None

    def _extract_times(
        self, content: Dict[str, Any], entity_map: Dict[str, Entity]
    ) -> List[Entity]:
        """Extract time period entities."""
        times = []

        def find_times(obj, depth=0):
            if depth > 5:
                return
            if isinstance(obj, dict):
                for key in TIME_KEYS:
                    if key in obj:
                        time_val = str(obj[key])
                        if time_val not in entity_map:
                            entity = Entity(
                                name=time_val,
                                type="TimePeriod",
                                description=f"Time period: {time_val}"
                            )
                            entity_map[time_val] = entity
                            times.append(entity)
                for v in obj.values():
                    find_times(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    find_times(item, depth + 1)

        find_times(content)
        return times

    def _extract_metrics(self, content: Dict[str, Any], processed_keys: Set[str]) -> List[Dict[str, Any]]:
        """Extract all metric values from the content."""
        metrics = []

        if "metrics" in content and isinstance(content["metrics"], list):
            for m in content["metrics"]:
                if isinstance(m, dict) and "name" in m:
                    key = f"metrics.{m.get('name', '')}"
                    if key not in processed_keys:
                        processed_keys.add(key)
                        metrics.append(m)

        if "facts" in content and isinstance(content["facts"], list):
            for fact in content["facts"]:
                if isinstance(fact, dict) and "value" in fact:
                    key = f"facts.{fact.get('name', str(fact.get('value', '')))}"
                    if key not in processed_keys:
                        processed_keys.add(key)
                        metrics.append(fact)

        nested = self._extract_nested_metrics(content, processed_keys)
        metrics.extend(nested)

        for key, value in content.items():
            if isinstance(value, (int, float)) and key.lower() not in ["limit", "count"]:
                metric_key = f"direct.{key}"
                if metric_key in processed_keys:
                    continue
                processed_keys.add(metric_key)

                year_match = re.search(r'_(\d{4})$', key)
                if year_match:
                    period = year_match.group(1)
                    metric_name = re.sub(r'_\d{4}$', '', key)
                else:
                    period = content.get("year") or content.get("Year")
                    metric_name = key

                metrics.append({
                    "name": metric_name,
                    "value": value,
                    "period": str(period) if period else None
                })

        return metrics

    def _extract_nested_metrics(self, obj: Any, processed_keys: Set[str], path: str = "") -> List[Dict[str, Any]]:
        """Recursively extract metrics from nested structures."""
        metrics = []

        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() in ["metrics", "facts", "raw_data", "limit", "count"]:
                    continue

                new_path = f"{path}.{key}" if path else key

                if isinstance(value, (int, float)) and value is not None:
                    metric_key = f"nested.{new_path}"
                    if metric_key in processed_keys:
                        continue
                    processed_keys.add(metric_key)

                    period = self._extract_period_from_path(new_path)
                    metrics.append({
                        "name": key,
                        "value": value,
                        "period": period,
                        "path": new_path
                    })
                elif isinstance(value, dict):
                    metrics.extend(self._extract_nested_metrics(value, processed_keys, new_path))

        return metrics

    def _extract_period_from_path(self, path: str) -> Optional[str]:
        """Try to extract a time period from a nested path."""
        year_match = re.search(r'\b(20\d{2})\b', path)
        if year_match:
            return year_match.group(1)

        quarter_match = re.search(r'(20\d{2}Q[1-4])', path)
        if quarter_match:
            return quarter_match.group(1)

        return None

    def _resolve_municipality(self, code_or_name: str) -> str:
        """Resolve a municipality code to its name."""
        if code_or_name in MUNICIPALITY_CODES:
            return MUNICIPALITY_CODES[code_or_name]

        if " " in code_or_name:
            parts = code_or_name.split(" ", 1)
            if parts[0] in MUNICIPALITY_CODES:
                return MUNICIPALITY_CODES[parts[0]]
            return parts[-1]

        return code_or_name

    def _normalize_metric_name(self, name: str) -> str:
        """
        Normalize a metric name to a standard form.

        Uses EXACT matching only to prevent data collision.
        Example: 'population_change' must NOT match 'population'.
        """
        name_lower = name.lower().strip()

        if name_lower in METRIC_NORMALIZATIONS:
            return METRIC_NORMALIZATIONS[name_lower]

        base_name = re.sub(r'_\d{4}$', '', name_lower)
        if base_name in METRIC_NORMALIZATIONS:
            return METRIC_NORMALIZATIONS[base_name]

        cleaned = name.replace("_", " ").replace("-", " ").title()
        return cleaned

    def _parse_period(self, period: str) -> Optional[datetime]:
        """Parse a period string into a datetime."""
        if not period:
            return None

        period = str(period).strip()

        try:
            if re.match(r'^\d{4}$', period):
                return datetime(int(period), 12, 31)

            quarter_match = re.match(r'^(\d{4})Q([1-4])$', period)
            if quarter_match:
                year = int(quarter_match.group(1))
                quarter = int(quarter_match.group(2))
                month = quarter * 3
                return datetime(year, month, 1)

            month_match = re.match(r'^(\d{4})M(\d{1,2})$', period)
            if month_match:
                year = int(month_match.group(1))
                month = int(month_match.group(2))
                return datetime(year, month, 1)

        except Exception as e:
            self._add_warning(f"Could not parse period '{period}': {e}")

        return None

    def _get_or_create_entity(
        self, entity_map: Dict[str, Entity], name: str, entity_type: str
    ) -> Entity:
        """Get an existing entity or create a new one."""
        if name in entity_map:
            return entity_map[name]

        entity = Entity(
            name=name,
            type=entity_type,
            description=f"{entity_type}: {name}"
        )
        entity_map[name] = entity
        return entity

    def _find_statfin_tables(self, content: Dict[str, Any]) -> List[str]:
        """Find StatFin table references in content."""
        tables = []

        def search(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key.lower() in ["table", "table_id", "provenance"]:
                        if isinstance(value, str) and "statfin" in value.lower():
                            tables.append(value)
                    search(value)
            elif isinstance(obj, list):
                for item in obj:
                    search(item)

        search(content)
        return tables
