import requests
from bs4 import BeautifulSoup
import pandas as pd
import psycopg2
import re

# -------------------------------------------------------
#requests --  fetches the page 
#BeautifulSoup -- parses the HTML 
#re -- cleans the messy text (regular expression)
#pandas -- organizes it into a dataframe 
#psycopg2 -- loads it into PostgreSQL
# -------------------------------------------------------

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
#location of db_config file 
DB_CONFIG = load_db_config(r"C:\Users\17163\OneDrive\Documents\DirtBikeRacing\db_config.txt")

HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_soup(url):
    response = requests.get(url, headers=HEADERS)
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")
# -------------------------------------------------------
# BeautifulSoup parser - brand from image
# -------------------------------------------------------
def parse_results_table(soup):
    rows = []
    seen_names = set()
    tables = soup.find_all("table")

    for table in tables:
        trs = table.find_all("tr")
        for tr in trs:
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue

            overall_text = tds[0].get_text(" ").strip()

            # Strict place match only
            if not re.match(r'^(\d{1,3}(st|nd|rd|th)|DNS|DNF)\b', overall_text, re.IGNORECASE):
                continue

            # Brand - get from image src or alt attribute
            brand = None
            img = tds[1].find("img")
            if img:
                alt = img.get("alt", "").strip()
                if alt and len(alt) <= 15:
                    brand = alt
                else:
                    src = img.get("src", "")
                    if src:
                        filename  = src.split("/")[-1]
                        name_only = filename.split(".")[0]
                        brand     = name_only.upper() if name_only else None
            else:
                brand_raw = tds[1].get_text().strip().replace('\n','').replace('\r','').strip()
                brand = brand_raw if brand_raw and len(brand_raw) <= 15 else None

            # Name cell - split on newlines to separate name from city
            name_cell_lines = [
                l.strip() for l in tds[2].get_text("\n").split("\n")
                if l.strip()
            ]
            name = name_cell_lines[0] if name_cell_lines else ""

            if not name or name.upper() in ("NAME", "OVERALL"):
                continue
            if name in seen_names:
                continue
            seen_names.add(name)

            # City/state from second non-empty line
            city  = None
            state = None
            if len(name_cell_lines) > 1:
                location = name_cell_lines[1].strip()
                if "," in location:
                    loc_parts = location.split(",")
                    city  = loc_parts[0].strip() or None
                    state = loc_parts[1].strip() or None
                elif location:
                    city = location or None

            # Points - grab all numbers, take the last one, cap at 999
            points_raw  = tds[5].get_text().strip() if len(tds) > 5 else ""
            points_nums = re.findall(r'\d+', points_raw)
            if points_nums:
                last_num = int(points_nums[-1])
                points = last_num if last_num <= 999 else None
            else:
                points = None

            # Place and number
            parts     = overall_text.split()
            place_raw = parts[0] if parts else ""
            number    = parts[1] if len(parts) > 1 else ""

            place_clean = place_raw.lower()
            for suffix in ["st", "nd", "rd", "th"]:
                place_clean = place_clean.replace(suffix, "")
            try:
                place_numeric = int(place_clean)
                place = str(place_numeric)
            except (ValueError, TypeError):
                place = place_raw.upper()
                place_numeric = None

            rows.append({
                "Place":         place,
                "Place_Numeric": place_numeric,
                "Number":        number,
                "Brand":         brand,
                "Name":          name,
                "City":          city,
                "State":         state,
                "Points":        points
            })

    return pd.DataFrame(rows)

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

