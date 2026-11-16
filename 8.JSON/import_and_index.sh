#!/bin/bash
set -euo pipefail

TELEMETRY_FILE="${1:-/opt/undata/telemetry_data.json}"

echo "==================================================================="
echo "1. Incrementally Upserting IoT Telemetry into MongoDB ($TELEMETRY_FILE)"
echo "==================================================================="
mongoimport --db sensorDB \
            --collection telemetry \
            --file "$TELEMETRY_FILE" \
            --mode=upsert \
            --upsertFields=equipment_id,timestamp,fault_code

echo "==================================================================="
echo "2. Building Compound & Diagnostic Indexes in MongoDB"
echo "==================================================================="
mongosh sensorDB --quiet << 'EOF'
// Single-field indexes
db.telemetry.createIndex({ timestamp: -1 });
db.telemetry.createIndex({ equipment_id: 1 });
db.telemetry.createIndex({ fault_code: 1 });

// Compound indexes for query optimization (Multi-hop + Temporal)
db.telemetry.createIndex({ equipment_id: 1, timestamp: -1 });
db.telemetry.createIndex({ equipment_id: 1, fault_code: 1, timestamp: -1 });
db.telemetry.createIndex({ fault_code: 1, "telemetry.temperature_c": -1 });

// Retrieve diagnostic summary
print("\n--- Diagnostic Summary: Battery Failures by Fault Code ---");
db.telemetry.aggregate([
  { $match: { fault_code: { $in: ["ERR_BMS_701", "ERR_BMS_705", "ERR_BMS_708", "ERR_VOLT_102"] } } },
  { $group: {
      _id: "$fault_code",
      count: { $sum: 1 },
      avg_temp: { $avg: "$telemetry.temperature_c" },
      avg_soc: { $avg: "$telemetry.soc_percent" },
      equipment_affected: { $addToSet: "$equipment_id" }
  }}
]).forEach(printjson);
EOF