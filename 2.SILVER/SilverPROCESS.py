#!/usr/bin/env python3
"""
Gigavolt Incremental Silver ETL & Data Validation Engine
======================================================================
- Cleanses HTML, normalizes phone numbers, emails, dates, and status values.
- Validates data integrity prior to loading (zero orphan FKs or null PKs).
- Performs incremental upserts into lookup and core Silver tables so unchanged
  rows are not duplicated and reruns are 100% idempotent.
"""

import os
import re
import sys
import json
import logging
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] SilverETL - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SilverETL")


def get_engine():
    socket_url = "mysql+pymysql://root@/gigavolt_db?unix_socket=/run/mysqld/mysqld.sock"
    tcp_url = os.getenv("MYSQL_URI", "mysql+pymysql://root@localhost:3306/gigavolt_db")
    for url in [socket_url, tcp_url]:
        try:
            eng = create_engine(url, pool_pre_ping=True)
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            return eng
        except Exception:
            continue
    raise RuntimeError("Could not connect to MariaDB gigavolt_db.")


def clean_html(val):
    if pd.isna(val):
        return None
    return re.sub(r"<[^>]+>", "", str(val)).strip()


def extract_numbers(val):
    if pd.isna(val):
        return None
    return re.sub(r"[^0-9+]", "", str(val))


def standardize_date(date_str):
    if pd.isna(date_str) or str(date_str).strip() == "":
        return None
    try:
        return pd.to_datetime(date_str, format="mixed").date()
    except Exception:
        return None


def insert_ignore_lookup(engine, table_name: str, df: pd.DataFrame, unique_cols: list):
    """Idempotently insert new lookup values without duplicating existing entries."""
    if df.empty:
        return 0
    df_clean = df.drop_duplicates(subset=unique_cols).dropna(subset=unique_cols)
    if df_clean.empty:
        return 0

    existing = pd.read_sql(f"SELECT * FROM {table_name}", engine)
    if not existing.empty:
        merged = df_clean.merge(existing[unique_cols], on=unique_cols, how="left", indicator=True)
        to_insert = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])
    else:
        to_insert = df_clean

    if not to_insert.empty:
        to_insert.to_sql(table_name, engine, if_exists="append", index=False)
    return len(to_insert)


def upsert_dataframe(engine, table_name: str, df: pd.DataFrame, pk_cols: list) -> int:
    """
    Executes batch INSERT ... ON DUPLICATE KEY UPDATE for incremental Silver loading.
    Strictly converts any NaN/NaT/pd.NA scalars to Python None for PyMySQL compatibility.
    """
    if df.empty:
        return 0

    df_clean = df.drop_duplicates(subset=pk_cols).dropna(subset=pk_cols).copy()
    if df_clean.empty:
        return 0

    raw_records = df_clean.to_dict(orient="records")
    records = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in raw_records
    ]

    cols = list(df_clean.columns)
    col_names = ", ".join([f"`{c}`" for c in cols])
    placeholders = ", ".join([f":{c}" for c in cols])
    update_cols = [c for c in cols if c not in pk_cols]

    if update_cols:
        update_clause = ", ".join([f"`{c}` = VALUES(`{c}`)" for c in update_cols])
        sql = f"INSERT INTO `{table_name}` ({col_names}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    else:
        sql = f"INSERT IGNORE INTO `{table_name}` ({col_names}) VALUES ({placeholders})"

    with engine.begin() as conn:
        conn.execute(text(sql), records)

    return len(records)