def get_or_create_racer(cur, name, number, city, state, bike):
    cur.execute("SELECT racer_id FROM racer WHERE racer_name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        """INSERT INTO racer (racer_name, racer_number, racer_city, racer_state, racer_bike)
           VALUES (%s, %s, %s, %s, %s) RETURNING racer_id""",
        (
            name,
            number if number and str(number) != "nan" else None,
            city   if city   and str(city)   != "nan" else None,
            state  if state  and str(state)  != "nan" else None,
            bike   if bike   and str(bike)   != "nan" else None
        )
    )
    return cur.fetchone()[0]

# -------------------------------------------------------
# Main insert function
# -------------------------------------------------------
def insert_results(cur, df, series_name, series_desc,
                   event_name, event_date, location, city, state,
                   class_name, class_type):

    series_id = get_or_create_series(cur, series_name, series_desc)
    event_id  = get_or_create_event(cur, series_id, event_name, event_date, location, city, state)
    class_id  = get_or_create_class(cur, class_name, class_type)

    inserted = 0
    for _, row in df.iterrows():
        name  = str(row.get("Name", "")).strip()
        if not name or name.lower() == "nan":
            continue

        number      = str(row.get("Number", "")).strip()
        brand       = row.get("Brand",  None)
        racer_city  = row.get("City",   None)
        racer_state = row.get("State",  None)
        place       = str(row.get("Place", "")).strip()

        # Force native Python int to avoid numpy int64 overflow
        try:
            place_numeric = int(row.get("Place_Numeric")) if row.get("Place_Numeric") is not None else None
        except (ValueError, TypeError):
            place_numeric = None

        try:
            points = int(row.get("Points")) if row.get("Points") is not None else None
            if points is not None and points > 999:
                points = None
        except (ValueError, TypeError):
            points = None

        racer_id = get_or_create_racer(cur, name, number, racer_city, racer_state, brand)

        cur.execute(
            """INSERT INTO results
               (racer_id, event_id, class_id, place, place_numeric,
                laps, finish_time, points_earned, brand, number)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                racer_id, event_id, class_id,
                place, place_numeric,
                None, None,
                points,
                brand, number
            )
        )
        inserted += 1

    print(f"  Inserted {inserted} rows → {event_name} | {class_name}")

# -------------------------------------------------------
# Scrape PAGE 1: Women 13+ - Area 51 MX 10/25/2020
# -------------------------------------------------------
print("Fetching Women 13+ - Area 51 MX...")
soup1 = get_soup("https://resultsmx.com/empirestate/class.asp?s=50&e=400&c=373&h=11708")
df_women = parse_results_table(soup1)
print(f"  Racers found: {len(df_women)}")
print(df_women[["Place", "Number", "Brand", "Name", "City", "State"]].to_string())

# -------------------------------------------------------
# Scrape PAGE 2: Beginner Over 18 - Pavilion 10/20/2019
# -------------------------------------------------------
print("\nFetching Beginner Over 18 - Pavilion...")
soup2 = get_soup("https://resultsmx.com/empirestate/class.asp?s=45&e=363&c=427&h=11708")
df_beg = parse_results_table(soup2)
print(f"  Racers found: {len(df_beg)}")
print(df_beg[["Place", "Number", "Brand", "Name", "City", "State"]].head(10).to_string())

# -------------------------------------------------------
# Connect and insert into PostgreSQL
# -------------------------------------------------------
print("\nConnecting to PostgreSQL...")
conn = None
cur  = None

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    print("Connected.\n")

    cur.execute("TRUNCATE TABLE results RESTART IDENTITY")
    cur.execute("TRUNCATE TABLE racer   RESTART IDENTITY CASCADE")
    print("Results and Racer tables cleared.\n")

    insert_results(
        cur, df_women,
        series_name  = "Empire State",
        series_desc  = "Empire State MX Series",
        event_name   = "Area 51 MX",
        event_date   = "2020-10-25",
        location     = "Area 51 MX",
        city         = "Batavia",
        state        = "NY",
        class_name   = "Women 13+",
        class_type   = "Women"
    )

    insert_results(
        cur, df_beg,
        series_name  = "Empire State",
        series_desc  = "Empire State MX Series",
        event_name   = "Pavilion Hare Scramble",
        event_date   = "2019-10-20",
        location     = "Pavilion",
        city         = "Covington",
        state        = "NY",
        class_name   = "Beginner Over 18",
        class_type   = "Beginner"
    )

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