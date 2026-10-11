import csv, random
from datetime import date, timedelta

print("Generating 500,000 rows...")
with open('/opt/data/large_dispatches.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    for i in range(500000):
        writer.writerow([
            f"DSP-{900000+i}", f"EQ-{(i%5000)+1}", date(2024, 1, 1) + timedelta(days=i%730),
            (i % 50) + 1, (i % 20) + 1, round(random.uniform(1, 8), 2),
            round(random.uniform(100, 1000), 2), "Routine maintenance", (i % 5) + 1
        ])
print("Done! Saved to /opt/data/large_dispatches.csv")