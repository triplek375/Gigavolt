import pandas as pd
import re
from sqlalchemy import create_engine

engine = create_engine('mysql+pymysql://root@localhost/gigavolt_db')

def clean_html(text):
    if pd.isna(text): return None
    return re.sub(r'<[^>]+>', '', str(text)).strip()

def extract_numbers(text):
    if pd.isna(text): return None
    return re.sub(r'[^0-9+]', '', str(text))

def standardize_date(date_str):
    if pd.isna(date_str): return None
    try:
        return pd.to_datetime(date_str, format='mixed').date()
    except:
        return None



print("Processing Customers...")
df_b = pd.read_sql("SELECT * FROM bronze_customers", engine)

# 1. Clean Data
df_b['company_name_clean'] = df_b['company_name'].apply(clean_html)
df_b['address_clean'] = df_b['address'].apply(clean_html)
df_b['phone_clean'] = df_b['phone'].apply(extract_numbers)
df_b['email_clean'] = df_b['email'].str.lower().str.strip()
df_b['created_date_clean'] = df_b['created_date'].apply(standardize_date)

# Extract First and Last Name
contact_cleaned = df_b['contact_name'].apply(lambda x: re.sub(r'\s+', ' ', str(x)).strip() if pd.notna(x) else '')
df_b['first_name'] = contact_cleaned.apply(lambda x: x.split(' ')[0] if x else 'Unknown')
df_b['last_name'] = contact_cleaned.apply(lambda x: ' '.join(x.split(' ')[1:]) if len(x.split(' ')) > 1 else 'Unknown')

# 2. Populate Lookup Tables
# Companies
companies = pd.DataFrame({'company_name': df_b['company_name_clean'].dropna().unique()})
companies.to_sql('companies', engine, if_exists='append', index=False)
db_companies = pd.read_sql("SELECT * FROM companies", engine)

# Countries
df_b['country_clean'] = df_b['country'].replace(
    {None: 'United States', '': 'United States', 'US': 'United States', 'USA': 'United States'}
)
countries = pd.DataFrame({'country_name': df_b['country_clean'].dropna().unique()})
countries.to_sql('countries', engine, if_exists='append', index=False)
db_countries = pd.read_sql("SELECT * FROM countries", engine)

# States
df_b['state_clean'] = df_b['state'].str.upper().str.strip()
states_m = df_b[['state_clean', 'country_clean']].drop_duplicates().dropna()
states_m = states_m.merge(db_countries, left_on='country_clean', right_on='country_name')
states_m[['state_clean', 'country_id']].rename(columns={'state_clean': 'state_name'}).to_sql('states', engine, if_exists='append', index=False)
db_states = pd.read_sql("SELECT * FROM states", engine)

# Cities
df_b['city_clean'] = df_b['city'].str.strip()
cities_m = df_b[['city_clean', 'state_clean']].drop_duplicates().dropna()
cities_m = cities_m.merge(db_states, left_on='state_clean', right_on='state_name')
cities_m[['city_clean', 'state_id']].rename(columns={'city_clean': 'city_name'}).to_sql('cities', engine, if_exists='append', index=False)
db_cities = pd.read_sql("SELECT * FROM cities", engine)

# Locations (Zip Codes)
df_b['zip_clean'] = df_b['zip'].apply(lambda x: str(x).zfill(5) if pd.notna(x) else None)
loc_m = df_b[['zip_clean', 'city_clean', 'state_clean']].drop_duplicates().dropna()
loc_m = loc_m.merge(cities_m, on=['city_clean', 'state_clean'])
loc_m[['zip_clean', 'city_id']].rename(columns={'zip_clean': 'zip'}).to_sql('locations', engine, if_exists='append', index=False)
db_locations = pd.read_sql("SELECT * FROM locations", engine)

# Customer Status
df_b['status_clean'] = df_b['status'].str.strip()
statuses = pd.DataFrame({'status_name': df_b['status_clean'].dropna().unique()})
statuses.to_sql('customerStatus', engine, if_exists='append', index=False)
db_statuses = pd.read_sql("SELECT * FROM customerStatus", engine)

