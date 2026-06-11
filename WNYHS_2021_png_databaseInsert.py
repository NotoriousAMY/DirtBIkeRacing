import psycopg2
from datetime import datetime

# -------------------------------------------------------
# Load database connection settings from config file
# -------------------------------------------------------
def load_db_config(filepath):
    config = {}
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    config["port"] = int(config["port"])
    return config

DB_CONFIG = load_db_config(r"C:\Users\17163\OneDrive\Documents\DirtBikeRacing\db_config.txt")

# -------------------------------------------------------
# Name normalization lookup
# Maps source typos / alternate spellings → canonical name
# Add entries here whenever a new variant is found
# -------------------------------------------------------
NAME_CORRECTIONS = {
    "MURDCK, KELSEY":  "MURDOCK, KELSEY",
    "MURDCK KELSEY":   "MURDOCK, KELSEY",
}

def normalize_name(name):
    name = name.strip().upper()
    return NAME_CORRECTIONS.get(name, name)

# -------------------------------------------------------
# Data extracted from PNG result screenshots
# Source: Area_51_Womens_10-25-2021.PNG
#         Palmyra_Womens_11-07-2021.PNG
#
# finish_time = sum of individual lap times from source image.
# The "Finish Time" column in the source is NOT a race duration
# and is intentionally ignored.
# -------------------------------------------------------
EVENTS = [
    {
        "name":     "WNYHS Area 51",
        "date":     "10/24/2021",
        "location": "Batavia, NY",
        "city":     "Batavia",
        "state":    "NY",
        "results": [
            {"Place": "1",   "Name": "WARFALE, EMILY",    "Brand": "YAM", "Laps": "5", "FinishTime": "02:20:13"},
            {"Place": "2",   "Name": "MASTERS, AMY",      "Brand": "HUS", "Laps": "4", "FinishTime": "02:00:06"},
            {"Place": "3",   "Name": "WHEELER, BECKI",    "Brand": "HON", "Laps": "4", "FinishTime": "02:05:43"},
            {"Place": "4",   "Name": "DIETEMAN, DESTRIE", "Brand": "KTM", "Laps": "4", "FinishTime": "02:08:16"},
            {"Place": "5",   "Name": "OCONNOR, ASHLEY",   "Brand": "HON", "Laps": "3", "FinishTime": "02:06:53"},
            {"Place": "6",   "Name": "MURDCK, KELSEY",    "Brand": "HON", "Laps": "3", "FinishTime": "02:10:55"},
            {"Place": "7",   "Name": "KING, CLORISSA",    "Brand": "KAW", "Laps": "2", "FinishTime": "01:24:10"},
            {"Place": "8",   "Name": "LACHUT, KARYN",     "Brand": "KTM", "Laps": "2", "FinishTime": "01:54:13"},
            {"Place": "9",   "Name": "NUTTER, LAURA",     "Brand": "YAM", "Laps": "1", "FinishTime": "01:21:14"},
        ]
    },
    {
        "name":     "WNYHS Palmyra",
        "date":     "11/07/2021",
        "location": "Palmyra, NY",
        "city":     "Palmyra",
        "state":    "NY",
        "results": [
            {"Place": "1",   "Name": "EBERHARDT, MALLORY", "Brand": "KTM", "Laps": "4", "FinishTime": "01:34:52"},
            {"Place": "2",   "Name": "WARFALE, EMILY",     "Brand": "HON", "Laps": "4", "FinishTime": "01:51:52"},
            {"Place": "3",   "Name": "MASTERS, AMY",       "Brand": "HUS", "Laps": "4", "FinishTime": "01:53:50"},
            {"Place": "4",   "Name": "OCONNOR, ASHLEY",    "Brand": "HON", "Laps": "3", "FinishTime": "02:28:51"},
            {"Place": "5",   "Name": "DIETEMAN, DESTRIE",  "Brand": "KTM", "Laps": "3", "FinishTime": "01:58:19"},
            {"Place": "6",   "Name": "KING, CLORISSA",     "Brand": "KAW", "Laps": "2", "FinishTime": "01:58:08"},
            {"Place": "7",   "Name": "MURDCK, KELSEY",     "Brand": "HON", "Laps": "1", "FinishTime": "00:39:02"},
            {"Place": "8",   "Name": "LACHUT, KARYN",      "Brand": "KTM", "Laps": "1", "FinishTime": "00:46:55"},
            {"Place": "9",   "Name": "NUTTER, LAURA",      "Brand": "YAM", "Laps": "1", "FinishTime": "01:10:11"},
            {"Place": "DNF", "Name": "BROWER, OLIVIA",     "Brand": "KTM", "Laps": None, "FinishTime": None},
        ]
    },
]

