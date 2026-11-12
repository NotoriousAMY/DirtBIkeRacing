import csv
import os
import sys
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

DB_CONFIG_PATH = r"C:\Users\17163\OneDrive\Documents\DirtBikeRacing\db_config.txt"
CSV_PATH       = r"C:\Users\17163\OneDrive\Documents\DirtBikeRacing\wnyhs_2026_palmyra_women.csv"

# -------------------------------------------------------
# WNYHS 2026 Palmyra - Women (13+ 100cc+)
# Transcribed from results image (page 2 of 3, printed 11/01/2026)
# -------------------------------------------------------
EVENTS = [
    {
        "date":     "11/01/2026",
        "name":     "WNYHS Palmyra",
        "location": "Palmyra, NY",
        "rows": [
            {"Place": "1",   "Number": "9015", "Name": "MATTIE SIMS",        "Location": "Duncannon, PA",       "Brand": "KTM", "Laps": "4", "Time": "01:44:10"},
            {"Place": "2",   "Number": "9003", "Name": "KELSEY MURDOCK",     "Location": "Cortland, NY",        "Brand": "KTM", "Laps": "4", "Time": "01:54:04"},
            {"Place": "3",   "Number": "9009", "Name": "EMILY HOFFMAN",      "Location": "Millport, NY",        "Brand": "HON", "Laps": "4", "Time": "01:55:35"},
            {"Place": "4",   "Number": "9006", "Name": "ERIN HARPER",        "Location": "St. Catharines, ON",  "Brand": "KTM", "Laps": "4", "Time": "01:55:40"},
            {"Place": "5",   "Number": "9018", "Name": "COLLINS HOFFMAN",    "Location": "",                    "Brand": "KTM", "Laps": "3", "Time": "01:30:32"},
            {"Place": "6",   "Number": "9023", "Name": "EMMA MILLER",        "Location": "",                    "Brand": "GG",  "Laps": "3", "Time": "01:31:26"},
            {"Place": "7",   "Number": "9007", "Name": "CALI DART",          "Location": "Hollow Spethport, F", "Brand": "HUS", "Laps": "3", "Time": "01:33:06"},
            {"Place": "8",   "Number": "9020", "Name": "KRISTEN HEARD",      "Location": "Orchard Park, NY",    "Brand": "TM",  "Laps": "3", "Time": "01:35:52"},
            {"Place": "9",   "Number": "9021", "Name": "AMY MASTERS",        "Location": "Irving, NY",          "Brand": "HUS", "Laps": "3", "Time": "01:39:55"},
            {"Place": "10",  "Number": "9017", "Name": "OLIVIA HOFFMAN",     "Location": "",                    "Brand": "KTM", "Laps": "3", "Time": "01:43:04"},
            {"Place": "11",  "Number": "9008", "Name": "BECKI WHEELER",      "Location": "Montour Falls, NY",   "Brand": "BET", "Laps": "3", "Time": "01:46:29"},
            {"Place": "12",  "Number": "9019", "Name": "HANNAH GODDARD",     "Location": "",                    "Brand": "YAM", "Laps": "3", "Time": "01:54:53"},
            {"Place": "13",  "Number": "9022", "Name": "STANLYNN COLBERT",   "Location": "",                    "Brand": "HON", "Laps": "2", "Time": "01:15:00"},
            {"Place": "14",  "Number": "9016", "Name": "SARAH HESS",         "Location": "",                    "Brand": "HON", "Laps": "2", "Time": "01:19:41"},
            {"Place": "15",  "Number": "9010", "Name": "KARYN LACHUT",       "Location": "Vernon, NY",          "Brand": "KTM", "Laps": "2", "Time": "01:25:04"},
            {"Place": "16",  "Number": "9004", "Name": "JULIANNE LANZIERI",  "Location": "Central Square, NY",  "Brand": "YAM", "Laps": "2", "Time": "01:33:00"},
            {"Place": "17",  "Number": "9024", "Name": "BRIANNE WILDRICK",   "Location": "",                    "Brand": "",    "Laps": "1", "Time": "01:30:26"},
            {"Place": "DNF", "Number": "9011", "Name": "KIERA CROSBY",       "Location": "",                    "Brand": "KTM", "Laps": "0", "Time": "00:00:00"},
        ]
    },
]

CLASS_NAME = "Women"

