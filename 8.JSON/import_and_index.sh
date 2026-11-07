#!/bin/bash
set -euo pipefail

echo "==================================================================="
echo "1. Ingesting IoT Telemetry into MongoDB"
echo "==================================================================="
mongoimport --db sensorDB \
            --collection telemetry \
            --file /opt/undata/telemetry_data.json \
            --drop

echo "==================================================================="
echo "2. Indexing and Querying Battery Diagnostics"
echo "==================================================================="
mongosh sensorDB --quiet << 'EOF'

// Index by timestamp for chronological sorting and range queries
db.telemetry.createIndex({ timestamp: -1 });

// Index by equipment_id to quickly isolate individual units
db.telemetry.createIndex({ equipment_id: 1 });

// Index by fault_code (actual error code field) for failure categorization
db.telemetry.createIndex({ fault_code: 1 });

// Retrieve diagnostic data for battery-related failures
print("\n--- Battery Failure Diagnostic Records ---");
const cursor = db.telemetry.find({
  $or: [
    // Real battery fault codes in the dataset
    { fault_code: { $in: ["ERR_BMS_701", "ERR_BMS_705", "ERR_BMS_708", "ERR_VOLT_102"] } },
    // Flagged battery hardware (BMS modules, battery cells)
    { flagged_components: { $regex: /^(BMS|CEL|MOD)/i } },
    // Battery-specific keywords in technician/system notes
    { notes: { $regex: /battery|cell|thermal runaway|discharge/i } },
    // Diagnostic telemetry thresholds (overheating cell or severe deep discharge)
    { "telemetry.temperature_c": { $gte: 65 } },
    { "telemetry.soc_percent": { $lte: 5 } }
  ]
}).sort({ timestamp: -1 }).limit(20);

while (cursor.hasNext()) {
  printjson(cursor.next());
}

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