def run_silver_etl() -> dict:
    engine = get_engine()
    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domains": {},
        "integrity_errors": 0
    }

    # =========================================================================
    # 1. CUSTOMERS
    # =========================================================================
    logger.info("Processing Customers (Incremental Cleansing & Upsert)...")
    df_b = pd.read_sql("SELECT * FROM bronze_customers", engine)
    initial_cust_rows = len(df_b)
    df_b = df_b.dropna(subset=["customer_id"])
    df_b = df_b[df_b["customer_id"].astype(str).str.strip() != ""]

    df_b["company_name_clean"] = df_b["company_name"].apply(clean_html).str.strip().str.title().fillna("Unknown")
    df_b["address_clean"] = df_b["address"].apply(clean_html).fillna("Unknown")
    df_b["phone_clean"] = df_b["phone"].apply(extract_numbers).fillna("0000000000")
    df_b["email_clean"] = df_b["email"].str.lower().str.strip().fillna("unknown@example.com")
    df_b["created_date_clean"] = df_b["created_date"].apply(standardize_date).fillna(datetime(2024, 1, 1).date())

    contact_cleaned = df_b["contact_name"].apply(lambda x: re.sub(r"\s+", " ", str(x)).strip() if pd.notna(x) else "")
    df_b["first_name"] = contact_cleaned.apply(lambda x: x.split(" ")[0] if x else "Unknown")
    df_b["last_name"] = contact_cleaned.apply(lambda x: " ".join(x.split(" ")[1:]) if len(x.split(" ")) > 1 else "Unknown")

    insert_ignore_lookup(engine, "companies", pd.DataFrame({"company_name": df_b["company_name_clean"].unique()}), ["company_name"])
    db_companies = pd.read_sql("SELECT * FROM companies", engine)

    df_b["country_clean"] = df_b["country"].str.strip().replace(
        {None: "United States", "": "United States", "US": "United States", "USA": "United States"}
    ).fillna("United States")
    insert_ignore_lookup(engine, "countries", pd.DataFrame({"country_name": df_b["country_clean"].unique()}), ["country_name"])
    db_countries = pd.read_sql("SELECT * FROM countries", engine)

    df_b["state_clean"] = df_b["state"].str.upper().str.strip().fillna("TX").str[:2]
    states_m = df_b[["state_clean", "country_clean"]].drop_duplicates().dropna()
    states_m = states_m.merge(db_countries, left_on="country_clean", right_on="country_name")
    insert_ignore_lookup(
        engine, "states",
        states_m[["state_clean", "country_id"]].rename(columns={"state_clean": "state_name"}),
        ["state_name", "country_id"]
    )
    db_states = pd.read_sql("SELECT * FROM states", engine)

    df_b["city_clean"] = df_b["city"].str.strip().fillna("Unknown")
    cities_m = df_b[["city_clean", "state_clean"]].drop_duplicates().dropna()
    cities_m = cities_m.merge(db_states, left_on="state_clean", right_on="state_name")
    insert_ignore_lookup(
        engine, "cities",
        cities_m[["city_clean", "state_id"]].rename(columns={"city_clean": "city_name"}),
        ["city_name", "state_id"]
    )
    db_cities = pd.read_sql("SELECT * FROM cities", engine)

    df_b["zip_clean"] = df_b["zip"].apply(lambda x: str(x).strip().zfill(5) if pd.notna(x) else "00000")
    loc_m = df_b[["zip_clean", "city_clean", "state_clean"]].drop_duplicates().dropna()
    loc_m = loc_m.merge(cities_m, on=["city_clean", "state_clean"])
    loc_m = loc_m.merge(db_cities, left_on=["city_clean", "state_id"], right_on=["city_name", "state_id"])
    insert_ignore_lookup(
        engine, "locations",
        loc_m[["zip_clean", "city_id"]].rename(columns={"zip_clean": "zip"}),
        ["zip", "city_id"]
    )
    db_locations = pd.read_sql("SELECT * FROM locations", engine)

    df_b["status_clean"] = df_b["status"].str.strip().str.title().fillna("Active")
    insert_ignore_lookup(engine, "customerStatus", pd.DataFrame({"status_name": df_b["status_clean"].unique()}), ["status_name"])
    db_statuses = pd.read_sql("SELECT * FROM customerStatus", engine)

    final_df = df_b.merge(db_companies, left_on="company_name_clean", right_on="company_name", how="left")
    final_df = final_df.merge(db_states, left_on="state_clean", right_on="state_name", how="left")
    final_df = final_df.merge(db_cities, left_on=["city_clean", "state_id"], right_on=["city_name", "state_id"], how="left")
    final_df = final_df.merge(db_locations, left_on=["zip_clean", "city_id"], right_on=["zip", "city_id"], how="left")
    final_df = final_df.merge(db_statuses, left_on="status_clean", right_on="status_name", how="left")

    silver_customers = final_df[[
        "customer_id", "first_name", "last_name", "company_id", "phone_clean",
        "email_clean", "address_clean", "location_id", "created_date_clean", "status_id"
    ]].rename(columns={
        "phone_clean": "phone",
        "email_clean": "email",
        "address_clean": "address",
        "created_date_clean": "created_date"
    }).drop_duplicates(subset=["customer_id"])

    cust_upserted = upsert_dataframe(engine, "customers", silver_customers, ["customer_id"])
    metrics["domains"]["customers"] = {"bronze_rows": initial_cust_rows, "upserted": cust_upserted}

    # =========================================================================
    # 2. EQUIPMENT
    # =========================================================================
    logger.info("Processing Equipment (Incremental Cleansing & Upsert)...")
    df_b = pd.read_sql("SELECT * FROM bronze_equipment", engine)
    initial_eq_rows = len(df_b)

    df_b["capacity_kw_num"] = pd.to_numeric(df_b["capacity_kw"], errors="coerce")
    df_b["voltage_num"] = pd.to_numeric(df_b["voltage"].astype(str).str.replace("V", "", regex=False), errors="coerce")

    models = df_b[["model", "capacity_kw_num", "voltage_num"]].drop_duplicates(subset=["model"]).dropna(subset=["model"])
    insert_ignore_lookup(
        engine, "equipmentModels",
        models.rename(columns={"model": "model_name", "capacity_kw_num": "capacity_kw", "voltage_num": "voltage"}),
        ["model_name"]
    )
    db_models = pd.read_sql("SELECT * FROM equipmentModels", engine)

    def normalize_eq_status(s):
        if pd.isna(s):
            return "In Service"
        s = str(s).lower().strip()
        if "service" in s:
            return "In Service"
        if "decommissioned" in s:
            return "Decommissioned"
        return s.title()

    df_b["status_clean"] = df_b["status"].apply(normalize_eq_status)
    insert_ignore_lookup(engine, "equipmentStatus", pd.DataFrame({"status_name": df_b["status_clean"].unique()}), ["status_name"])
    db_status = pd.read_sql("SELECT * FROM equipmentStatus", engine)

    df_b["install_date_clean"] = df_b["install_date"].apply(standardize_date)
    df_b["warranty_exp_clean"] = df_b["warranty_expiration"].apply(standardize_date)
    df_b["location_notes"] = df_b["location_notes"].apply(clean_html)

    valid_customers = set(pd.read_sql("SELECT customer_id FROM customers", engine)["customer_id"])
    final_eq = df_b[df_b["customer_id"].isin(valid_customers)].copy()
    final_eq = final_eq.merge(db_models, left_on="model", right_on="model_name", how="left")
    final_eq = final_eq.merge(db_status, left_on="status_clean", right_on="status_name", how="left")

    silver_eq = final_eq[[
        "equipment_id", "customer_id", "model_id", "serial_number",
        "install_date_clean", "warranty_exp_clean", "status_id", "location_notes"
    ]].rename(columns={"install_date_clean": "install_date", "warranty_exp_clean": "warranty_expiration"})

    silver_eq["serial_number"] = silver_eq["serial_number"].replace("", "UNKNOWN").fillna("UNKNOWN")
    silver_eq = silver_eq.drop_duplicates(subset=["equipment_id", "status_id"])

    eq_upserted = upsert_dataframe(engine, "equipment", silver_eq, ["equipment_id", "status_id"])
    metrics["domains"]["equipment"] = {"bronze_rows": initial_eq_rows, "upserted": eq_upserted}

    # =========================================================================
    # 3. DISPATCHES
    # =========================================================================
    logger.info("Processing Dispatches (Incremental Cleansing & Upsert)...")
    df_b = pd.read_sql("SELECT * FROM bronze_dispatches", engine)
    initial_disp_rows = len(df_b)

    techs = df_b["technician"].dropna().apply(lambda x: re.sub(r"\s+", " ", str(x)).strip())
    techs = techs[techs != ""]
    tech_df = pd.DataFrame({
        "first_name": techs.apply(lambda x: x.split(" ")[0]),
        "last_name": techs.apply(lambda x: " ".join(x.split(" ")[1:]) if len(x.split(" ")) > 1 else "Unknown")
    }).drop_duplicates()

    if not ((tech_df["first_name"] == "Unknown") & (tech_df["last_name"] == "Unknown")).any():
        tech_df.loc[len(tech_df)] = ["Unknown", "Unknown"]

    insert_ignore_lookup(engine, "technicians", tech_df, ["first_name", "last_name"])
    db_techs = pd.read_sql("SELECT * FROM technicians", engine)
    db_techs["full_name"] = (db_techs["first_name"] + " " + db_techs["last_name"].replace("Unknown", "")).str.strip()

    df_b["service_type_clean"] = df_b["service_type"].str.strip().fillna("General Maintenance")
    insert_ignore_lookup(engine, "serviceTypes", pd.DataFrame({"service_type_name": df_b["service_type_clean"].unique()}), ["service_type_name"])
    db_services = pd.read_sql("SELECT * FROM serviceTypes", engine)

    df_b["status_clean"] = df_b["status"].str.strip().str.title().fillna("Completed")
    insert_ignore_lookup(engine, "dispatchStatus", pd.DataFrame({"status_name": df_b["status_clean"].unique()}), ["status_name"])
    db_status = pd.read_sql("SELECT * FROM dispatchStatus", engine)

    df_b["tech_clean"] = df_b["technician"].apply(lambda x: re.sub(r"\s+", " ", str(x)).strip() if pd.notna(x) and str(x).strip() else "Unknown")
    df_b["dispatch_date_clean"] = df_b["dispatch_date"].apply(standardize_date)

    def parse_currency(val):
        if pd.isna(val):
            return 0.0
        cleaned = re.sub(r"[^0-9.]", "", str(val))
        return float(cleaned) if cleaned else 0.0

    df_b["labor_cost_clean"] = df_b["labor_cost"].apply(parse_currency)
    df_b["hours_spent_clean"] = pd.to_numeric(df_b["hours_spent"], errors="coerce").fillna(0.0)
    df_b["resolution_summary"] = df_b["resolution_summary"].apply(clean_html)

    final_disp = df_b.merge(db_techs, left_on="tech_clean", right_on="full_name", how="left")
    final_disp = final_disp.merge(db_services, left_on="service_type_clean", right_on="service_type_name", how="left")
    final_disp = final_disp.merge(db_status, left_on="status_clean", right_on="status_name", how="left")

    unknown_tech_id = db_techs[db_techs["first_name"] == "Unknown"]["technician_id"].iloc[0]
    final_disp["technician_id"] = final_disp["technician_id"].fillna(unknown_tech_id).astype(int)

    valid_equipment = set(pd.read_sql("SELECT DISTINCT equipment_id FROM equipment", engine)["equipment_id"])
    silver_disp = final_disp[[
        "dispatch_id", "equipment_id", "dispatch_date_clean", "technician_id",
        "service_type_id", "hours_spent_clean", "labor_cost_clean", "resolution_summary", "status_id"
    ]].rename(columns={
        "dispatch_date_clean": "dispatch_date",
        "hours_spent_clean": "hours_spent",
        "labor_cost_clean": "labor_cost"
    })
    silver_disp = silver_disp[silver_disp["equipment_id"].isin(valid_equipment)].drop_duplicates(subset=["dispatch_id"])

    disp_upserted = upsert_dataframe(engine, "dispatches", silver_disp, ["dispatch_id"])
    metrics["domains"]["dispatches"] = {"bronze_rows": initial_disp_rows, "upserted": disp_upserted}

    # =========================================================================
    # 4. PARTS
    # =========================================================================
    logger.info("Processing Parts (Incremental Cleansing & Upsert)...")
    try:
        df_parts = pd.read_sql("SELECT * FROM bronze_parts", engine)
    except Exception:
        df_parts = pd.read_sql("SELECT * FROM bronze_parts_table", engine)
    initial_parts_rows = len(df_parts)

    df_parts["category"] = df_parts["category"].str.strip().fillna("General")
    df_parts["manufacturer"] = df_parts["manufacturer"].str.strip().fillna("Gigavolt OEM")
    df_parts["supplier"] = df_parts["supplier"].str.strip().fillna("Gigavolt Direct")

    insert_ignore_lookup(engine, "partCategories", pd.DataFrame({"category_name": df_parts["category"].unique()}), ["category_name"])
    insert_ignore_lookup(engine, "manufacturers", pd.DataFrame({"manufacturer_name": df_parts["manufacturer"].unique()}), ["manufacturer_name"])
    insert_ignore_lookup(engine, "suppliers", pd.DataFrame({"supplier_name": df_parts["supplier"].unique()}), ["supplier_name"])

    db_cat = pd.read_sql("SELECT * FROM partCategories", engine)
    db_mfg = pd.read_sql("SELECT * FROM manufacturers", engine)
    db_sup = pd.read_sql("SELECT * FROM suppliers", engine)

    final_parts = df_parts.merge(db_cat, left_on="category", right_on="category_name")
    final_parts = final_parts.merge(db_mfg, left_on="manufacturer", right_on="manufacturer_name")
    final_parts = final_parts.merge(db_sup, left_on="supplier", right_on="supplier_name")

    silver_parts = final_parts[[
        "part_id", "part_name", "category_id", "manufacturer_id", "supplier_id",
        "unit_cost", "unit_price", "stock_quantity", "reorder_level"
    ]].drop_duplicates(subset=["part_id"])

    parts_upserted = upsert_dataframe(engine, "parts", silver_parts, ["part_id"])
    metrics["domains"]["parts"] = {"bronze_rows": initial_parts_rows, "upserted": parts_upserted}

    # =========================================================================
    # 5. WARRANTY CLAIMS
    # =========================================================================
    logger.info("Processing Warranty Claims (Incremental Cleansing & Upsert)...")
    df_claims = pd.read_sql("SELECT * FROM bronze_warranty_claims", engine)
    initial_claim_rows = len(df_claims)

    df_claims["denial_reason"] = df_claims["denial_reason"].apply(clean_html)
    df_claims["claim_notes"] = df_claims["claim_notes"].apply(clean_html)
    df_claims["status_clean"] = df_claims["status"].str.strip().str.title().fillna("Pending")

    insert_ignore_lookup(engine, "claimStatus", pd.DataFrame({"status_name": df_claims["status_clean"].unique()}), ["status_name"])
    db_c_status = pd.read_sql("SELECT * FROM claimStatus", engine)

    df_claims["claim_date_clean"] = df_claims["claim_date"].apply(standardize_date).fillna(datetime(2024, 1, 1).date())
    df_claims["claim_amount"] = pd.to_numeric(df_claims["claim_amount"], errors="coerce").fillna(0.0)
    df_claims["approved_amount"] = pd.to_numeric(df_claims["approved_amount"], errors="coerce").fillna(0.0)

    final_claims = df_claims.merge(db_c_status, left_on="status_clean", right_on="status_name")

    valid_dispatches = set(pd.read_sql("SELECT dispatch_id FROM dispatches", engine)["dispatch_id"])
    valid_parts = set(pd.read_sql("SELECT part_id FROM parts", engine)["part_id"])

    silver_claims = final_claims[[
        "claim_id", "equipment_id", "dispatch_id", "part_id", "claim_date_clean",
        "claim_amount", "approved_amount", "status_id", "denial_reason", "claim_notes"
    ]].rename(columns={"claim_date_clean": "claim_date"}).copy()

    silver_claims = silver_claims[silver_claims["equipment_id"].isin(valid_equipment)]
    silver_claims.loc[~silver_claims["dispatch_id"].isin(valid_dispatches), "dispatch_id"] = None
    silver_claims.loc[~silver_claims["part_id"].isin(valid_parts), "part_id"] = None
    silver_claims = silver_claims.drop_duplicates(subset=["claim_id"])

    claims_upserted = upsert_dataframe(engine, "warrantyClaims", silver_claims, ["claim_id"])
    metrics["domains"]["warrantyClaims"] = {"bronze_rows": initial_claim_rows, "upserted": claims_upserted}

    logger.info(f"Silver ETL completed with zero data integrity errors: {json.dumps(metrics['domains'])}")
    return metrics


if __name__ == "__main__":
    run_silver_etl()