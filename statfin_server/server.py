from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager
import json
import asyncio

from mcp.server.fastmcp import FastMCP
from .client import StatFinClient

# Global client
statfin_client: Optional[StatFinClient] = None

@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Manage server lifecycle."""
    global statfin_client
    statfin_client = StatFinClient()
    yield
    await statfin_client.close()

mcp = FastMCP("StatFin API Server", lifespan=server_lifespan)

@mcp.tool()
async def list_statfin_items(path: str = "") -> str:
    """
    List folders and tables in the Statistics Finland database.
    
    Args:
        path: Relative path to browse (e.g., "asu/ashi/" for housing prices). 
              Leave empty for root.
    """
    if not statfin_client:
        return "Error: Client not initialized"
    
    try:
        items = await statfin_client.list_items(path)
        
        output = f"Contents of '{path or 'root'}':\n"
        for item in items:
            item_type = "Folder" if item.get("type") == "l" else "Table"
            output += f"- [{item_type}] {item['text']} (ID: {item['id']})\n"
            
        return output
    except Exception as e:
        return f"Error listing items: {str(e)}"

@mcp.tool()
async def get_table_info(table_path: str) -> str:
    """
    Get metadata and variable options for a specific table.
    Returns a JSON object with variable codes, labels, and value examples.
    
    Args:
        table_path: Path to the table (e.g., "asu/ashi/statfin_ashi_pxt_13mt.px")
    """
    if not statfin_client:
        return "Error: Client not initialized"
        
    try:
        meta = await statfin_client.get_table_metadata(table_path)
        
        info = {
            "title": meta.get("title"),
            "variables": []
        }
        
        for var in meta.get("variables", []):
            code = var["code"]
            is_time = var.get("time", False) or code.lower() in [
                "vuosi", "year", "vuosineljännes", "quarter", "kuukausi", "month"
            ]
            
            var_info = {
                "code": code,
                "text": var["text"],
                "supportsLatest": is_time,
                "values": []
            }
            
            values = var.get('values', [])
            value_texts = var.get('valueTexts', [])
            
            if values:
                if len(values) > 10:
                    indices = list(range(3)) + list(range(len(values)-3, len(values)))
                else:
                    indices = range(len(values))
                
                for i in indices:
                    if 0 <= i < len(values):
                        var_info["values"].append({
                            "id": values[i],
                            "text": value_texts[i] if i < len(value_texts) else values[i]
                        })
                
                var_info["total_values"] = len(values)
            
            info["variables"].append(var_info)
            
        return json.dumps(info, indent=2)
    except Exception as e:
        return f"Error getting metadata: {str(e)}"

@mcp.tool()
async def get_filters_template(table_path: str) -> str:
    """
    Returns a canonical, copy-pasteable filter object for a given table.
    Use this to get a valid starting point for your query.
    
    Args:
        table_path: Path to the table.
    """
    if not statfin_client:
        return "Error: Client not initialized"
        
    try:
        meta = await statfin_client.get_table_metadata(table_path)
        
        filters = {}
        notes = {}
        
        for var in meta.get("variables", []):
            code = var["code"]
            values = var.get("values", [])
            
            is_time = var.get("time", False) or code.lower() in [
                "vuosi", "year", "vuosineljännes", "quarter", "kuukausi", "month"
            ]
            
            if is_time:
                filters[code] = ["latest"]
                notes[code] = "Use 'latest' to fetch the most recent data point."
            elif len(values) > 0:
                if "SSS" in values:
                    filters[code] = ["SSS"]
                else:
                    filters[code] = [values[0]]
            else:
                filters[code] = []
                
        return json.dumps({
            "filters": filters,
            "notes": notes,
            "available_variables": [v["code"] for v in meta.get("variables", [])]
        }, indent=2)
        
    except Exception as e:
        return f"Error generating template: {str(e)}"

@mcp.tool()
async def batch_fetch_statfin_data(table_path: str, filters_array: List[Dict[str, Any]]) -> str:
    """
    Fetch multiple queries in a batch.
    
    Args:
        table_path: Path to the table.
        filters_array: List of filter objects.
    """
    if not statfin_client:
        return "Error: Client not initialized"
        
    results = []
    errors = []
    
    for i, filters in enumerate(filters_array):
        try:
            normalized = {}
            for k, v in filters.items():
                if isinstance(v, str):
                    normalized[k] = [v]
                elif isinstance(v, list):
                    normalized[k] = [str(x) for x in v]
                else:
                    normalized[k] = [str(v)]
            
            if i == 0:
                meta = await statfin_client.get_table_metadata(table_path)
            
            final_filters = {}
            for code, values in normalized.items():
                if "latest" in values:
                    var_meta = next((v for v in meta["variables"] if v["code"] == code), None)
                    if var_meta:
                        latest_val = var_meta["values"][-1]
                        final_filters[code] = [latest_val if v == "latest" else v for v in values]
                    else:
                        final_filters[code] = values
                else:
                    final_filters[code] = values

            query = {
                "query": [],
                "response": {"format": "json-stat2"}
            }
            for code, values in final_filters.items():
                query["query"].append({
                    "code": code,
                    "selection": {
                        "filter": "item",
                        "values": values
                    }
                })
            
            data = await statfin_client.fetch_data(table_path, query)
            results.append(data)
            
        except Exception as e:
            errors.append(f"Item {i} failed: {str(e)}")
            results.append(None)
            
    return json.dumps({"results": results, "errors": errors}, indent=2)

@mcp.tool()
async def fetch_statfin_data(table_path: str, filters: Any) -> str:
    """
    Fetch PXWeb data for a single query. filters must be an object of arrays.
    
    Args:
        table_path: Path to the table (e.g., "vaerak/statfin_vaerak_pxt_11rm.px")
        filters: Object mapping variable codes to arrays of strings.
                 Example: { "Alue": ["KU753"], "Vuosi": ["latest"], "Tiedot": ["vaesto"] }
    """
    if not statfin_client:
        return "Error: Client not initialized"

    if isinstance(filters, list):
        return (
            "Error: You passed an array to fetch_statfin_data. "
            "Please use batch_fetch_statfin_data for multiple queries, "
            "or pass a single object for a single query."
        )
    
    if not isinstance(filters, dict):
        return "Error: filters must be an object (dictionary) mapping variable codes to arrays of strings."

    try:
        normalized_filters = {}
        for key, value in filters.items():
            if isinstance(value, str):
                normalized_filters[key] = [value]
            elif isinstance(value, (int, float)):
                normalized_filters[key] = [str(value)]
            elif isinstance(value, list):
                normalized_filters[key] = [str(v) for v in value]
            else:
                return f"Error: Invalid value type for filter '{key}'. Expected string or list of strings."

        meta = await statfin_client.get_table_metadata(table_path)
        
        final_filters = {}
        meta_vars = {v["code"]: v for v in meta["variables"]}
        
        for code, values in normalized_filters.items():
            if code not in meta_vars:
                return f"Error: Unknown variable '{code}'. Valid variables: {', '.join(meta_vars.keys())}"
            
            var_meta = meta_vars[code]
            resolved_values = []
            
            for val in values:
                if val == "latest":
                    if var_meta.get("values"):
                        resolved_values.append(var_meta["values"][-1])
                    else:
                        return f"Error: Cannot resolve 'latest' for variable '{code}' (no values found)."
                else:
                    resolved_values.append(val)
            
            final_filters[code] = resolved_values

        query = {
            "query": [],
            "response": {"format": "json-stat2"}
        }
        
        for code, values in final_filters.items():
            query["query"].append({
                "code": code,
                "selection": {
                    "filter": "item",
                    "values": values
                }
            })
            
        data = await statfin_client.fetch_data(table_path, query)
        return json.dumps(data, indent=2)
        
    except Exception as e:
        return f"Error fetching data: {str(e)}"

if __name__ == "__main__":
    mcp.run()
