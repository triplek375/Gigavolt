#!/usr/bin/env python3
"""
Gigavolt Hybrid Retrieval Pipeline
==================================
Combines three distinct data sources into a unified retrieval context:
1. Relational SQL Filters (MariaDB): Equipment metadata, specifications, and warranty status.
2. Vector Similarity Search (ChromaDB + HNSW): Technical documentation, manuals, SOPs, and incident reports.
3. Document Queries (MongoDB): IoT telemetry patterns, fault codes, thermal/battery anomalies, and diagnostic aggregations.

Reuses existing database definitions and schemas from:
- 2.SILVER & 3.PAYLOAD (equipment, warrantyClaims, equipmentModels, customers, generated context)
- 7.VECTOR (GigavoltVectorDB, EmbeddingGenerator, all-MiniLM-L6-v2)
- 8.JSON (sensorDB.telemetry, battery failure diagnostics & aggregations)
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, date, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

# Ensure 7.VECTOR and project root are in Python path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent if CURRENT_DIR.name == "10.HYBRID" else CURRENT_DIR
VECTOR_DIR = REPO_ROOT / "7.VECTOR"
for path_entry in [str(VECTOR_DIR), str(REPO_ROOT)]:
    if path_entry not in sys.path:
        sys.path.append(path_entry)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("HybridRetrieval")

# Optional imports with graceful handling
try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except ImportError:
    logger.error("SQLAlchemy is not installed. Install with: pip install sqlalchemy pymysql")
    create_engine, text, Engine = None, None, None

try:
    import pymongo
    from pymongo import MongoClient
except ImportError:
    logger.error("pymongo is not installed. Install with: pip install pymongo")
    MongoClient = None

try:
    from vector_db import GigavoltVectorDB
except ImportError:
    try:
        from vector_db import GigavoltVectorDB
    except Exception as e:
        logger.warning(f"GigavoltVectorDB could not be imported: {e}")
        GigavoltVectorDB = None


# ============================================================================
# 1. SQL RETRIEVAL: EQUIPMENT METADATA & WARRANTY STATUS (MariaDB)
# ============================================================================

class SQLEquipmentRetriever:
    """
    Retrieves equipment metadata, warranty expiration status, and warranty claims
    from MariaDB/MySQL (gigavolt_db) using schemas from 2.SILVER and 3.PAYLOAD.
    """

    DEFAULT_SOCKET_URL = "mysql+pymysql://root@/gigavolt_db?unix_socket=/run/mysqld/mysqld.sock"
    DEFAULT_TCP_URL = "mysql+pymysql://root@localhost:3306/gigavolt_db"

    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url or os.getenv("MYSQL_URI")
        self._engine: Optional[Engine] = None

    def get_engine(self) -> Optional[Engine]:
        """Lazy initialize SQLAlchemy engine with socket and TCP fallbacks."""
        if self._engine is not None:
            return self._engine

        if create_engine is None:
            return None

        candidate_urls = []
        if self.connection_url:
            candidate_urls.append(self.connection_url)
        candidate_urls.extend([
            self.DEFAULT_SOCKET_URL,
            self.DEFAULT_TCP_URL,
            "mysql+pymysql://root:password@localhost/gigavolt_db"
        ])

        for url in candidate_urls:
            try:
                engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info(f"Connected to SQL Database via {url.split('@')[0]}@...")
                self._engine = engine
                return self._engine
            except Exception as e:
                logger.debug(f"Connection attempt to {url} failed: {e}")

        logger.warning("Could not establish connection to MariaDB/MySQL database. SQL retrieval will return empty/mock results.")
        return None

    def query_equipment_metadata(
        self,
        equipment_id: Optional[str] = None,
        model_name: Optional[str] = None,
        warranty_status: Optional[str] = None,  # 'ACTIVE', 'EXPIRED', or None
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query equipment metadata combined with warranty expiration status.
        Uses tables: equipment, equipmentModels, equipmentStatus, customers.
        """
        engine = self.get_engine()
        if engine is None:
            return []

        conditions = ["1=1"]
        params = {"limit": limit}

        if equipment_id:
            conditions.append("e.equipment_id = :equipment_id")
            params["equipment_id"] = equipment_id

        if model_name:
            conditions.append("em.model_name LIKE :model_name")
            params["model_name"] = f"%{model_name}%"

        if warranty_status:
            status_upper = warranty_status.strip().upper()
            if status_upper == "ACTIVE":
                conditions.append("e.warranty_expiration >= CURRENT_DATE()")
            elif status_upper == "EXPIRED":
                conditions.append("e.warranty_expiration < CURRENT_DATE()")

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT 
                e.equipment_id,
                e.serial_number,
                e.install_date,
                e.warranty_expiration,
                CASE 
                    WHEN e.warranty_expiration IS NULL THEN 'UNKNOWN'
                    WHEN e.warranty_expiration >= CURRENT_DATE() THEN 'ACTIVE'
                    ELSE 'EXPIRED'
                END AS warranty_active_status,
                DATEDIFF(e.warranty_expiration, CURRENT_DATE()) AS warranty_days_remaining,
                e.location_notes,
                COALESCE(e.equipment_context, '') AS equipment_context,
                em.model_name,
                em.capacity_kw,
                em.voltage,
                es.status_name AS equipment_status,
                c.customer_id,
                CONCAT(c.first_name, ' ', c.last_name) AS customer_name,
                c.email AS customer_email
            FROM equipment e
            LEFT JOIN equipmentModels em ON e.model_id = em.model_id
            LEFT JOIN equipmentStatus es ON e.status_id = es.status_id
            LEFT JOIN customers c ON e.customer_id = c.customer_id
            WHERE {where_clause}
            ORDER BY e.equipment_id
            LIMIT :limit
        """

        results = []
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql), params).mappings().fetchall()
                for row in rows:
                    item = dict(row)
                    for k, v in item.items():
                        if isinstance(v, (datetime, date)):
                            item[k] = v.isoformat()
                    results.append(item)
        except Exception as e:
            logger.error(f"Error querying equipment metadata: {e}")

        return results

    def query_warranty_claims(
        self,
        equipment_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query warranty claims history for a given equipment ID.
        Uses tables: warrantyClaims, claimStatus, parts.
        """
        engine = self.get_engine()
        if engine is None:
            return []

        sql = """
            SELECT 
                wc.claim_id,
                wc.equipment_id,
                wc.claim_date,
                wc.claim_amount,
                wc.approved_amount,
                cs.status_name AS claim_status,
                COALESCE(wc.denial_reason, '') AS denial_reason,
                COALESCE(wc.claim_notes, '') AS claim_notes,
                COALESCE(wc.claim_context, '') AS claim_context,
                COALESCE(p.part_name, 'N/A') AS part_name
            FROM warrantyClaims wc
            LEFT JOIN claimStatus cs ON wc.status_id = cs.status_id
            LEFT JOIN parts p ON wc.part_id = p.part_id
            WHERE wc.equipment_id = :equipment_id
            ORDER BY wc.claim_date DESC
            LIMIT :limit
        """

        claims = []
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql), {"equipment_id": equipment_id, "limit": limit}).mappings().fetchall()
                for row in rows:
                    item = dict(row)
                    for k, v in item.items():
                        if isinstance(v, (datetime, date)):
                            item[k] = v.isoformat()
                        elif hasattr(v, '__float__'):
                            item[k] = float(v)
                    claims.append(item)
        except Exception as e:
            logger.error(f"Error querying warranty claims for {equipment_id}: {e}")

        return claims


