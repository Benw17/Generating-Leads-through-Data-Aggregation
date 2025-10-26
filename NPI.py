import requests
import csv

# CONFIG
HIGH_RELEVANCE = 5
MEDIUM_RELEVANCE = 3
LOW_RELEVANCE = 1

ANZSIC_CODES = [
    # Mining & Extraction
    "0600", "0700", "0800", "0911", "0919", "0990",
    # Manufacturing
    "1111", "1131", "1210", "1311", "1411", "1412", "1413", "1491", "1492", "1493",
    "1499", "1510", "1521", "1611", "1700", "1800", "1811", "1821", "1831", "1841",
    "1911", "1920", "2010", "2021", "2029", "2031", "2034", "2110", "2121", "2131",
    "2139", "2210", "2221", "2299", "2311", "2411", "2462", "2499", "2511",
    # Utilities & Waste
    "2611", "2621", "2630", "2811", "2911", "2921", "2922", "2923",
    # Construction & Heavy Engineering
    "3011", "3101", "3109", "3231", "3239",
    # Agriculture & Forestry
    "0111", "0121", "0139", "0141", "0142", "0144", "0145", "0160", "0171",
    "0191", "0411", "0510",
    # Scientific & Environmental Services
    "6910", "6922", "6925"
]

BASE_URL = "https://services-ap1.arcgis.com/ypkPEy1AmwPKGNNv/arcgis/rest/services/National_Pollutant_Inventory/FeatureServer/0/query"

OUTPUT_CSV = "facilities.csv"

FIELDNAMES = [
    "registered_business_name", "facility_name", "state", "suburb",
    "street_address", "postcode", "primary_anzsic_class_code",
    "primary_anzsic_class_name", "main_activities", "abn", "acn",
    "facility_website", "latest_report_year", "latest_report_url"
]

REQUEST_BATCH_SIZE = 1000  # Number of facilities per request


def fetch_facilities(offset):
    # Fetch a batch of facilities with pagination.
    params = {
        "f": "json",
        "where": "1=1",  # Fetch all
        "outFields": ",".join(FIELDNAMES + ["objectid", "globalid", "first_report_year", "jurisdiction_facility_id"]),
        "outSR": "102100",
        "returnM": "true",
        "returnZ": "true",
        "spatialRel": "esriSpatialRelIntersects",
        "resultOffset": offset,
        "resultRecordCount": REQUEST_BATCH_SIZE
    }
    try:
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("features", [])
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return []


def save_facilities_to_csv(all_features):
    # Write facilities to CSV while skipping duplicates.
    seen_addresses = set()
    seen_companies = set()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        writer.writeheader()

        count_saved = 0
        for feature in all_features:
            attrs = feature.get("attributes", {})
            anzsic = attrs.get("primary_anzsic_class_code")

            if anzsic not in ANZSIC_CODES:
                continue

            try: 
                address_key = f"{attrs.get('street_address', '').strip()}_{attrs.get('postcode', '').strip()}"
                company_name = attrs.get("registered_business_name", "").strip()

            except Exception:
                continue
            if not address_key or not company_name:
                continue

            if address_key in seen_addresses or company_name in seen_companies:
                continue

            seen_addresses.add(address_key)
            seen_companies.add(company_name)

            writer.writerow({
                "registered_business_name": attrs.get("registered_business_name"),
                "facility_name": attrs.get("facility_name"),
                "state": attrs.get("state"),
                "suburb": attrs.get("suburb"),
                "street_address": attrs.get("street_address"),
                "postcode": attrs.get("postcode"),
                "primary_anzsic_class_code": attrs.get("primary_anzsic_class_code"),
                "primary_anzsic_class_name": attrs.get("primary_anzsic_class_name"),
                "main_activities": attrs.get("main_activities"),
                "abn": attrs.get("abn"),
                "acn": attrs.get("acn"),
                "facility_website": attrs.get("facility_website"),
                "latest_report_year": attrs.get("latest_report_year"),
                "latest_report_url": attrs.get("latest_report_url"),
            })
            count_saved += 1

    print(f"CSV written successfully: {OUTPUT_CSV}")
    print(f"Total unique facilities saved: {count_saved}")


def main():
    offset = 0
    all_features = []

    print("Fetching all facilities from NPI..")
    while True:
        batch = fetch_facilities(offset)
        if not batch:
            break
        all_features.extend(batch)
        print(f"Retrieved {len(batch)} facilities (offset {offset})")
        offset += REQUEST_BATCH_SIZE

    print(f"Total facilities retrieved: {len(all_features)}")
    save_facilities_to_csv(all_features)


if __name__ == "__main__":
    main()
