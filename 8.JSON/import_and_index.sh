#!/bin/bash

mongosh

# Import the JSON telemetry data into MongoDB
mongoimport --db sensorDB --collection telemetry --file /opt/undata/telemetry_data.json

### Indexing by Timestamp, Equipment ID, and Error Codes
```javascript
use sensorDB;

// Index by timestamp for range queries and chronological sorting
db.telemetry.createIndex({ timestamp: -1 });

// Index by equipment_id to quickly isolate individual machinery/devices
db.telemetry.createIndex({ equipment_id: 1 });

// Index by error codes for fast failure categorization and filtering
db.telemetry.createIndex({ error_codes: 1 });

// Retrieve recent telemetry logs matching battery-related failure codes
db.telemetry.find({
  $or: [
    { error_codes: { $in: ["BAT_FAIL", "BATTERY_LOW", "CELL_VOLTAGE_DROP"] } },
    { "diagnostics.battery_status": "failed" },
    { error_codes: { $regex: /battery/i } }
  ]
}).sort({ timestamp: -1 }).limit(100);