# ============================================================================
# 2. DOCUMENT RETRIEVAL: IOT TELEMETRY PATTERNS (MongoDB)
# ============================================================================

class MongoTelemetryRetriever:
    """
    Retrieves IoT telemetry records and diagnostic failure patterns from MongoDB
    (sensorDB.telemetry) as defined in 8.JSON/import_and_index.sh.
    """

    DEFAULT_MONGO_URI = "mongodb://localhost:27017"
    DB_NAME = "sensorDB"
    COLLECTION_NAME = "telemetry"

    # Known battery failure fault codes from 8.JSON
    BATTERY_FAULT_CODES = ["ERR_BMS_701", "ERR_BMS_705", "ERR_BMS_708", "ERR_VOLT_102"]

    def __init__(self, uri: Optional[str] = None):
        self.uri = uri or os.getenv("MONGO_URI", self.DEFAULT_MONGO_URI)
        self._client: Optional[MongoClient] = None

    def get_collection(self):
        """Lazy initialize MongoDB client and return telemetry collection."""
        if MongoClient is None:
            return None

        if self._client is None:
            try:
                self._client = MongoClient(self.uri, serverSelectionTimeoutMS=2000)
                self._client.admin.command("ping")
                logger.info(f"Connected to MongoDB at {self.uri}")
            except Exception as e:
                logger.warning(f"Could not connect to MongoDB at {self.uri}: {e}")
                self._client = None
                return None

        return self._client[self.DB_NAME][self.COLLECTION_NAME]

    def query_telemetry_patterns(
        self,
        equipment_id: Optional[str] = None,
        fault_code: Optional[Union[str, List[str]]] = None,
        include_battery_anomalies: bool = True,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query IoT telemetry patterns matching equipment and diagnostic criteria.
        Mirrors criteria from 8.JSON/import_and_index.sh:
        - Battery fault codes (ERR_BMS_701, ERR_BMS_705, etc.)
        - Flagged components regex: ^(BMS|CEL|MOD)
        - Notes regex: battery|cell|thermal runaway|discharge
        - Thresholds: temperature_c >= 65, soc_percent <= 5
        """
        coll = self.get_collection()
        if coll is None:
            return []

        query_clauses = []

        if equipment_id:
            query_clauses.append({"equipment_id": equipment_id})

        if fault_code:
            if isinstance(fault_code, list):
                query_clauses.append({"fault_code": {"$in": fault_code}})
            else:
                query_clauses.append({"fault_code": fault_code})

        if include_battery_anomalies and not fault_code:
            diagnostic_or = [
                {"fault_code": {"$in": self.BATTERY_FAULT_CODES}},
                {"flagged_components": {"$regex": "^(BMS|CEL|MOD)", "$options": "i"}},
                {"notes": {"$regex": "battery|cell|thermal runaway|discharge", "$options": "i"}},
                {"telemetry.temperature_c": {"$gte": 65}},
                {"telemetry.soc_percent": {"$lte": 5}}
            ]
            query_clauses.append({"$or": diagnostic_or})

        final_filter = {"$and": query_clauses} if len(query_clauses) > 1 else (query_clauses[0] if query_clauses else {})

        records = []
        try:
            cursor = coll.find(final_filter, {"_id": 0}).sort("timestamp", -1).limit(limit)
            for doc in cursor:
                if "timestamp" in doc and isinstance(doc["timestamp"], (datetime, date)):
                    doc["timestamp"] = doc["timestamp"].isoformat()
                records.append(doc)
        except Exception as e:
            logger.error(f"Error querying telemetry patterns from MongoDB: {e}")

        return records

    def aggregate_fault_summary(
        self,
        equipment_id: Optional[str] = None,
        fault_codes: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Aggregate telemetry diagnostic summary (count, average temperature, average SOC)
        grouped by fault code as defined in 8.JSON.
        """
        coll = self.get_collection()
        if coll is None:
            return []

        codes = fault_codes or self.BATTERY_FAULT_CODES
        match_stage: Dict[str, Any] = {"fault_code": {"$in": codes}}
        if equipment_id:
            match_stage["equipment_id"] = equipment_id

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": "$fault_code",
                    "count": {"$sum": 1},
                    "avg_temp": {"$avg": "$telemetry.temperature_c"},
                    "avg_soc": {"$avg": "$telemetry.soc_percent"},
                    "equipment_affected": {"$addToSet": "$equipment_id"}
                }
            },
            {"$sort": {"count": -1}}
        ]

        summary = []
        try:
            results = coll.aggregate(pipeline)
            for doc in results:
                summary.append({
                    "fault_code": doc.get("_id"),
                    "count": doc.get("count", 0),
                    "avg_temp_c": round(doc.get("avg_temp", 0.0), 2) if doc.get("avg_temp") is not None else None,
                    "avg_soc_percent": round(doc.get("avg_soc", 0.0), 2) if doc.get("avg_soc") is not None else None,
                    "equipment_count": len(doc.get("equipment_affected", []))
                })
        except Exception as e:
            logger.error(f"Error running telemetry aggregation: {e}")

        return summary