# 3. Assemble and Insert Main Customers Table
final_df = df_b.merge(db_companies, left_on='company_name_clean', right_on='company_name', how='left')
final_df = final_df.merge(db_locations, left_on='zip_clean', right_on='zip', how='left')
final_df = final_df.merge(db_statuses, left_on='status_clean', right_on='status_name', how='left')

silver_customers = final_df[[
    'customer_id', 'first_name', 'last_name', 'company_id', 'phone_clean', 
    'email_clean', 'address_clean', 'location_id', 'created_date_clean', 'status_id'
]].rename(columns={'phone_clean': 'phone', 'email_clean': 'email', 'address_clean': 'address', 'created_date_clean': 'created_date'})

silver_customers.to_sql('customers', engine, if_exists='append', index=False)



print("Processing Equipment...")
df_b = pd.read_sql("SELECT * FROM bronze_equipment", engine)

# Clean & Insert Models
df_b['capacity_kw_num'] = pd.to_numeric(df_b['capacity_kw'], errors='coerce')
df_b['voltage_num'] = pd.to_numeric(df_b['voltage'].str.replace('V', ''), errors='coerce')
models = df_b[['model', 'capacity_kw_num', 'voltage_num']].drop_duplicates().dropna(subset=['model'])
models.rename(columns={'model': 'model_name', 'capacity_kw_num': 'capacity_kw', 'voltage_num': 'voltage'}).to_sql('equipmentModels', engine, if_exists='append', index=False)
db_models = pd.read_sql("SELECT * FROM equipmentModels", engine)

# Clean & Insert Status
def normalize_eq_status(s):
    if pd.isna(s): return None
    s = str(s).lower().strip()
    if 'service' in s: return 'In Service'
    if 'decommissioned' in s: return 'Decommissioned'
    return s.title()

df_b['status_clean'] = df_b['status'].apply(normalize_eq_status)
pd.DataFrame({'status_name': df_b['status_clean'].dropna().unique()}).to_sql('equipmentStatus', engine, if_exists='append', index=False)
db_status = pd.read_sql("SELECT * FROM equipmentStatus", engine)

# Dates
df_b['install_date_clean'] = df_b['install_date'].apply(standardize_date)
df_b['warranty_exp_clean'] = df_b['warranty_expiration'].apply(standardize_date)

# Assemble Main
final_eq = df_b.merge(db_models, left_on=['model', 'capacity_kw_num', 'voltage_num'], right_on=['model_name', 'capacity_kw', 'voltage'], how='left')
final_eq = final_eq.merge(db_status, left_on='status_clean', right_on='status_name', how='left')

silver_eq = final_eq[[
    'equipment_id', 'customer_id', 'model_id', 'serial_number', 
    'install_date_clean', 'warranty_exp_clean', 'status_id', 'location_notes'
]].rename(columns={'install_date_clean': 'install_date', 'warranty_exp_clean': 'warranty_expiration'})

# Fill blanks
silver_eq['serial_number'] = silver_eq['serial_number'].replace('', 'UNKNOWN').fillna('UNKNOWN')
silver_eq.drop_duplicates(subset=['equipment_id', 'status_id']).to_sql('equipment', engine, if_exists='append', index=False)



print("Processing Dispatches...")
df_b = pd.read_sql("SELECT * FROM bronze_dispatches", engine)

# Technicians
techs = df_b['technician'].dropna().apply(lambda x: re.sub(r'\s+', ' ', str(x)).strip())
tech_df = pd.DataFrame({
    'first_name': techs.apply(lambda x: x.split(' ')[0]),
    'last_name': techs.apply(lambda x: ' '.join(x.split(' ')[1:]) if len(x.split(' ')) > 1 else 'Unknown')
}).drop_duplicates()
tech_df.loc[len(tech_df)] = ['Unknown', 'Unknown'] # Fallback
tech_df.drop_duplicates().to_sql('technicians', engine, if_exists='append', index=False)
db_techs = pd.read_sql("SELECT * FROM technicians", engine)
db_techs['full_name'] = db_techs['first_name'] + ' ' + db_techs['last_name'].replace('Unknown', '').str.strip()

# Service Types
pd.DataFrame({'service_type_name': df_b['service_type'].str.strip().dropna().unique()}).to_sql('serviceTypes', engine, if_exists='append', index=False)
db_services = pd.read_sql("SELECT * FROM serviceTypes", engine)