# -------------------------------------------------------
# DB helper functions (get or create pattern)
# -------------------------------------------------------
def get_or_create_series(cur, series_name, series_desc):
    cur.execute("SELECT series_id FROM series WHERE series_name = %s", (series_name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO series (series_name, series_desc) VALUES (%s, %s) RETURNING series_id",
        (series_name, series_desc)
    )
    return cur.fetchone()[0]

def get_or_create_event(cur, series_id, event_name, event_date, location, city, state):
    cur.execute(
        "SELECT event_id FROM event WHERE event_name = %s AND event_date = %s",
        (event_name, event_date)
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """INSERT INTO event (series_id, event_name, event_date, location, city, state)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING event_id""",
        (series_id, event_name, event_date, location, city, state)
    )
    return cur.fetchone()[0]

def get_or_create_class(cur, class_name, class_type):
    cur.execute("SELECT class_id FROM class WHERE class_name = %s", (class_name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO class (class_name, class_class) VALUES (%s, %s) RETURNING class_id",
        (class_name, class_type)
    )
    return cur.fetchone()[0]

def get_or_create_racer(cur, name, brand):
    # normalize_name handles source typos before the DB lookup
    name = normalize_name(name)
    cur.execute("SELECT racer_id FROM racer WHERE racer_name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """INSERT INTO racer (racer_name, racer_bike)
           VALUES (%s, %s) RETURNING racer_id""",
        (name, brand if brand else None)
    )
    return cur.fetchone()[0]

# -------------------------------------------------------
# Insert results for one event
# -------------------------------------------------------
def insert_event_results(cur, event_data, event_id, class_id):
    inserted = 0
    for row in event_data["results"]:
        name  = row.get("Name",  "").strip()
        brand = row.get("Brand", "").strip() or None

        if not name:
            continue

        racer_id = get_or_create_racer(cur, name, brand)

        place = row.get("Place", "").strip()
        try:
            place_numeric = int(place)
        except (ValueError, TypeError):
            place_numeric = None   # DNF → NULL

        laps = row.get("Laps")
        try:
            laps = int(laps) if laps is not None else None
        except (ValueError, TypeError):
            laps = None

        finish_time = row.get("FinishTime") or None

        cur.execute(
            """INSERT INTO results
               (racer_id, event_id, class_id, place, place_numeric,
                laps, finish_time, points_earned, brand)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                racer_id, event_id, class_id,
                place, place_numeric,
                laps,
                finish_time,
                None,   # points_earned unknown
                brand
            )
        )
        inserted += 1

    print(f"  Inserted {inserted} rows → {event_data['name']} | Women")

# -------------------------------------------------------
# Connect and process all events
# -------------------------------------------------------
print("Connecting to PostgreSQL...")
conn = None
cur  = None

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    print("Connected.\n")

    series_id = get_or_create_series(cur, "WNYHS", "WNY Fall Hare Scramble Series")

    class_id  = get_or_create_class(cur, "Women", "Women")

    for event in EVENTS:
        print(f"Processing: {event['name']} {event['date']}...")

        try:
            event_date = datetime.strptime(event["date"], "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            event_date = None

        event_id = get_or_create_event(
            cur, series_id,
            event["name"], event_date,
            event["location"],
            event["city"],
            event["state"]
        )

        insert_event_results(cur, event, event_id, class_id)

    conn.commit()
    print("\nAll records committed to PostgreSQL successfully.")

except Exception as e:
    print(f"\nError: {e}")
    if conn:
        conn.rollback()
        print("Transaction rolled back.")

finally:
    if cur:  cur.close()
    if conn: conn.close()
    print("Connection closed.")

print("\nDone!")