# ============================================================================
# 3. VECTOR SIMILARITY RETRIEVAL: TECHNICAL DOCUMENTATION (ChromaDB + HNSW)
# ============================================================================

class VectorDocRetriever:
    """
    Executes dense vector similarity search over technical documentation embeddings
    using GigavoltVectorDB and SentenceTransformers (all-MiniLM-L6-v2) from 7.VECTOR.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = db_path
        elif os.getenv("VECTOR_DB_PATH"):
            self.db_path = os.getenv("VECTOR_DB_PATH")
        elif Path("/opt/undata/gigavolt_vectordb").exists():
            self.db_path = "/opt/undata/gigavolt_vectordb"
        elif (REPO_ROOT / "gigavolt_vectordb").exists():
            self.db_path = str(REPO_ROOT / "gigavolt_vectordb")
        else:
            self.db_path = db_path
        self._vector_db: Optional[Any] = None

    def get_vector_db(self) -> Optional[Any]:
        """Lazy load GigavoltVectorDB instance."""
        if self._vector_db is not None:
            return self._vector_db

        if GigavoltVectorDB is None:
            return None

        try:
            self._vector_db = GigavoltVectorDB(db_path=self.db_path)
            self._vector_db.create_or_get_collection()
            logger.info("Initialized GigavoltVectorDB collection successfully.")
            return self._vector_db
        except Exception as e:
            logger.warning(f"Could not initialize GigavoltVectorDB: {e}. Vector search will return empty results.")
            return None

    def search_documents(
        self,
        query: str,
        n_results: int = 5,
        doc_type: Optional[str] = None,
        where_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute vector similarity search for technical manuals, SOPs, and incident reports.
        """
        vdb = self.get_vector_db()
        if vdb is None:
            return []

        try:
            raw_results = vdb.query(
                query_text=query,
                n_results=n_results,
                doc_type=doc_type,
                where_filter=where_filter
            )

            hits = []
            if raw_results and "ids" in raw_results and raw_results["ids"]:
                ids = raw_results["ids"][0]
                docs = raw_results.get("documents", [[]])[0]
                metas = raw_results.get("metadatas", [[]])[0]
                distances = raw_results.get("distances", [[]])[0] if "distances" in raw_results else [0.0] * len(ids)

                for idx in range(len(ids)):
                    hits.append({
                        "id": ids[idx],
                        "text": docs[idx] if idx < len(docs) else "",
                        "metadata": metas[idx] if idx < len(metas) else {},
                        "distance": round(float(distances[idx]), 4) if idx < len(distances) else None,
                        "similarity_score": round(1.0 - float(distances[idx]), 4) if idx < len(distances) else None
                    })
            return hits
        except Exception as e:
            logger.error(f"Error during vector similarity search for '{query}': {e}")
            return []


