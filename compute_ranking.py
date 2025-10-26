import requests
import csv
from datetime import datetime, timedelta
from fuzzywuzzy import fuzz
import json


# CONFIG
NPI_CSV = "facilities.csv"
OUTPUT_CSV = "prime_companies_ranked.csv"

START_DATE = "2020-01-01T00:00:00Z"
END_DATE = "2025-10-19T23:59:59Z"

FUZZY_MATCH_THRESHOLD = 85

# Relevance weight constants
HIGH_RELEVANCE = 5
MEDIUM_RELEVANCE = 3
LOW_RELEVANCE = 1


# ANZSIC RELEVANCE WEIGHTS
ANZSIC_WEIGHTS = {
    # Mining & Extraction (High)
    "0600": HIGH_RELEVANCE, "0700": HIGH_RELEVANCE, "0800": HIGH_RELEVANCE,
    "0911": HIGH_RELEVANCE, "0919": HIGH_RELEVANCE, "0990": HIGH_RELEVANCE,

    # Manufacturing (Medium)
    "1111": MEDIUM_RELEVANCE, "1131": MEDIUM_RELEVANCE, "1210": MEDIUM_RELEVANCE,
    "1311": MEDIUM_RELEVANCE, "1411": MEDIUM_RELEVANCE, "1412": MEDIUM_RELEVANCE,
    "1413": MEDIUM_RELEVANCE, "1491": MEDIUM_RELEVANCE, "1492": MEDIUM_RELEVANCE,
    "1493": MEDIUM_RELEVANCE, "1499": MEDIUM_RELEVANCE, "1510": MEDIUM_RELEVANCE,
    "1521": MEDIUM_RELEVANCE, "1611": MEDIUM_RELEVANCE, "1700": MEDIUM_RELEVANCE,
    "1800": MEDIUM_RELEVANCE, "1811": MEDIUM_RELEVANCE, "1821": MEDIUM_RELEVANCE,
    "1831": MEDIUM_RELEVANCE, "1841": MEDIUM_RELEVANCE, "1911": MEDIUM_RELEVANCE,
    "1920": MEDIUM_RELEVANCE, "2010": MEDIUM_RELEVANCE, "2021": MEDIUM_RELEVANCE,
    "2029": MEDIUM_RELEVANCE, "2031": MEDIUM_RELEVANCE, "2034": MEDIUM_RELEVANCE,
    "2110": MEDIUM_RELEVANCE, "2121": MEDIUM_RELEVANCE, "2131": MEDIUM_RELEVANCE,
    "2139": MEDIUM_RELEVANCE, "2210": MEDIUM_RELEVANCE, "2221": MEDIUM_RELEVANCE,
    "2299": MEDIUM_RELEVANCE, "2311": MEDIUM_RELEVANCE, "2411": MEDIUM_RELEVANCE,
    "2462": MEDIUM_RELEVANCE, "2499": MEDIUM_RELEVANCE, "2511": MEDIUM_RELEVANCE,

    # Utilities & Waste (High)
    "2611": HIGH_RELEVANCE, "2621": HIGH_RELEVANCE, "2630": HIGH_RELEVANCE,
    "2811": HIGH_RELEVANCE, "2911": HIGH_RELEVANCE, "2921": HIGH_RELEVANCE,
    "2922": HIGH_RELEVANCE, "2923": HIGH_RELEVANCE,

    # Construction & Heavy Engineering (Medium)
    "3011": MEDIUM_RELEVANCE, "3101": MEDIUM_RELEVANCE, "3109": MEDIUM_RELEVANCE,
    "3231": MEDIUM_RELEVANCE, "3239": MEDIUM_RELEVANCE,

    # Agriculture & Forestry (High)
    "0111": HIGH_RELEVANCE, "0121": HIGH_RELEVANCE, "0139": HIGH_RELEVANCE,
    "0141": HIGH_RELEVANCE, "0142": HIGH_RELEVANCE, "0144": HIGH_RELEVANCE,
    "0145": HIGH_RELEVANCE, "0160": HIGH_RELEVANCE, "0171": HIGH_RELEVANCE,
    "0191": MEDIUM_RELEVANCE, "0411": MEDIUM_RELEVANCE, "0510": MEDIUM_RELEVANCE,

    # Scientific & Environmental Services (Medium)
    "6910": MEDIUM_RELEVANCE, "6922": MEDIUM_RELEVANCE, "6925": MEDIUM_RELEVANCE
}

# FUNCTIONS

def load_npi_companies(csv_file):
    # Load NPI companies from CSV into a dict keyed by ABN.
    companies = {}
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            abn = row.get("abn", "").strip()
            name = row.get("registered_business_name", "").strip()
            anzsic = row.get("primary_anzsic_class_code", "").strip()
            companies[abn] = {
                "name": name,
                "anzsic": anzsic,
                "matched_tenders": []
            }
    return companies


def fetch_tenders_day(start_date, end_date):
    # Fetch tenders from AusTender API in 1-day batches.
    all_tenders = []
    start = start_date

    while start < end_date:
        batch_end = min(start + timedelta(days=1), end_date)
        url = f"https://api.tenders.gov.au/ocds/findByDates/contractStart/{start.isoformat()}Z/{batch_end.isoformat()}Z"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            tenders = data.get("releases", [])
            for i in range(len(tenders)):
                if isinstance(tenders[i], str):
                    tenders[i] = json.loads(tenders[i])
            all_tenders.extend(tenders)
            print(f"📦 {len(tenders)} tenders fetched for {start.date()} → {batch_end.date()}")
        except Exception as e:
            print(f"Error fetching tenders for {start.date()} → {batch_end.date()}: {e}")

        start = batch_end
    return all_tenders


