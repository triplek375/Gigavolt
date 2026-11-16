"""
Gigavolt Optimized Hybrid Retrieval Pipeline
==========================================================
Combines three distinct data sources into a unified retrieval context with:
1. Parallel Multi-Database Execution (ThreadPoolExecutor across SQL, MongoDB, ChromaDB)
2. Intelligent LRU + TTL Caching for query embeddings and retrieval payloads
3. Granular Stage Latency Profiling (SQL ms, MongoDB ms, Vector ms)
4. Standardized 5-Field Provenance Metadata on every record:
   (database_type, record_id, document_name, chunk_id, timestamp)
"""

import os
import sys
import time
import json
import hashlib
import logging
import argparse
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent if CURRENT_DIR.name == "10.HYBRID" else CURRENT_DIR
VECTOR_DIR = REPO_ROOT / "7.VECTOR"
for path_entry in [str(CURRENT_DIR), str(VECTOR_DIR), str(REPO_ROOT), "/opt/scripts"]:
    if Path(path_entry).exists() and path_entry not in sys.path:
        sys.path.append(path_entry)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("HybridRetrieval")

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except ImportError:
    create_engine, text, Engine = None, None, None

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

try:
    from vector_db import GigavoltVectorDB
except Exception:
    GigavoltVectorDB = None


# ============================================================================
# THREAD-SAFE LRU + TTL CACHE FOR QUERY & EMBEDDING OPTIMIZATION
# ============================================================================
class LRUTTLCache:
    def __init__(self, maxsize: int = 256, ttl_seconds: float = 600.0):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._store:
                self.misses += 1
                return None
            val, ts = self._store[key]
            if (time.time() - ts) > self.ttl:
                del self._store[key]
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return val

    def set(self, key: str, value: Any):
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, time.time())
            if len(self._store) > self.maxsize:
                self._store.popitem(last=False)

    def clear(self):
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "size": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_pct": round((self.hits / total * 100), 2) if total > 0 else 0.0
        }


GLOBAL_RETRIEVAL_CACHE = LRUTTLCache(maxsize=512, ttl_seconds=900.0)
GLOBAL_EMBEDDING_CACHE = LRUTTLCache(maxsize=512, ttl_seconds=3600.0)


def clear_global_cache():
    """Called by pipeline_dag.py after incremental updates to ensure fresh data."""
    GLOBAL_RETRIEVAL_CACHE.clear()
    GLOBAL_EMBEDDING_CACHE.clear()
    logger.info("Cleared global hybrid retrieval and embedding caches.")