# -------------------------------------------------------
# Location parser
# -------------------------------------------------------
def parse_location(location_str):
    city  = None
    state = None
    if not location_str:
        return city, state
    location_str = location_str.strip()
    if "," in location_str:
        parts = location_str.split(",")
        city  = parts[0].strip() or None
        state = parts[1].strip() or None
    else:
        city = location_str or None
    return city, state

# -------------------------------------------------------
# CSV export (review before inserting)
# -------------------------------------------------------
def export_csv(path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_name", "event_date", "event_location", "class",
                    "place", "number", "racer_name", "racer_location",
                    "brand", "laps", "finish_time"])
        for event in EVENTS:
            for r in event["rows"]:
                w.writerow([event["name"], event["date"], event["location"], CLASS_NAME,
                            r["Place"], r["Number"], r["Name"].upper(), r["Location"],
                            r["Brand"], r["Laps"], r["Time"]])
    print(f"CSV written: {path}")

# -------------------------------------------------------
# DB helpers
# -------------------------------------------------------
def get_or_create_series(cur, series_name, series_desc=""):
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

def get_or_create_racer(cur, name, city, state, brand):
    name = name.strip().upper()
    cur.execute("SELECT racer_id FROM racer WHERE racer_name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """INSERT INTO racer (racer_name, racer_city, racer_state, racer_bike)
           VALUES (%s, %s, %s, %s) RETURNING racer_id""",
        (name, city or None, state or None, brand or None)
    )
    return cur.fetchone()[0]

def results_already_loaded(cur, event_id, class_id):
    cur.execute(
        "SELECT COUNT(*) FROM results WHERE event_id = %s AND class_id = %s",
        (event_id, class_id)
    )
    return cur.fetchone()[0] > 0

# -------------------------------------------------------
# Main insert function
# -------------------------------------------------------
def insert_event_results(cur, rows, event, event_id, class_id):
    inserted = 0
    for row in rows:
        name   = row.get("Name",   "").strip().upper()
        number = row.get("Number", "").strip()
        brand  = row.get("Brand",  "").strip() or None

        if not name:
            continue

        racer_city, racer_state = parse_location(row.get("Location", ""))
        racer_id = get_or_create_racer(cur, name, racer_city, racer_state, brand)

        place = row.get("Place", "").strip()
        try:
            place_numeric = int(place)
        except (ValueError, TypeError):
            place_numeric = None

        try:
            laps = int(row.get("Laps", ""))
        except (ValueError, TypeError):
            laps = None

        finish_time = row.get("Time", "").strip() or None
        if finish_time == "00:00:00":
            finish_time = None

        cur.execute(
            """INSERT INTO results
               (racer_id, event_id, class_id, place, place_numeric,
                laps, finish_time, points_earned, brand, number)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (racer_id, event_id, class_id, place, place_numeric,
             laps, finish_time, None, brand, number)
        )
        inserted += 1

    print(f"  Inserted {inserted} rows -> {event['name']} | {CLASS_NAME}")

# -------------------------------------------------------
# Run
#   python WNYHS_2026_palmyra_women_insert.py csv     -> write review CSV only
#   python WNYHS_2026_palmyra_women_insert.py insert  -> load into PostgreSQL
# -------------------------------------------------------
if __name__ == "__main__":
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "csv"

    if mode == "csv":
        export_csv(CSV_PATH)
        sys.exit(0)

    DB_CONFIG = load_db_config(DB_CONFIG_PATH)
    print("Connecting to PostgreSQL...")
    conn = None
    cur  = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()
        print("Connected.\n")

        series_id = get_or_create_series(cur, "WNYHS", "WNY Fall Hare Scramble Series")
        class_id  = get_or_create_class(cur, CLASS_NAME, CLASS_NAME)

        for event in EVENTS:
            print(f"Processing: {event['name']} {event['date']}...")
            event_date = datetime.strptime(event["date"], "%m/%d/%Y").strftime("%Y-%m-%d")
            event_city, event_state = parse_location(event["location"])
            event_id = get_or_create_event(cur, series_id, event["name"], event_date,
                                           event["location"], event_city, event_state)

            # Guard against the double-run duplicate problem
            if results_already_loaded(cur, event_id, class_id):
                print(f"  Skipped: results already exist for event_id {event_id}.")
                continue

            insert_event_results(cur, event["rows"], event, event_id, class_id)

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
