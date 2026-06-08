import requests
from bs4 import BeautifulSoup
import psycopg2
import re
import time
from datetime import datetime

YEARS        = ["2021", "2022"]
TARGET_CLASS = "15. WOMEN"
HEADERS      = {"User-Agent": "Mozilla/5.0"}

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
# Scraper helpers
# -------------------------------------------------------
def get_soup(url, retries=3, timeout=30):
    for attempt in range(retries):
        try:
            time.sleep(1 + attempt)
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            if response.status_code != 200:
                return None
            return BeautifulSoup(response.text, "html.parser")
        except requests.exceptions.RequestException as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt == retries - 1:
                print(f"  All {retries} attempts failed, skipping.")
                return None

# -------------------------------------------------------
# Location parser - splits "VAN ETTEN, NY" into city + state
# -------------------------------------------------------
def parse_location(location_str):
    city  = None
    state = "NY"
    if not location_str:
        return city, state
    location_str = location_str.strip()
    if "," in location_str:
        parts = location_str.split(",")
        city  = parts[0].strip() or None
        state = parts[1].strip() or "NY"
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

def get_or_create_racer(cur, name, number, brand):
    cur.execute("SELECT racer_id FROM racer WHERE racer_name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """INSERT INTO racer (racer_name, racer_number, racer_bike)
           VALUES (%s, %s, %s) RETURNING racer_id""",
        (
            name,
            number if number else None,
            brand  if brand  else None
        )
    )
    return cur.fetchone()[0]

def insert_result(cur, record, series_id, event_id, class_id):
    name   = record.get("Name",   "").strip()
    number = record.get("Nbr",    "").strip()
    brand  = record.get("Brand",  "").strip() or None

    if not name:
        return

    racer_id = get_or_create_racer(cur, name, number, brand)

    place = record.get("Class Finish", "").strip()
    try:
        place_numeric = int(place)
    except (ValueError, TypeError):
        place_numeric = None

    laps = record.get("Laps", "")
    try:
        laps = int(laps)
    except (ValueError, TypeError):
        laps = None

    finish_time = record.get("Elapsed Time", "").strip() or None

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

# -------------------------------------------------------
# Main scrape + load loop
# -------------------------------------------------------
print("Connecting to PostgreSQL...")
conn = None
cur  = None

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    print("Connected.\n")

  #  cur.execute("TRUNCATE TABLE results RESTART IDENTITY")
  #  cur.execute("TRUNCATE TABLE racer   RESTART IDENTITY CASCADE")
  #  print("Results and Racer tables cleared.\n")

    for YEAR in YEARS:
        BASE_URL    = f"https://www.xcracing.com/wnyoa/archive/{YEAR}"
        RESULTS_URL = f"{BASE_URL}/results.asp?f=9"

        print(f"\n{'='*50}")
        print(f"Processing year: {YEAR}")
        print(f"{'='*50}")

        print("Fetching event list...")
        soup = get_soup(RESULTS_URL)

        if soup is None:
            print(f"  Could not load results page for {YEAR}, skipping.")
            continue

        events = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "class_list.asp" in href:
                full_url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"
                label = a.get_text(strip=True)
                parts = label.split(" - ")
                if len(parts) >= 3:
                    events.append({
                        "url":      full_url,
                        "date":     parts[0].strip(),
                        "name":     parts[1].strip(),
                        "location": parts[2].strip(),
                        "year":     YEAR,
                    })

        print(f"Found {len(events)} events.")

        series_id = get_or_create_series(cur, "WNYOA", "WNY Off-Road Association")
        class_id  = get_or_create_class(cur, TARGET_CLASS, "Women")

        for event in events:
            print(f"\nProcessing: {event['date']} - {event['name']}")
            soup = get_soup(event["url"])

            if soup is None:
                print("  Skipping - could not load event page.")
                continue

            # Find the Women's class link
            class_link = None
            for a in soup.find_all("a", href=True):
                if TARGET_CLASS.lower() in a.get_text(strip=True).lower() and "class.asp" in a["href"]:
                    class_link = a["href"]
                    break

            if not class_link:
                print(f"  No '{TARGET_CLASS}' class found, skipping.")
                continue

            class_url = class_link if class_link.startswith("http") else f"{BASE_URL}/{class_link.lstrip('/')}"

            # Parse event date into YYYY-MM-DD for PostgreSQL
            try:
                event_date = datetime.strptime(event["date"], "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                event_date = None

            # Parse location into city and state
            event_city, event_state = parse_location(event["location"])
            print(f"  Location: {event['location']} → city={event_city} state={event_state}")

            event_id = get_or_create_event(
                cur, series_id,
                event["name"], event_date,
                event["location"],
                event_city,
                event_state
            )

            # ---------------------------------------------
            # Scrape and insert class finish results
            # ---------------------------------------------
            soup = get_soup(class_url)

            if soup is None:
                print("  Skipping class results - could not load page.")
                continue

            inserted = 0
            for row in soup.find_all("tr"):
                cells = row.find_all("td")
                if not cells:
                    continue

                text  = row.get_text(" ", strip=True)
                parts = text.split()
                if not parts:
                    continue

                place = parts[0]
                if place not in [str(i) for i in range(1, 50)] + ["DNF", "DNS"]:
                    continue

                elapsed_match = re.search(r'(\d{2}:\d{2}:\d{2}\.\d+)', text)
                brand_match   = re.search(r'\b(KTM|KAW|HON|YAM|HSQ|BET|OTH|SUZ|HUS|GAS|ATK)\b', text)

                elapsed = elapsed_match.group(1) if elapsed_match else ""
                brand   = brand_match.group(1)   if brand_match   else ""

                laps = ""
                if elapsed:
                    before_elapsed = text[:text.index(elapsed)].strip()
                    laps_match = re.search(r'(\d+)\s*$', before_elapsed)
                    if laps_match:
                        laps = laps_match.group(1)

                overall = parts[1] if len(parts) > 1 else ""
                nbr     = parts[2] if len(parts) > 2 else ""

                name_tag = row.find("a", href=lambda h: h and "racer.asp" in h)
                name = name_tag.get_text(strip=True) if name_tag else ""

                record = {
                    "Class Finish": place,
                    "Nbr":          nbr,
                    "Name":         name,
                    "Brand":        brand,
                    "Laps":         laps,
                    "Elapsed Time": elapsed,
                }

                insert_result(cur, record, series_id, event_id, class_id)
                inserted += 1

            print(f"  Inserted {inserted} rows → {event['name']} | {TARGET_CLASS}")

            # ---------------------------------------------
            # LAP TIMES - commented out, not needed
            # ---------------------------------------------
            # lap_url = class_url.replace("class.asp", "laptimes.asp")
            # soup = get_soup(lap_url)
            # if soup:
            #     for row in soup.find_all("tr"):
            #         cells = row.find_all("td")
            #         if not cells:
            #             continue
            #         text  = row.get_text(" ", strip=True)
            #         parts = text.split()
            #         if not parts:
            #             continue
            #         finish = parts[0]
            #         if finish not in [str(i) for i in range(1, 50)] + ["DNF", "DNS"]:
            #             continue
            #         name_tag = row.find("a", href=lambda h: h and "racer.asp" in h)
            #         name = name_tag.get_text(strip=True) if name_tag else ""
            #         all_times   = re.findall(r'\d{2}:\d{2}:\d{2}\.\d+', text)
            #         actual_laps = all_times[::3] if all_times else []

    # -------------------------------------------------------
    # Commit everything
    # -------------------------------------------------------
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