# ============================================================================
# 1. SQL RETRIEVAL: EQUIPMENT, CLAIMS, DISPATCH HISTORY & PARTS (MariaDB)
# ============================================================================
class SQLEquipmentRetriever:
    DEFAULT_SOCKET_URL = "mysql+pymysql://root@/gigavolt_db?unix_socket=/run/mysqld/mysqld.sock"
    DEFAULT_TCP_URL = "mysql+pymysql://root@localhost:3306/gigavolt_db"
    _shared_engine: Optional[Engine] = None

    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url or os.getenv("MYSQL_URI")
        self._engine: Optional[Engine] = None
        self._connect_failed = False

    def get_engine(self) -> Optional[Engine]:
        if self._engine is not None:
            return self._engine
        if SQLEquipmentRetriever._shared_engine is not None and not self.connection_url:
            self._engine = SQLEquipmentRetriever._shared_engine
            return self._engine
        if create_engine is None or self._connect_failed:
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
                engine = create_engine(
                    url,
                    pool_size=8,
                    max_overflow=16,
                    pool_pre_ping=True,
                    connect_args={"connect_timeout": 2}
                )
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self._engine = engine
                if not self.connection_url:
                    SQLEquipmentRetriever._shared_engine = engine
                return self._engine
            except Exception:
                continue

        self._connect_failed = True
        return None

    def query_equipment_metadata(
        self,
        equipment_id: Optional[str] = None,
        serial_number: Optional[str] = None,
        model_name: Optional[str] = None,
        warranty_status: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        engine = self.get_engine()
        if engine is None:
            return []

        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit}

        if equipment_id:
            conditions.append("e.equipment_id = :equipment_id")
            params["equipment_id"] = equipment_id
        if serial_number:
            conditions.append("e.serial_number = :serial_number")
            params["serial_number"] = serial_number
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
                c.email AS customer_email,
                comp.company_name,
                ci.city_name,
                st.state_name
            FROM equipment e
            LEFT JOIN equipmentModels em ON e.model_id = em.model_id
            LEFT JOIN equipmentStatus es ON e.status_id = es.status_id
            LEFT JOIN customers c ON e.customer_id = c.customer_id
            LEFT JOIN companies comp ON c.company_id = comp.company_id
            LEFT JOIN locations loc ON c.location_id = loc.location_id
            LEFT JOIN cities ci ON loc.city_id = ci.city_id
            LEFT JOIN states st ON ci.state_id = st.state_id
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
                        elif hasattr(v, "__float__"):
                            item[k] = float(v)
                    eq_id = item.get("equipment_id", "EQ-UNKNOWN")
                    ts = item.get("install_date") or "2025-01-01"
                    item["provenance_meta"] = {
                        "database_type": "MariaDB",
                        "record_id": eq_id,
                        "document_name": "gigavolt_db.equipment",
                        "chunk_id": f"SQL_EQ_{eq_id}",
                        "timestamp": str(ts)
                    }
                    results.append(item)
        except Exception as e:
            logger.error(f"Error querying equipment metadata: {e}")
        return results

    def query_warranty_claims(
        self,
        equipment_id: Optional[str] = None,
        serial_number: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        engine = self.get_engine()
        if engine is None:
            return []

        conditions = []
        params: Dict[str, Any] = {"limit": limit}
        if equipment_id:
            conditions.append("wc.equipment_id = :equipment_id")
            params["equipment_id"] = equipment_id
        if serial_number:
            conditions.append("e.serial_number = :serial_number")
            params["serial_number"] = serial_number

        where_expr = f"WHERE {' OR '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT 
                wc.claim_id,
                wc.equipment_id,
                wc.dispatch_id,
                wc.claim_date,
                wc.claim_amount,
                wc.approved_amount,
                cs.status_name AS claim_status,
                COALESCE(wc.denial_reason, '') AS denial_reason,
                COALESCE(wc.claim_notes, '') AS claim_notes,
                COALESCE(p.part_id, 'N/A') AS part_id,
                COALESCE(p.part_name, 'N/A') AS part_name,
                COALESCE(p.unit_price, 0.0) AS part_unit_price
            FROM warrantyClaims wc
            LEFT JOIN equipment e ON wc.equipment_id = e.equipment_id
            LEFT JOIN claimStatus cs ON wc.status_id = cs.status_id
            LEFT JOIN parts p ON wc.part_id = p.part_id
            {where_expr}
            ORDER BY wc.claim_date DESC
            LIMIT :limit
        """

        claims = []
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql), params).mappings().fetchall()
                for row in rows:
                    item = dict(row)
                    for k, v in item.items():
                        if isinstance(v, (datetime, date)):
                            item[k] = v.isoformat()
                        elif hasattr(v, "__float__"):
                            item[k] = float(v)
                    cid = item.get("claim_id", "CLM-UNKNOWN")
                    ts = item.get("claim_date") or "2025-01-01"
                    item["provenance_meta"] = {
                        "database_type": "MariaDB",
                        "record_id": cid,
                        "document_name": "gigavolt_db.warrantyClaims",
                        "chunk_id": f"SQL_CLM_{cid}",
                        "timestamp": str(ts)
                    }
                    claims.append(item)
        except Exception as e:
            logger.error(f"Error querying warranty claims: {e}")
        return claims

    def query_dispatches_history(
        self,
        equipment_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieves chronological service dispatches for temporal & multi-hop queries."""
        engine = self.get_engine()
        if engine is None:
            return []

        where_clause = "WHERE d.equipment_id = :equipment_id" if equipment_id else ""
        params: Dict[str, Any] = {"limit": limit}
        if equipment_id:
            params["equipment_id"] = equipment_id

        sql = f"""
            SELECT
                d.dispatch_id,
                d.equipment_id,
                d.dispatch_date,
                CONCAT(t.first_name, ' ', t.last_name) AS technician_name,
                st.service_type_name AS service_type,
                d.hours_spent,
                d.labor_cost,
                d.resolution_summary,
                ds.status_name AS dispatch_status
            FROM dispatches d
            LEFT JOIN technicians t ON d.technician_id = t.technician_id
            LEFT JOIN serviceTypes st ON d.service_type_id = st.service_type_id
            LEFT JOIN dispatchStatus ds ON d.status_id = ds.status_id
            {where_clause}
            ORDER BY d.dispatch_date DESC
            LIMIT :limit
        """
        dispatches = []
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql), params).mappings().fetchall()
                for row in rows:
                    item = dict(row)
                    for k, v in item.items():
                        if isinstance(v, (datetime, date)):
                            item[k] = v.isoformat()
                        elif hasattr(v, "__float__"):
                            item[k] = float(v)
                    did = item.get("dispatch_id", "DSP-UNKNOWN")
                    ts = item.get("dispatch_date") or "2025-01-01"
                    item["provenance_meta"] = {
                        "database_type": "MariaDB",
                        "record_id": did,
                        "document_name": "gigavolt_db.dispatches",
                        "chunk_id": f"SQL_DSP_{did}",
                        "timestamp": str(ts)
                    }
                    dispatches.append(item)
        except Exception as e:
            logger.error(f"Error querying dispatches history: {e}")
        return dispatches


