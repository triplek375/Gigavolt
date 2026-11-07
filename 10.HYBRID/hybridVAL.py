#!/usr/bin/env python3
"""
Gigavolt Hybrid Retrieval - Sample Queries Demonstration
=========================================================
Demonstrates cross-source hybrid search combining:
1. SQL Relational Filters (MariaDB: equipment specifications & warranty status)
2. Document Pattern Queries (MongoDB: IoT sensor telemetry & fault codes)
3. Vector Similarity Search (ChromaDB + HNSW: technical documentation embeddings)

Contains practical, high-value field investigation scenarios:
- Scenario 1: Critical Battery Thermal Runaway & Active Warranty Assessment
- Scenario 2: Inverter Overvoltage Surge & Out-of-Warranty Claim Triage
- Scenario 3: Rapid Deep Discharge & Cell Voltage Imbalance Investigation
- Scenario 4: Engineering Change Order (ECO) & BMS Module Degradation
- Scenario 5: Fleet-Wide Thermal Telemetry Anomaly Pattern Investigation
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure 10.HYBRID and project root are in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from hybridSearch import hybrid_search, HybridSearchPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SampleQueries")


# ============================================================================
# SAMPLE QUERY SCENARIOS
# ============================================================================

SAMPLE_SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "scenario_1_thermal_runaway",
        "title": "Scenario 1: Critical Battery Thermal Runaway & Active Warranty Assessment",
        "description": (
            "An operator reports battery overheating. Queries active-warranty units, "
            "scans MongoDB for high-temperature telemetry alerts (>= 65°C, ERR_BMS_701), "
            "and retrieves emergency containment SOPs from technical documentation."
        ),
        "params": {
            "query": "Battery Management System thermal runaway high cell temperature emergency shutdown procedure",
            "equipment_id": "EQ-1001",
            "warranty_status": "ACTIVE",
            "fault_code": "ERR_BMS_701",
            "doc_type": "SOP",
            "n_docs": 3,
            "n_telemetry": 5
        }
    },
    {
        "id": "scenario_2_inverter_overvoltage",
        "title": "Scenario 2: Inverter Overvoltage Surge & Out-of-Warranty Claim Triage",
        "description": (
            "Investigates DC bus overvoltage inverter trips on expired-warranty units. "
            "Correlates historical warranty denial claims with inverter fault telemetry "
            "and technical equipment specifications."
        ),
        "params": {
            "query": "DC-bus overvoltage surge protection trip and inverter IGBT component failure",
            "equipment_id": "EQ-1042",
            "warranty_status": "EXPIRED",
            "fault_code": "ERR_VOLT_102",
            "doc_type": "SPEC",
            "n_docs": 3,
            "n_telemetry": 5
        }
    },
    {
        "id": "scenario_3_deep_discharge",
        "title": "Scenario 3: Rapid Deep Discharge & Cell Voltage Imbalance",
        "description": (
            "Detects units dropping below 5% state-of-charge (SOC). "
            "Retrieves telemetry failure patterns for ERR_BMS_705 and checks "
            "incident reports (INC) on severe cell degradation."
        ),
        "params": {
            "query": "Severe battery pack deep discharge below 5 percent SOC cell balancing failure",
            "fault_code": "ERR_BMS_705",
            "doc_type": "INC",
            "n_docs": 3,
            "n_telemetry": 5
        }
    },
    {
        "id": "scenario_4_bms_hardware_eco",
        "title": "Scenario 4: Engineering Change Order (ECO) & BMS Module Degradation",
        "description": (
            "Identifies flagged hardware components (BMS/MOD) from sensor logs, "
            "verifies customer equipment model specs, and fetches related Engineering "
            "Change Orders (ECO) detailing hardware/firmware revisions."
        ),
        "params": {
            "query": "BMS module cooling fan sensor firmware upgrade and contactor resistance",
            "fault_code": "ERR_BMS_708",
            "doc_type": "ECO",
            "n_docs": 3,
            "n_telemetry": 5
        }
    },
    {
        "id": "scenario_5_fleet_thermal_aggregations",
        "title": "Scenario 5: Fleet-Wide Thermal Telemetry Anomaly Pattern Investigation",
        "description": (
            "Performs a fleet-wide scan across all equipment for thermal patterns. "
            "Aggregates diagnostic telemetry by fault code to find affected units "
            "and matches cooling system maintenance manuals."
        ),
        "params": {
            "query": "High ambient operating temperature thermal management cooling loop fault",
            "doc_type": "MAN",
            "n_docs": 4,
            "n_telemetry": 8
        }
    }
]


# ============================================================================
# EXECUTION & DISPLAY ENGINE
# ============================================================================

def execute_scenario(
    scenario: Dict[str, Any],
    sql_url: Optional[str] = None,
    mongo_uri: Optional[str] = None,
    vector_db_path: Optional[str] = None,
    raw_json: bool = False
) -> Dict[str, Any]:
    """Execute a single hybrid retrieval scenario and display formatted results."""
    params = dict(scenario["params"])
    params["sql_url"] = sql_url
    params["mongo_uri"] = mongo_uri
    params["vector_db_path"] = vector_db_path

    print("\n" + "=" * 80)
    print(f"▶ {scenario['title']}")
    print("=" * 80)
    print(f"Goal: {scenario['description']}")
    print(f"Parameters: {json.dumps(scenario['params'], indent=2)}")
    print("-" * 80)

    result = hybrid_search(**params)

    if raw_json:
        print(json.dumps(result, indent=2))
    else:
        # Display the synthesized unified context
        print(result["unified_context"])

        # Display concise breakdown of information gathered per source
        sources = result["sources"]
        print("\n--- Value Extracted Summary ---")
        eq_count = len(sources.get("sql_equipment", []))
        claims_count = len(sources.get("sql_warranty_claims", []))
        telemetry_count = len(sources.get("mongodb_telemetry_events", []))
        summary_count = len(sources.get("mongodb_telemetry_summary", []))
        docs_count = len(sources.get("vector_technical_docs", []))

        print(f"• SQL Equipment Profiles: {eq_count} matched")
        print(f"• SQL Warranty Claims:   {claims_count} historical claims evaluated")
        print(f"• MongoDB Telemetry:     {telemetry_count} anomaly events isolated")
        print(f"• MongoDB Aggregations:  {summary_count} diagnostic fault summaries")
        print(f"• ChromaDB Vector Docs:  {docs_count} technical documentation chunks matched")

    return result


def run_all_scenarios(
    sql_url: Optional[str] = None,
    mongo_uri: Optional[str] = None,
    vector_db_path: Optional[str] = None,
    raw_json: bool = False
) -> List[Dict[str, Any]]:
    """Execute all defined hybrid search scenarios in sequence."""
    results = []
    print("\n" + "#" * 80)
    print(" GIGAVOLT HYBRID RETRIEVAL - RUNNING ALL SAMPLE SCENARIOS")
    print("#" * 80)

    for scenario in SAMPLE_SCENARIOS:
        res = execute_scenario(
            scenario=scenario,
            sql_url=sql_url,
            mongo_uri=mongo_uri,
            vector_db_path=vector_db_path,
            raw_json=raw_json
        )
        results.append(res)

    print("\n" + "#" * 80)
    print(f" Successfully executed all {len(SAMPLE_SCENARIOS)} hybrid retrieval scenarios!")
    print("#" * 80 + "\n")
    return results


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run sample hybrid search queries across SQL, MongoDB, and Vector DB."
    )
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        default="all",
        help="Scenario index (1-5), scenario ID (e.g. thermal_runaway), or 'all' (default: all)."
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available sample scenarios and exit."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON results instead of formatted markdown context."
    )
    parser.add_argument("--mysql-uri", type=str, default=None, help="Optional MariaDB/MySQL connection URI.")
    parser.add_argument("--mongo-uri", type=str, default=None, help="Optional MongoDB connection URI.")
    parser.add_argument("--vector-db-path", type=str, default=None, help="Optional ChromaDB storage path.")

    args = parser.parse_args()

    if args.list:
        print("\nAvailable Sample Scenarios:")
        for idx, sc in enumerate(SAMPLE_SCENARIOS, start=1):
            print(f"  {idx}. [{sc['id']}] {sc['title']}")
            print(f"     {sc['description']}\n")
        return

    if args.scenario.lower() == "all":
        run_all_scenarios(
            sql_url=args.mysql_uri,
            mongo_uri=args.mongo_uri,
            vector_db_path=args.vector_db_path,
            raw_json=args.json
        )
    else:
        # Resolve requested scenario by number or keyword
        target_scenario = None
        if args.scenario.isdigit():
            idx = int(args.scenario) - 1
            if 0 <= idx < len(SAMPLE_SCENARIOS):
                target_scenario = SAMPLE_SCENARIOS[idx]
        else:
            search_key = args.scenario.lower()
            for sc in SAMPLE_SCENARIOS:
                if search_key in sc["id"].lower() or search_key in sc["title"].lower():
                    target_scenario = sc
                    break

        if not target_scenario:
            print(f"Error: Unknown scenario '{args.scenario}'. Use --list to see available scenarios.")
            sys.exit(1)

        execute_scenario(
            scenario=target_scenario,
            sql_url=args.mysql_uri,
            mongo_uri=args.mongo_uri,
            vector_db_path=args.vector_db_path,
            raw_json=args.json
        )


if __name__ == "__main__":
    main()
