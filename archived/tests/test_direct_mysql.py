import mysql.connector
import time

conn = mysql.connector.connect(
    host='10.0.0.160',
    port=3306,
    user='brian',
    password='Fl1p5ma5h!',
    database='vocab'
)

cursor = conn.cursor()

print("Testing simple queries...")

# Test 1: Show tables
print("1. Listing tables...")
start = time.time()
cursor.execute("SHOW TABLES")
tables = cursor.fetchall()
print(f"Found {len(tables)} tables in {time.time()-start:.2f}s")
for table in tables[:5]:  # Show first 5
    print(f"  - {table[0]}")

  # Test 2: Check if 'defined' table exists
if ('defined',) in tables:
    print("\n2. 'defined' table exists")

    # Test 3: Simple select without COUNT
    print("3. Testing simple SELECT...")
    start = time.time()
    cursor.execute("SELECT id, term FROM defined LIMIT 5")
    results = cursor.fetchall()
    print(f"Got {len(results)} rows in {time.time()-start:.2f}s")
    for row in results:
        print(f"  - {row[0]}: {row[1]}")
else:
    print("\n2. 'defined' table NOT FOUND!")
    print("Available tables:", [t[0] for t in tables])

conn.close()