# ============================================================================
# 2. DOCUMENT RETRIEVAL: IOT TELEMETRY PATTERNS (MongoDB)
# ============================================================================
class MongoTelemetryRetriever:
    DEFAULT_MONGO_URI = "mongodb://localhost:27017"
    DB_NAME = "sensorDB"
    COLLECTION_NAME = "telemetry"
    BATTERY_FAULT_CODES = ["ERR_BMS_701", "ERR_BMS_705", "ERR_BMS_708", "ERR_VOLT_102"]
    _shared_client: Optional[Any] = None

    def __init__(self, uri: Optional[str] = None):
        self.uri = uri or os.getenv("MONGO_URI", self.DEFAULT_MONGO_URI)
        self._client = None
        self._connect_failed = False

    def get_collection(self):
        if MongoClient is None or self._connect_failed:
            return None
        if self._client is None:
            if MongoTelemetryRetriever._shared_client is not None:
                self._client = MongoTelemetryRetriever._shared_client
            else:
                try:
                    self._client = MongoClient(self.uri, serverSelectionTimeoutMS=800, maxPoolSize=16)
                    self._client.admin.command("ping")
                    MongoTelemetryRetriever._shared_client = self._client
                except Exception:
                    self._connect_failed = True
                    return None
        return self._client[self.DB_NAME][self.COLLECTION_NAME]

    def query_telemetry_patterns(
        self,
        equipment_id: Optional[str] = None,
        fault_code: Optional[Union[str, List[str]]] = None,
        include_battery_anomalies: bool = True,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
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
        elif include_battery_anomalies and not equipment_id:
            query_clauses.append({"fault_code": {"$in": self.BATTERY_FAULT_CODES}})

        final_filter = {"$and": query_clauses} if len(query_clauses) > 1 else (query_clauses[0] if query_clauses else {})

        records = []
        try:
            cursor = coll.find(final_filter, {"_id": 0}).sort("timestamp", -1).limit(limit)
            for idx, doc in enumerate(cursor):
                if "timestamp" in doc and isinstance(doc["timestamp"], (datetime, date)):
                    doc["timestamp"] = doc["timestamp"].isoformat()
                eq_id = doc.get("equipment_id", "EQ-IOT")
                f_code = doc.get("fault_code", "ERR_IOT")
                ts = str(doc.get("timestamp", "2026-01-01T00:00:00Z"))
                doc["provenance_meta"] = {
                    "database_type": "MongoDB",
                    "record_id": f"{eq_id}:{f_code}",
                    "document_name": "sensorDB.telemetry",
                    "chunk_id": f"MONGO_TEL_{eq_id}_{idx}",
                    "timestamp": ts
                }
                records.append(doc)
        except Exception as e:
            logger.error(f"Error querying MongoDB telemetry: {e}")
        return records

    def aggregate_fault_summary(
        self,
        equipment_id: Optional[str] = None,
        fault_codes: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
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
                    "latest_ts": {"$max": "$timestamp"},
                    "equipment_affected": {"$addToSet": "$equipment_id"}
                }
            },
            {"$sort": {"count": -1}}
        ]

        summary = []
        try:
            for doc in coll.aggregate(pipeline):
                fcode = doc.get("_id", "ERR_BMS")
                ts = str(doc.get("latest_ts") or "2026-01-01T00:00:00Z")
                summary.append({
                    "fault_code": fcode,
                    "count": doc.get("count", 0),
                    "avg_temp_c": round(doc.get("avg_temp", 0.0), 2) if doc.get("avg_temp") is not None else None,
                    "avg_soc_percent": round(doc.get("avg_soc", 0.0), 2) if doc.get("avg_soc") is not None else None,
                    "equipment_count": len(doc.get("equipment_affected", [])),
                    "provenance_meta": {
                        "database_type": "MongoDB",
                        "record_id": f"AGG_{fcode}",
                        "document_name": "sensorDB.telemetry",
                        "chunk_id": f"MONGO_AGG_{fcode}",
                        "timestamp": ts
                    }
                })
        except Exception as e:
            logger.error(f"Error running telemetry aggregation: {e}")
        return summary


