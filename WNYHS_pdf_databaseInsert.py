import pdfplumber
import psycopg2
import re
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
# All 4 WNYHS 2022 events
# -------------------------------------------------------
EVENTS = [
    {
        "pdf":      r"C:\Users\17163\OneDrive\Documents\DirtBikeRacing\pavilion Women 10 16 2022.pdf",
        "date":     "10/16/2022",
        "name":     "WNYHS Pavilion",
        "location": "Covington, NY",
        "fallback": [
            {"Place": "1",   "Number": "5010", "Name": "ERIN HARPER",          "Location": "St. Catharines, ON", "Brand": "KTM", "Laps": "6", "Time": "02:01:57"},
            {"Place": "2",   "Number": "5006", "Name": "EMILY WARFALE",        "Location": "Milport, NY",        "Brand": "HON", "Laps": "6", "Time": "02:11:39"},
            {"Place": "3",   "Number": "5008", "Name": "DESTRIE DIETEMAN",     "Location": "Oneida, NY",         "Brand": "KTM", "Laps": "6", "Time": "02:11:55"},
            {"Place": "4",   "Number": "5007", "Name": "AMY MASTERS",          "Location": "Irving, NY",         "Brand": "HUS", "Laps": "5", "Time": "01:58:09"},
            {"Place": "5",   "Number": "5009", "Name": "ANNALEISE GEISINGER",  "Location": "Sayre, PA",          "Brand": "YAM", "Laps": "4", "Time": "02:00:42"},
            {"Place": "6",   "Number": "5005", "Name": "KELSEY MURDOCK",       "Location": "Groton, NY",         "Brand": "KTM", "Laps": "2", "Time": "01:01:20"},
            {"Place": "7",   "Number": "6001", "Name": "KARYN LACHUT",         "Location": "Vernon, NY",         "Brand": "KTM", "Laps": "2", "Time": "49:24:24"},
            {"Place": "DNF", "Number": "5001", "Name": "LAURA NUTTER",         "Location": "Penfield, NY",       "Brand": "YAM", "Laps": "0", "Time": "00:00:00"},
        ]
    },
    {
        "pdf":      r"C:\Users\17163\OneDrive\Documents\DirtBikeRacing\area 51 women 10 23 2022.pdf",
        "date":     "10/23/2022",
        "name":     "WNYHS Area 51",
        "location": "Batavia, NY",
        "fallback": [
            {"Place": "1", "Number": "5010", "Name": "ERIN HARPER",          "Location": "St. Catharines, ON", "Brand": "KTM", "Laps": "6", "Time": "02:17:37"},
            {"Place": "2", "Number": "5012", "Name": "CARLEY FENNER",        "Location": "",                   "Brand": "KAW", "Laps": "6", "Time": "02:17:40"},
            {"Place": "3", "Number": "5006", "Name": "EMILY WARFALE",        "Location": "Milport, NY",        "Brand": "HON", "Laps": "6", "Time": "02:17:50"},
            {"Place": "4", "Number": "5008", "Name": "DESTRIE DIETEMAN",     "Location": "Oneida, NY",         "Brand": "KTM", "Laps": "5", "Time": "02:06:51"},
            {"Place": "5", "Number": "5007", "Name": "AMY MASTERS",          "Location": "Irving, NY",         "Brand": "HUS", "Laps": "5", "Time": "02:11:43"},
            {"Place": "6", "Number": "5011", "Name": "CALI DART",            "Location": "Hollow Spethport, F","Brand": "HUS", "Laps": "5", "Time": "02:14:28"},
            {"Place": "7", "Number": "5005", "Name": "KELSEY MURDOCK",       "Location": "Groton, NY",         "Brand": "KTM", "Laps": "5", "Time": "02:16:34"},
            {"Place": "8", "Number": "5009", "Name": "ANNALEISE GEISINGER",  "Location": "Sayre, PA",          "Brand": "KAW", "Laps": "4", "Time": "02:02:06"},
            {"Place": "9", "Number": "5003", "Name": "KARYN LACHUT",         "Location": "Vernon, NY",         "Brand": "KTM", "Laps": "3", "Time": "01:49:16"},
        ]
    },
    {
        "pdf":      r"C:\Users\17163\OneDrive\Documents\DirtBikeRacing\sick bros women 10 30 2022.pdf",
        "date":     "10/30/2022",
        "name":     "WNYHS Sick Bros",
        "location": "Cohocton, NY",
        "fallback": [
            {"Place": "1", "Number": "5010", "Name": "ERIN HARPER",          "Location": "St. Catharines, ON", "Brand": "KTM", "Laps": "6", "Time": "01:50:44"},
            {"Place": "2", "Number": "5006", "Name": "EMILY WARFALE",        "Location": "Milport, NY",        "Brand": "HON", "Laps": "6", "Time": "02:02:29"},
            {"Place": "3", "Number": "5008", "Name": "DESTRIE DIETEMAN",     "Location": "Oneida, NY",         "Brand": "KTM", "Laps": "5", "Time": "01:45:13"},
            {"Place": "4", "Number": "5013", "Name": "JULIA GOWKA",          "Location": "",                   "Brand": "KAW", "Laps": "5", "Time": "01:47:25"},
            {"Place": "5", "Number": "5005", "Name": "KELSEY MURDOCK",       "Location": "Groton, NY",         "Brand": "KTM", "Laps": "5", "Time": "01:50:36"},
            {"Place": "6", "Number": "5009", "Name": "ANNALEISE GEISINGER",  "Location": "Sayre, PA",          "Brand": "KAW", "Laps": "5", "Time": "01:56:56"},
            {"Place": "7", "Number": "5007", "Name": "AMY MASTERS",          "Location": "Irving, NY",         "Brand": "HUS", "Laps": "5", "Time": "01:58:10"},
            {"Place": "8", "Number": "5011", "Name": "CALI DART",            "Location": "Hollow Spethport, F","Brand": "HUS", "Laps": "4", "Time": "01:54:26"},
            {"Place": "9", "Number": "5004", "Name": "KARYN LACHUT",         "Location": "Vernon, NY",         "Brand": "KTM", "Laps": "1", "Time": "00:43:24"},
        ]
    },
    {
        "pdf":      r"C:\Users\17163\OneDrive\Documents\DirtBikeRacing\palmyra women 11 06 2022.pdf",
        "date":     "11/06/2022",
        "name":     "WNYHS Palmyra",
        "location": "Palmyra, NY",
        "fallback": [
            {"Place": "1",   "Number": "1500", "Name": "MALLORY CHRISTOFFERSO", "Location": "",                   "Brand": "GG",  "Laps": "5", "Time": "02:17:10"},
            {"Place": "2",   "Number": "5010", "Name": "ERIN HARPER",           "Location": "St. Catharines, ON", "Brand": "KTM", "Laps": "4", "Time": "01:56:45"},
            {"Place": "3",   "Number": "5006", "Name": "EMILY WARFALE",         "Location": "Milport, NY",        "Brand": "HON", "Laps": "4", "Time": "02:05:35"},
            {"Place": "4",   "Number": "5008", "Name": "DESTRIE DIETEMAN",      "Location": "Oneida, NY",         "Brand": "KTM", "Laps": "4", "Time": "02:06:20"},
            {"Place": "5",   "Number": "5005", "Name": "KELSEY MURDOCK",        "Location": "Groton, NY",         "Brand": "KTM", "Laps": "4", "Time": "02:10:21"},
            {"Place": "6",   "Number": "5018", "Name": "MINNIE HANSEN",         "Location": "",                   "Brand": "KTM", "Laps": "4", "Time": "02:12:00"},
            {"Place": "7",   "Number": "5017", "Name": "JESSICA KRZEMIEN",      "Location": "East Concord, NY",   "Brand": "KTM", "Laps": "4", "Time": "02:22:13"},
            {"Place": "8",   "Number": "5007", "Name": "AMY MASTERS",           "Location": "Irving, NY",         "Brand": "HUS", "Laps": "4", "Time": "02:23:12"},
            {"Place": "9",   "Number": "5011", "Name": "CALI DART",             "Location": "Hollow Spethport, F","Brand": "HUS", "Laps": "4", "Time": "02:28:08"},
            {"Place": "10",  "Number": "5014", "Name": "MAUDE LIZOTTE",         "Location": "Coaticook, ON",      "Brand": "KTM", "Laps": "3", "Time": "02:02:17"},
            {"Place": "11",  "Number": "5004", "Name": "KARYN LACHUT",          "Location": "Vernon, NY",         "Brand": "KTM", "Laps": "2", "Time": "01:42:10"},
            {"Place": "12",  "Number": "5016", "Name": "KRISTEN HEARD",         "Location": "Orchard Park, NY",   "Brand": "TM",  "Laps": "1", "Time": "00:41:13"},
            {"Place": "DNF", "Number": "5009", "Name": "ANNALEISE GEISINGER",   "Location": "Sayre, PA",          "Brand": "KAW", "Laps": "0", "Time": "00:00:00"},
        ]
    },
]