# ============================================================================
# 4. UNIFIED HYBRID RETRIEVAL PIPELINE
# ============================================================================

class HybridRetrievalPipeline:
    """
    Unified retrieval pipeline orchestrating:
    - SQL Filters (Equipment metadata, warranty expiration & claims)
    - Document Queries (IoT Telemetry patterns & failure diagnostics)
    - Vector Similarity Search (Technical documentation & SOPs)
    """

    def __init__(
        self,
        sql_url: Optional[str] = None,
        mongo_uri: Optional[str] = None,
        vector_db_path: Optional[str] = None
    ):
        self.sql_retriever = SQLEquipmentRetriever(connection_url=sql_url)
        self.telemetry_retriever = MongoTelemetryRetriever(uri=mongo_uri)
        self.vector_retriever = VectorDocRetriever(db_path=vector_db_path)

    def retrieve(
        self,
        query: str,
        equipment_id: Optional[str] = None,
        warranty_status: Optional[str] = None,
        fault_code: Optional[Union[str, List[str]]] = None,
        doc_type: Optional[str] = None,
        n_docs: int = 5,
        n_telemetry: int = 10
    ) -> Dict[str, Any]:
        """
        Unified hybrid retrieval function combining all three data sources.

        Args:
            query: Natural language search query or symptom description.
            equipment_id: Optional equipment identifier (e.g. 'EQ-1001').
            warranty_status: Optional filter ('ACTIVE', 'EXPIRED', or None).
            fault_code: Optional telemetry fault code filter (e.g. 'ERR_BMS_701').
            doc_type: Optional documentation type ('INC', 'MAN', 'SOP', 'ECO', 'SPEC').
            n_docs: Max technical documentation chunks to retrieve.
            n_telemetry: Max telemetry log records to retrieve.

        Returns:
            Dictionary containing combined context from SQL, Vector DB, and MongoDB,
            along with a pre-formatted unified prompt context string.
        """
        logger.info(f"Executing hybrid retrieval pipeline for query='{query}', equipment_id={equipment_id}...")

        # 1. SQL: Fetch Equipment Metadata & Warranty Status
        equipment_list = []
        warranty_claims = []
        if equipment_id:
            equipment_list = self.sql_retriever.query_equipment_metadata(
                equipment_id=equipment_id,
                warranty_status=warranty_status,
                limit=1
            )
            warranty_claims = self.sql_retriever.query_warranty_claims(
                equipment_id=equipment_id,
                limit=5
            )
        else:
            equipment_list = self.sql_retriever.query_equipment_metadata(
                warranty_status=warranty_status,
                limit=5
            )

        # 2. MongoDB: Fetch IoT Telemetry Patterns & Diagnostics
        telemetry_events = self.telemetry_retriever.query_telemetry_patterns(
            equipment_id=equipment_id,
            fault_code=fault_code,
            include_battery_anomalies=True,
            limit=n_telemetry
        )
        telemetry_summary = self.telemetry_retriever.aggregate_fault_summary(
            equipment_id=equipment_id,
            fault_codes=[fault_code] if isinstance(fault_code, str) else fault_code
        )

        # 3. Vector DB: Fetch Technical Documentation Embeddings
        augmented_query = query
        if telemetry_events and "fault_code" in telemetry_events[0]:
            augmented_query = f"{query} {telemetry_events[0]['fault_code']}"

        technical_docs = self.vector_retriever.search_documents(
            query=augmented_query,
            n_results=n_docs,
            doc_type=doc_type
        )

        # 4. Formulate Unified Retrieval Payload
        unified_result = {
            "query": query,
            "augmented_query": augmented_query,
            "equipment_id": equipment_id,
            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources": {
                "sql_equipment": equipment_list,
                "sql_warranty_claims": warranty_claims,
                "mongodb_telemetry_events": telemetry_events,
                "mongodb_telemetry_summary": telemetry_summary,
                "vector_technical_docs": technical_docs
            }
        }

        # Build formatted context block for LLM consumption
        unified_result["unified_context"] = self._format_unified_context(unified_result)
        return unified_result

    def _format_unified_context(self, result: Dict[str, Any]) -> str:
        """
        Synthesizes the gathered context into a structured Markdown string
        ideal for LLM prompt augmentation and technician triage.
        """
        lines = []
        lines.append("=== GIGAVOLT UNIFIED RETRIEVAL CONTEXT ===")
        lines.append(f"Query: {result['query']}")
        if result.get("equipment_id"):
            lines.append(f"Target Equipment: {result['equipment_id']}")
        lines.append(f"Timestamp: {result['retrieval_timestamp']}\n")

        # 1. SQL Context: Equipment Metadata & Warranty Status
        lines.append("--- [SOURCE 1: SQL EQUIPMENT & WARRANTY STATUS] ---")
        eq_list = result["sources"].get("sql_equipment", [])
        if eq_list:
            for eq in eq_list:
                status_note = f"Status: {eq.get('equipment_status', 'Unknown')}"
                warranty_note = f"Warranty: {eq.get('warranty_active_status', 'N/A')} (Expires: {eq.get('warranty_expiration', 'N/A')})"
                specs = f"Model: {eq.get('model_name', 'Unknown')} | Capacity: {eq.get('capacity_kw', 'N/A')} kW | Voltage: {eq.get('voltage', 'N/A')} V"
                customer = f"Customer: {eq.get('customer_name', 'Unknown')} ({eq.get('customer_email', 'N/A')})"
                lines.append(f"- Unit [{eq.get('equipment_id', 'Unknown')}]: {specs}")
                lines.append(f"  {status_note} | {warranty_note}")
                lines.append(f"  {customer}")
                if eq.get("location_notes"):
                    lines.append(f"  Notes: {eq.get('location_notes')}")
                if eq.get("equipment_context"):
                    lines.append(f"  Profile Context: {eq.get('equipment_context')}")
        else:
            lines.append("No matching equipment records found in SQL database.")

        claims = result["sources"].get("sql_warranty_claims", [])
        if claims:
            lines.append("\nRecent Warranty Claims:")
            for cl in claims:
                lines.append(f"  * Claim {cl.get('claim_id')}: {cl.get('claim_status')} | Part: {cl.get('part_name')} | Amount: ${cl.get('claim_amount')} | Date: {cl.get('claim_date')}")
                if cl.get("claim_notes"):
                    lines.append(f"    Notes: {cl.get('claim_notes')}")
                if cl.get("denial_reason"):
                    lines.append(f"    Denial Reason: {cl.get('denial_reason')}")

        lines.append("")

        # 2. MongoDB Context: IoT Telemetry Patterns
        lines.append("--- [SOURCE 2: IOT TELEMETRY & DIAGNOSTIC PATTERNS] ---")
        telemetry = result["sources"].get("mongodb_telemetry_events", [])
        if telemetry:
            lines.append(f"Retrieved {len(telemetry)} recent diagnostic telemetry records:")
            for te in telemetry[:5]:
                fault = te.get("fault_code", "UNKNOWN")
                ts = te.get("timestamp", "N/A")
                t_data = te.get("telemetry", {})
                temp = f"{t_data.get('temperature_c', 'N/A')}°C" if "temperature_c" in t_data else "N/A"
                soc = f"{t_data.get('soc_percent', 'N/A')}%" if "soc_percent" in t_data else "N/A"
                flagged = te.get("flagged_components", "None")
                notes = te.get("notes", "")
                lines.append(f"- [{ts}] Equipment: {te.get('equipment_id')} | Fault: {fault} | Temp: {temp} | SOC: {soc} | Component: {flagged}")
                if notes:
                    lines.append(f"  Log Note: {notes}")
        else:
            lines.append("No anomalous IoT telemetry patterns found.")

        summary = result["sources"].get("mongodb_telemetry_summary", [])
        if summary:
            lines.append("\nDiagnostic Summary by Fault Code:")
            for sm in summary:
                lines.append(f"  * {sm.get('fault_code')}: Count={sm.get('count')} | Avg Temp={sm.get('avg_temp_c')}°C | Avg SOC={sm.get('avg_soc_percent')}% | Units Affected={sm.get('equipment_count')}")

        lines.append("")

        # 3. Vector DB Context: Technical Documentation
        lines.append("--- [SOURCE 3: TECHNICAL DOCUMENTATION EMBEDDINGS] ---")
        docs = result["sources"].get("vector_technical_docs", [])
        if docs:
            for i, doc in enumerate(docs, start=1):
                meta = doc.get("metadata", {})
                doc_id = meta.get("doc_id", "DOC")
                doc_title = meta.get("doc_title", meta.get("source_file", "Technical Manual"))
                score = doc.get("similarity_score", "N/A")
                lines.append(f"- Result {i} [{doc_id} - {doc_title}] (Similarity: {score}):")
                snippet = doc.get("text", "").strip()
                if len(snippet) > 300:
                    snippet = snippet[:300] + "..."
                lines.append(f"  \"{snippet}\"")
        else:
            lines.append("No vector similarity matches found in technical documentation.")

        lines.append("\n=== END OF CONTEXT ===")
        return "\n".join(lines)