# ============================================================================
# 3. VECTOR SIMILARITY RETRIEVAL: TECHNICAL DOCUMENTATION (ChromaDB + HNSW)
# ============================================================================
class VectorDocRetriever:
    _shared_vdb: Optional[Any] = None

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = db_path
        elif os.getenv("VECTOR_DB_PATH"):
            self.db_path = os.getenv("VECTOR_DB_PATH")
        elif Path("/opt/undata/gigavolt_vectordb").exists():
            self.db_path = "/opt/undata/gigavolt_vectordb"
        else:
            self.db_path = str(REPO_ROOT / "gigavolt_vectordb")
        self._vector_db = None

    def get_vector_db(self) -> Optional[Any]:
        if self._vector_db is not None:
            return self._vector_db
        if VectorDocRetriever._shared_vdb is not None:
            self._vector_db = VectorDocRetriever._shared_vdb
            return self._vector_db
        if GigavoltVectorDB is None:
            return None
        try:
            self._vector_db = GigavoltVectorDB(db_path=self.db_path)
            self._vector_db.create_or_get_collection()
            VectorDocRetriever._shared_vdb = self._vector_db
            return self._vector_db
        except Exception as e:
            logger.warning(f"Could not initialize GigavoltVectorDB: {e}")
            return None

    def search_documents(
        self,
        query: str,
        n_results: int = 4,
        doc_type: Optional[str] = None,
        where_filter: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        vdb = self.get_vector_db()
        if vdb is None:
            return []

        try:
            emb_key = hashlib.md5(query.encode("utf-8")).hexdigest()
            query_vec = GLOBAL_EMBEDDING_CACHE.get(emb_key) if use_cache else None
            if query_vec is None:
                query_vec = vdb.embedder.embed_query(query).tolist()
                if use_cache:
                    GLOBAL_EMBEDDING_CACHE.set(emb_key, query_vec)

            final_where = where_filter if where_filter else ({"doc_type": doc_type} if doc_type else None)
            raw_results = vdb.collection.query(
                query_embeddings=[query_vec],
                n_results=n_results,
                where=final_where
            )

            # Fallback to unfiltered search if doc_type filter returned 0 hits
            if (not raw_results or not raw_results.get("ids") or not raw_results["ids"][0]) and final_where:
                raw_results = vdb.collection.query(query_embeddings=[query_vec], n_results=n_results)

            hits = []
            if raw_results and "ids" in raw_results and raw_results["ids"]:
                ids = raw_results["ids"][0]
                docs = raw_results.get("documents", [[]])[0]
                metas = raw_results.get("metadatas", [[]])[0]
                distances = raw_results.get("distances", [[]])[0] if "distances" in raw_results else [0.0] * len(ids)

                for idx in range(len(ids)):
                    meta = metas[idx] if idx < len(metas) else {}
                    cid = ids[idx]
                    doc_id = meta.get("doc_id", cid.split("_chunk_")[0])
                    src_file = meta.get("source_file") or meta.get("doc_title") or "Gigavolt_Manual.pdf"
                    ts = meta.get("indexed_at") or "2026-01-01T00:00:00Z"

                    hits.append({
                        "id": cid,
                        "text": docs[idx] if idx < len(docs) else "",
                        "metadata": meta,
                        "distance": round(float(distances[idx]), 4) if idx < len(distances) else None,
                        "similarity_score": round(1.0 - float(distances[idx]), 4) if idx < len(distances) else None,
                        "provenance_meta": {
                            "database_type": "ChromaDB",
                            "record_id": doc_id,
                            "document_name": src_file,
                            "chunk_id": cid,
                            "timestamp": str(ts)
                        }
                    })
            return hits
        except Exception as e:
            logger.error(f"Error during vector similarity search: {e}")
            return []


# ============================================================================
# 4. UNIFIED HYBRID RETRIEVAL PIPELINE (PARALLEL + CACHED)
# ============================================================================
class HybridRetrievalPipeline:
    def __init__(
        self,
        sql_url: Optional[str] = None,
        mongo_uri: Optional[str] = None,
        vector_db_path: Optional[str] = None
    ):
        self.sql_retriever = SQLEquipmentRetriever(connection_url=sql_url)
        self.telemetry_retriever = MongoTelemetryRetriever(uri=mongo_uri)
        self.vector_retriever = VectorDocRetriever(db_path=vector_db_path)
        self._executor = ThreadPoolExecutor(max_workers=4)

    def retrieve(
        self,
        query: str,
        equipment_id: Optional[str] = None,
        serial_number: Optional[str] = None,
        model_name: Optional[str] = None,
        warranty_status: Optional[str] = None,
        fault_code: Optional[Union[str, List[str]]] = None,
        doc_type: Optional[str] = None,
        n_docs: int = 3,
        n_telemetry: int = 4,
        use_cache: bool = True,
        parallel: bool = True
    ) -> Dict[str, Any]:
        t_start_total = time.perf_counter()

        cache_key = hashlib.md5(
            json.dumps({
                "q": query, "eq": equipment_id, "sn": serial_number,
                "m": model_name, "w": warranty_status, "f": fault_code,
                "d": doc_type, "nd": n_docs, "nt": n_telemetry
            }, sort_keys=True).encode("utf-8")
        ).hexdigest()

        if use_cache:
            cached_res = GLOBAL_RETRIEVAL_CACHE.get(cache_key)
            if cached_res is not None:
                cached_copy = dict(cached_res)
                total_ms = round((time.perf_counter() - t_start_total) * 1000, 3)
                cached_copy["stage_latencies_ms"] = {
                    "sql_ms": 0.05,
                    "mongo_ms": 0.05,
                    "vector_ms": 0.05,
                    "total_retrieval_ms": total_ms,
                    "cache_hit": True
                }
                return cached_copy

        def _fetch_sql():
            t0 = time.perf_counter()
            eq_list = self.sql_retriever.query_equipment_metadata(
                equipment_id=equipment_id,
                serial_number=serial_number,
                model_name=model_name,
                warranty_status=warranty_status,
                limit=2 if (equipment_id or serial_number) else 3
            )
            resolved_eq = equipment_id or (eq_list[0].get("equipment_id") if eq_list else None)
            claims = self.sql_retriever.query_warranty_claims(
                equipment_id=resolved_eq,
                serial_number=serial_number,
                limit=3
            )
            dispatches = self.sql_retriever.query_dispatches_history(
                equipment_id=resolved_eq,
                limit=3
            )
            return eq_list, claims, dispatches, resolved_eq, round((time.perf_counter() - t0) * 1000, 2)

        def _fetch_mongo(target_eq: Optional[str]):
            t0 = time.perf_counter()
            events = self.telemetry_retriever.query_telemetry_patterns(
                equipment_id=target_eq,
                fault_code=fault_code,
                include_battery_anomalies=True,
                limit=n_telemetry
            )
            summary = self.telemetry_retriever.aggregate_fault_summary(
                equipment_id=target_eq,
                fault_codes=[fault_code] if isinstance(fault_code, str) else fault_code
            )
            return events, summary, round((time.perf_counter() - t0) * 1000, 2)

        def _fetch_vector():
            t0 = time.perf_counter()
            aug_q = f"{query} {fault_code}" if isinstance(fault_code, str) else query
            docs = self.vector_retriever.search_documents(
                query=aug_q,
                n_results=n_docs,
                doc_type=doc_type,
                use_cache=use_cache
            )
            return docs, aug_q, round((time.perf_counter() - t0) * 1000, 2)

        if parallel:
            fut_sql = self._executor.submit(_fetch_sql)
            fut_vec = self._executor.submit(_fetch_vector)
            # If equipment_id is already known, run Mongo in parallel immediately
            if equipment_id or not serial_number:
                fut_mongo = self._executor.submit(_fetch_mongo, equipment_id)
                equipment_list, warranty_claims, dispatches_list, target_eq_id, sql_ms = fut_sql.result()
                telemetry_events, telemetry_summary, mongo_ms = fut_mongo.result()
            else:
                equipment_list, warranty_claims, dispatches_list, target_eq_id, sql_ms = fut_sql.result()
                telemetry_events, telemetry_summary, mongo_ms = _fetch_mongo(target_eq_id)
            technical_docs, augmented_query, vector_ms = fut_vec.result()
        else:
            equipment_list, warranty_claims, dispatches_list, target_eq_id, sql_ms = _fetch_sql()
            telemetry_events, telemetry_summary, mongo_ms = _fetch_mongo(target_eq_id)
            technical_docs, augmented_query, vector_ms = _fetch_vector()

        total_retrieval_ms = round((time.perf_counter() - t_start_total) * 1000, 2)

        unified_result = {
            "query": query,
            "augmented_query": augmented_query,
            "equipment_id": target_eq_id or equipment_id,
            "serial_number": serial_number,
            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "stage_latencies_ms": {
                "sql_ms": sql_ms,
                "mongo_ms": mongo_ms,
                "vector_ms": vector_ms,
                "total_retrieval_ms": total_retrieval_ms,
                "cache_hit": False
            },
            "sources": {
                "sql_equipment": equipment_list,
                "sql_warranty_claims": warranty_claims,
                "sql_dispatches": dispatches_list,
                "mongodb_telemetry_events": telemetry_events,
                "mongodb_telemetry_summary": telemetry_summary,
                "vector_technical_docs": technical_docs
            }
        }

        unified_result["unified_context"] = self._format_unified_context(unified_result)
        if use_cache:
            GLOBAL_RETRIEVAL_CACHE.set(cache_key, unified_result)
        return unified_result

    def _format_unified_context(self, result: Dict[str, Any]) -> str:
        lines = ["=== GIGAVOLT UNIFIED RETRIEVAL CONTEXT ==="]
        lines.append(f"Query: {result['query']}")
        lines.append("--- [SOURCE 1: SQL EQUIPMENT, DISPATCHES & WARRANTY] ---")
        for eq in result["sources"].get("sql_equipment", []):
            pm = eq["provenance_meta"]
            lines.append(
                f"- [MariaDB | id={pm['record_id']} | doc={pm['document_name']} | chunk={pm['chunk_id']} | ts={pm['timestamp']}] "
                f"Serial: {eq.get('serial_number')} | Model: {eq.get('model_name')} ({eq.get('capacity_kw')}kW, {eq.get('voltage')}V) | "
                f"Status: {eq.get('equipment_status')} | Warranty: {eq.get('warranty_active_status')} (Exp: {eq.get('warranty_expiration')}) | "
                f"Customer: {eq.get('customer_name')} ({eq.get('company_name')})"
            )
        for cl in result["sources"].get("sql_warranty_claims", []):
            pm = cl["provenance_meta"]
            lines.append(
                f"- [MariaDB | id={pm['record_id']} | doc={pm['document_name']} | chunk={pm['chunk_id']} | ts={pm['timestamp']}] "
                f"Claim {cl.get('claim_id')} on {cl.get('equipment_id')}: {cl.get('claim_status')} | Part: {cl.get('part_name')} | Amount: ${cl.get('claim_amount')}"
            )
        for dsp in result["sources"].get("sql_dispatches", []):
            pm = dsp["provenance_meta"]
            lines.append(
                f"- [MariaDB | id={pm['record_id']} | doc={pm['document_name']} | chunk={pm['chunk_id']} | ts={pm['timestamp']}] "
                f"Dispatch {dsp.get('dispatch_id')} ({dsp.get('service_type')}): Tech {dsp.get('technician_name')} | {dsp.get('resolution_summary')}"
            )

        lines.append("\n--- [SOURCE 2: MONGODB IOT TELEMETRY] ---")
        for te in result["sources"].get("mongodb_telemetry_events", [])[:3]:
            pm = te["provenance_meta"]
            t_data = te.get("telemetry", {})
            lines.append(
                f"- [MongoDB | id={pm['record_id']} | doc={pm['document_name']} | chunk={pm['chunk_id']} | ts={pm['timestamp']}] "
                f"Unit: {te.get('equipment_id')} | Fault: {te.get('fault_code')} | Temp: {t_data.get('temperature_c')}C | SOC: {t_data.get('soc_percent')}%"
            )

        lines.append("\n--- [SOURCE 3: CHROMADB TECHNICAL DOCUMENTATION] ---")
        for doc in result["sources"].get("vector_technical_docs", []):
            pm = doc["provenance_meta"]
            snippet = doc.get("text", "").strip()[:240]
            lines.append(
                f"- [ChromaDB | id={pm['record_id']} | doc={pm['document_name']} | chunk={pm['chunk_id']} | ts={pm['timestamp']}] "
                f"\"{snippet}...\""
            )
        lines.append("=== END OF CONTEXT ===")
        return "\n".join(lines)


def hybrid_retrieval(
    query: str,
    equipment_id: Optional[str] = None,
    serial_number: Optional[str] = None,
    model_name: Optional[str] = None,
    warranty_status: Optional[str] = None,
    fault_code: Optional[Union[str, List[str]]] = None,
    doc_type: Optional[str] = None,
    n_docs: int = 3,
    n_telemetry: int = 4,
    sql_url: Optional[str] = None,
    mongo_uri: Optional[str] = None,
    vector_db_path: Optional[str] = None,
    use_cache: bool = True,
    parallel: bool = True
) -> Dict[str, Any]:
    pipeline = HybridRetrievalPipeline(sql_url=sql_url, mongo_uri=mongo_uri, vector_db_path=vector_db_path)
    return pipeline.retrieve(
        query=query,
        equipment_id=equipment_id,
        serial_number=serial_number,
        model_name=model_name,
        warranty_status=warranty_status,
        fault_code=fault_code,
        doc_type=doc_type,
        n_docs=n_docs,
        n_telemetry=n_telemetry,
        use_cache=use_cache,
        parallel=parallel
    )


hybrid_search = hybrid_retrieval
HybridSearchPipeline = HybridRetrievalPipeline


def main():
    parser = argparse.ArgumentParser(description="Gigavolt Hybrid Retrieval Pipeline")
    parser.add_argument("--query", "-q", type=str, required=True)
    parser.add_argument("--equipment-id", "-e", type=str, default=None)
    parser.add_argument("--warranty-status", "-w", type=str, default=None)
    parser.add_argument("--fault-code", "-f", type=str, default=None)
    parser.add_argument("--doc-type", "-d", type=str, default=None)
    parser.add_argument("--limit-docs", type=int, default=3)
    parser.add_argument("--limit-telemetry", type=int, default=4)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    res = hybrid_retrieval(
        query=args.query,
        equipment_id=args.equipment_id,
        warranty_status=args.warranty_status,
        fault_code=args.fault_code,
        doc_type=args.doc_type,
        n_docs=args.limit_docs,
        n_telemetry=args.limit_telemetry
    )
    print(json.dumps(res, indent=2) if args.json else res["unified_context"])


if __name__ == "__main__":
    main()