# Dispatch Status
df_b['status_clean'] = df_b['status'].str.strip().str.title()
pd.DataFrame({'status_name': df_b['status_clean'].dropna().unique()}).to_sql('dispatchStatus', engine, if_exists='append', index=False)
db_status = pd.read_sql("SELECT * FROM dispatchStatus", engine)

# Assemble Main
df_b['tech_clean'] = df_b['technician'].apply(lambda x: re.sub(r'\s+', ' ', str(x)).strip() if pd.notna(x) else 'Unknown Unknown')
df_b['dispatch_date_clean'] = df_b['dispatch_date'].apply(standardize_date)
df_b['labor_cost_clean'] = pd.to_numeric(df_b['labor_cost'].apply(extract_numbers), errors='coerce') / 100 # Adjust if decimals removed

final_disp = df_b.merge(db_techs, left_on='tech_clean', right_on='full_name', how='left')
final_disp = final_disp.merge(db_services, left_on='service_type', right_on='service_type_name', how='left')
final_disp = final_disp.merge(db_status, left_on='status_clean', right_on='status_name', how='left')

# Fallback to unknown tech id if missing
unknown_tech_id = db_techs[db_techs['first_name'] == 'Unknown']['technician_id'].iloc[0]
final_disp['technician_id'] = final_disp['technician_id'].fillna(unknown_tech_id)

silver_disp = final_disp[[
    'dispatch_id', 'equipment_id', 'dispatch_date_clean', 'technician_id', 
    'service_type_id', 'hours_spent', 'labor_cost_clean', 'resolution_summary', 'status_id'
]].rename(columns={'dispatch_date_clean': 'dispatch_date', 'labor_cost_clean': 'labor_cost'})

silver_disp.to_sql('dispatches', engine, if_exists='append', index=False)



print("Processing Parts...")

# PARTS
try:
    df_parts = pd.read_sql("SELECT * FROM bronze_parts", engine)
except:
    df_parts = pd.read_sql("SELECT * FROM bronze_parts_table", engine)

pd.DataFrame({'category_name': df_parts['category'].dropna().unique()}).to_sql('partCategories', engine, if_exists='append', index=False)
pd.DataFrame({'manufacturer_name': df_parts['manufacturer'].dropna().unique()}).to_sql('manufacturers', engine, if_exists='append', index=False)
pd.DataFrame({'supplier_name': df_parts['supplier'].dropna().unique()}).to_sql('suppliers', engine, if_exists='append', index=False)

db_cat = pd.read_sql("SELECT * FROM partCategories", engine)
db_mfg = pd.read_sql("SELECT * FROM manufacturers", engine)
db_sup = pd.read_sql("SELECT * FROM suppliers", engine)

final_parts = df_parts.merge(db_cat, left_on='category', right_on='category_name')
final_parts = final_parts.merge(db_mfg, left_on='manufacturer', right_on='manufacturer_name')
final_parts = final_parts.merge(db_sup, left_on='supplier', right_on='supplier_name')

final_parts[['part_id', 'part_name', 'category_id', 'manufacturer_id', 'supplier_id', 'unit_cost', 'unit_price', 'stock_quantity', 'reorder_level']].to_sql('parts', engine, if_exists='append', index=False)



print("Processing Claims...")
# CLAIMS
df_claims = pd.read_sql("SELECT * FROM bronze_warranty_claims", engine)
df_claims['status_clean'] = df_claims['status'].str.strip().str.title()
pd.DataFrame({'status_name': df_claims['status_clean'].dropna().unique()}).to_sql('claimStatus', engine, if_exists='append', index=False)
db_c_status = pd.read_sql("SELECT * FROM claimStatus", engine)

df_claims['claim_date_clean'] = df_claims['claim_date'].apply(standardize_date)
final_claims = df_claims.merge(db_c_status, left_on='status_clean', right_on='status_name')

silver_claims = final_claims[[
    'claim_id', 'equipment_id', 'dispatch_id', 'part_id', 'claim_date_clean',
    'claim_amount', 'approved_amount', 'status_id', 'denial_reason', 'claim_notes'
]].rename(columns={'claim_date_clean': 'claim_date'})

silver_claims.replace({'': None}).to_sql('warrantyClaims', engine, if_exists='append', index=False)



print("Silver DML ETL completed successfully.")