# -------------------------------------------------------
# PDF parser with fallback
# -------------------------------------------------------
def parse_pdf(pdf_path, fallback):
    rows = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text or "Women" not in text:
                    continue
                lines = text.split("\n")
                in_women = False
                for line in lines:
                    line = line.strip()
                    if re.match(r'^Women\s*$', line, re.IGNORECASE):
                        in_women = True
                        continue
                    if in_women and re.match(r'^(Beginner|Novice|Amateur|Expert|Junior|Senior|Printed:|Mini)', line, re.IGNORECASE):
                        in_women = False
                        continue
                    if not in_women:
                        continue
                    m = re.match(
                        r'^(DNF|\d+)\s+(\d+)\s+(.+?)\s{2,}(.+?)?\s+(KTM|HON|YAM|KAW|HUS|SUZ|GAS|GG|N\/A|TM|BET|N/A)\s+(\d+)\s+(\d{2}:\d{2}:\d{2})',
                        line
                    )
                    if m:
                        rows.append({
                            "Place":    m.group(1),
                            "Number":   m.group(2),
                            "Name":     m.group(3).strip().upper(),
                            "Location": m.group(4).strip() if m.group(4) else "",
                            "Brand":    m.group(5),
                            "Laps":     m.group(6),
                            "Time":     m.group(7),
                        })
    except FileNotFoundError:
        print(f"  WARNING: PDF not found, using fallback data.")

    if len(rows) < 5:
        print(f"  Regex parse incomplete - using fallback data.")
        rows = fallback

    return rows

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
    # Name always stored as UPPERCASE for consistency
    name = name.strip().upper()
    cur.execute("SELECT racer_id FROM racer WHERE racer_name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """INSERT INTO racer (racer_name, racer_city, racer_state, racer_bike)
           VALUES (%s, %s, %s, %s) RETURNING racer_id""",
        (
            name,
            city  if city  else None,
            state if state else None,
            brand if brand else None
        )
    )
    return cur.fetchone()[0]

# -------------------------------------------------------
# Main insert function
# -------------------------------------------------------
def insert_event_results(cur, rows, event, series_id, event_id, class_id):
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

        laps = row.get("Laps", "")
        try:
            laps = int(laps)
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
            (
                racer_id, event_id, class_id,
                place, place_numeric,
                laps, finish_time,
                None,
                brand, number
            )
        )
        inserted += 1

    print(f"  Inserted {inserted} rows → {event['name']} | Women")

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

    # Truncate results and racer before reload
    # cur.execute("TRUNCATE TABLE results RESTART IDENTITY")
    # cur.execute("TRUNCATE TABLE racer   RESTART IDENTITY CASCADE")
    # print("Results and Racer tables cleared.\n")

    series_id = get_or_create_series(cur, "WNYHS", "WNY Fall Hare Scramble Series")
    class_id  = get_or_create_class(cur, "Women", "Women")

    for event in EVENTS:
        print(f"Processing: {event['name']} {event['date']}...")

        rows = parse_pdf(event["pdf"], event["fallback"])

        try:
            event_date = datetime.strptime(event["date"], "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            event_date = None

        event_city, event_state = parse_location(event["location"])

        event_id = get_or_create_event(
            cur, series_id,
            event["name"], event_date,
            event["location"],
            event_city,
            event_state
        )

        insert_event_results(cur, rows, event, series_id, event_id, class_id)

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