def match_company_to_tender(npi_companies, tender, global_stats):
# Match NPI companies with tenders by ABN or fuzzy name. Tracks global min/max tender values across all tenders.
    parties = tender.get("parties", [])
    contracts = tender.get("contracts", [])
    contract_info = []

    for c in contracts:
        title = c.get("title", "")
        period = c.get("period", {})
        start_date = period.get("startDate", "")
        end_date = period.get("endDate", "")
        value = float(c.get("value", {}).get("amount", 0))

        # Update global tender stats
        if value > 0:
            global_stats["max_value"] = max(global_stats["max_value"], value)
            global_stats["min_value"] = min(global_stats["min_value"], value)

        contract_info.append({
            "title": title,
            "start": start_date,
            "end": end_date,
            "value": value
        })

    # Match suppliers in tender to NPI companies
    for party in parties:
        if "supplier" not in party.get("roles", []):
            continue

        abn = None
        for iden in party.get("additionalIdentifiers", []):
            if iden.get("scheme") == "AU-ABN":
                abn = iden.get("id")
                break

        name = party.get("name", "").strip().lower()

        # Direct ABN match
        if abn and abn in npi_companies:
            npi_companies[abn]["matched_tenders"].extend(contract_info)

        # Fuzzy name match
        else:
            for comp_abn, comp_data in npi_companies.items():
                ratio = fuzz.token_set_ratio(comp_data["name"].lower(), name)
                if ratio >= FUZZY_MATCH_THRESHOLD:
                    npi_companies[comp_abn]["matched_tenders"].extend(contract_info)

    return


# SCORING FUNCTIONS

def compute_anzsic_score(anzsic_code):
    return ANZSIC_WEIGHTS.get(anzsic_code[:4], LOW_RELEVANCE)

def compute_tender_score(tenders, global_stats):
    # Compute a 1-5 tender performance score based on tender list and global min/max.
    if not tenders:
        return 1

    total_value = sum(t.get("value", 0) for t in tenders if t.get("value"))
    num_tenders = len(tenders)

    min_val = global_stats.get("min_value", 0)
    max_val = global_stats.get("max_value", 1)
    if max_val == min_val:
        value_norm = 0
    else:
        value_norm = (total_value - min_val) / (max_val - min_val)
        value_norm = max(0, min(1, value_norm))

    weight_value = 0.7
    weight_count = 0.3
    count_norm = min(num_tenders / 10, 1.0)

    combined = (weight_value * value_norm) + (weight_count * count_norm)
    score = 1 + (combined * 4)
    return round(score, 2)



def compute_lead_score(anzsic_code, tenders, global_stats):
    anzsic_score = compute_anzsic_score(anzsic_code)
    tender_score = compute_tender_score(tenders, global_stats)
    lead_score = round((anzsic_score * 0.6) + (tender_score * 0.4), 2)
    return lead_score, anzsic_score, tender_score


# SAVE OUTPUT

def save_prime_companies(npi_companies, global_stats):
    fieldnames = ["rank", "registered_business_name", "abn", "anzsic_code",
                  "number_of_tenders", "anzsic_score", "tender_score", "lead_score"]

    ranked = []
    for abn, data in npi_companies.items():
        tenders = data["matched_tenders"]
        if not tenders:
            continue

        lead_score, anzsic_score, tender_score = compute_lead_score(data["anzsic"], tenders, global_stats)

        ranked.append({
            "registered_business_name": data["name"],
            "abn": abn,
            "anzsic_code": data["anzsic"],
            "number_of_tenders": len(tenders),
            "anzsic_score": anzsic_score,
            "tender_score": tender_score,
            "lead_score": lead_score
        })

    ranked = sorted(ranked, key=lambda x: x["lead_score"], reverse=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, row in enumerate(ranked, 1):
            row["rank"] = i
            writer.writerow(row)

    print(f"{len(ranked)} ranked companies written to {OUTPUT_CSV}")


# MAIN

def main():
    print("🔍 Loading NPI companies...")
    npi_companies = load_npi_companies(NPI_CSV)
    print(f"Loaded {len(npi_companies)} companies.")

    start_date = datetime.strptime(START_DATE, "%Y-%m-%dT%H:%M:%SZ")
    end_date = datetime.strptime(END_DATE, "%Y-%m-%dT%H:%M:%SZ")

    # Fetch tenders in 1-day batches due to restrictions on large date ranges
    print("Fetching AusTender data in 1 Day batches...")
    tenders = fetch_tenders_day(start_date, end_date)
    print(f"Total tenders fetched: {len(tenders)}")

    print("Matching companies with tenders...")
    global_stats = {"max_value": 0, "min_value": float("inf")}

    for tender in tenders:
        match_company_to_tender(npi_companies, tender, global_stats)

    print("Computing scores and saving results...")
    save_prime_companies(npi_companies, global_stats)
    print("Done!")


if __name__ == "__main__":
    main()