# ============================================================================
# 5. STANDALONE FUNCTION WRAPPER
# ============================================================================

def hybrid_retrieval(
    query: str,
    equipment_id: Optional[str] = None,
    warranty_status: Optional[str] = None,
    fault_code: Optional[Union[str, List[str]]] = None,
    doc_type: Optional[str] = None,
    n_docs: int = 5,
    n_telemetry: int = 10,
    sql_url: Optional[str] = None,
    mongo_uri: Optional[str] = None,
    vector_db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function executing the hybrid retrieval pipeline.

    Combines:
    - SQL Filters (equipment metadata, warranty status)
    - Vector similarity search (technical documentation embeddings)
    - Document queries (IoT telemetry patterns)
    """
    pipeline = HybridRetrievalPipeline(
        sql_url=sql_url,
        mongo_uri=mongo_uri,
        vector_db_path=vector_db_path
    )
    return pipeline.retrieve(
        query=query,
        equipment_id=equipment_id,
        warranty_status=warranty_status,
        fault_code=fault_code,
        doc_type=doc_type,
        n_docs=n_docs,
        n_telemetry=n_telemetry
    )


# Aliases for hybrid_search naming
hybrid_search = hybrid_retrieval
HybridSearchPipeline = HybridRetrievalPipeline


# ============================================================================
# 6. COMMAND LINE INTERFACE (CLI)
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Gigavolt Hybrid Retrieval Pipeline - Combines SQL metadata, Vector embeddings, and IoT telemetry."
    )
    parser.add_argument("--query", "-q", type=str, required=True, help="Natural language query or problem description.")
    parser.add_argument("--equipment-id", "-e", type=str, default=None, help="Specific equipment ID to filter (e.g. EQ-1001).")
    parser.add_argument("--warranty-status", "-w", type=str, choices=["ACTIVE", "EXPIRED", "ANY"], default=None, help="Filter by warranty expiration status.")
    parser.add_argument("--fault-code", "-f", type=str, default=None, help="Filter by specific IoT fault code (e.g. ERR_BMS_701).")
    parser.add_argument("--doc-type", "-d", type=str, choices=["ECO", "INC", "MAN", "SOP", "SPEC", "SUP"], default=None, help="Filter documentation by type.")
    parser.add_argument("--limit-docs", type=int, default=5, help="Number of vector documentation chunks to retrieve.")
    parser.add_argument("--limit-telemetry", type=int, default=10, help="Number of IoT telemetry records to retrieve.")
    parser.add_argument("--json", action="store_true", help="Output complete results in JSON format.")
    parser.add_argument("--mysql-uri", type=str, default=None, help="Optional MySQL/MariaDB connection URI.")
    parser.add_argument("--mongo-uri", type=str, default=None, help="Optional MongoDB connection URI.")
    parser.add_argument("--vector-db-path", type=str, default=None, help="Optional ChromaDB storage path.")

    args = parser.parse_args()

    warranty_filter = None if args.warranty_status == "ANY" else args.warranty_status

    results = hybrid_retrieval(
        query=args.query,
        equipment_id=args.equipment_id,
        warranty_status=warranty_filter,
        fault_code=args.fault_code,
        doc_type=args.doc_type,
        n_docs=args.limit_docs,
        n_telemetry=args.limit_telemetry,
        sql_url=args.mysql_uri,
        mongo_uri=args.mongo_uri,
        vector_db_path=args.vector_db_path
    )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(results["unified_context"])


if __name__ == "__main__":
    main()
