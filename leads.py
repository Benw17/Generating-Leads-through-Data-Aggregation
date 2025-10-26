import requests
from bs4 import BeautifulSoup
import time
import re
from rapidfuzz import fuzz
import json

# CONFIG
GUID = "10d676dc-3abc-4d08-a0cf-854437727a40"
BASE_URL = "https://www.yellowpages.com.au"
PAGES = 3  # adjust to crawl more pages
DELAY = 2  # seconds between requests
ACTIVE = '0000000001' # ABR code for active businesses

headers = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cookie' : 'BVBRANDID=5282667b-82e8-4dbe-8d22-a13ae820bbe8; s_ecid=MCMID%7C64848381951761708300960074996811087032; AMCVS_8412403D53AC3D7E0A490D4C%40AdobeOrg=1; s_cc=true; yellow-guid=63299a90-42ee-4b45-9bf3-ab83c60a7fa4; __gsas=ID=ce7c74742d115e7c:T=1759967397:RT=1759967397:S=ALNI_MZHkBmjSDp_0MqvBpsOdUzhbeZ2mw; BVImplmain_site=11347; s_sq=%5B%5BB%5D%5D; cf_clearance=0Xw4mVkqff2kb5U2ubQUeNi2BakLW3nEsypsJEIDYGk-1760426932-1.2.1.1-DSDQqJMtGJbq2gZFz2xJh4hCR3JBP4VyJgyfVslLoQgbp205kTjlI3ccMp0rtTEB7.yyDlRUU4kvkt0tGkeho2N5JU8tM1JvB38qHegJoyoHFUPqrZiJoxGrs3jDawcg8zRKA8GU2UoxHBG0KZrl5h5435zHpKxTBr43C17F.YFDvzwhDSOTBjRRpYG6MJSZwF6QTQXEo101qlA6Fz73oMrmIUzGeIGG1hB88nU3uVw; AMCV_8412403D53AC3D7E0A490D4C%40AdobeOrg=179643557%7CMCIDTS%7C20376%7CMCMID%7C64848381951761708300960074996811087032%7CMCAID%7CNONE%7CMCOPTOUT-1760434162s%7CNONE%7CvVersion%7C5.5.0; __cf_bm=baPS_5NnvFLNl0fbIkv6Mjfk8EWlC6ocHuFX_KG6NYE-1760430466-1.0.1.1-4y4bTrwBuJ23TNVPwIC7O3JIkzMggmf9ZD.VNrhXumgBon1frQHbnxo2EcPzN.CQIgGKVsJSY_FJn8YoxDmNJGyaQahrPqHCBQq7snaRFBo'
}

#ABR VALIDATION
def extract_postcode(address):
    match = re.search(r"\b\d{4}\b", address or "")
    return match.group(0) if match else None

def extract_suburb(address):
    if not address:
        return None
    parts = address.split(',')
    if len(parts) >= 2:
        suburb_part = parts[-2].strip()
        return suburb_part.split()[0]
    return None

def check_abn_active(business_name, address=None):
    # Searches ABR API for business name and verifies active status.
    try:
        url = f"https://abr.business.gov.au/json/MatchingNames.aspx?name={business_name}&locationClue=All+States&guid={GUID}"
        response = requests.get(url)
        if response.text.startswith("callback("):
            json_text = response.text[len("callback("):-1]
            data = json.loads(json_text)

        if "Names" not in data or not data["Names"]:
            print(f"No ABN match for {business_name}")
            return False, None

        postcode = extract_postcode(address)
        best_match = None
        best_score = 0

        for entry in data["Names"]:
            name_match = fuzz.token_sort_ratio(entry["Name"].lower(), business_name.lower())
            if name_match > best_score:
                best_match = entry
                best_score = name_match

        if best_match:
            if best_match.get("AbnStatus", "").lower() == ACTIVE:
                # extra check: verify postcode if available
                if postcode and best_match.get("Postcode") and best_match["Postcode"] != postcode:
                    return False, None
                return True, best_match.get("Abn")
        return False, None
    except Exception as e:
        print(f"ABN check error for {business_name}: {e}")
        return False, None


# === SCRAPER ===
def scrape_businesses(query, max_pages=PAGES):
    """Scrapes Yellow Pages for a given query and filters by active ABN."""
    active_businesses = []
    seen_urls = set()
    seen_names = set()

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/search/listings?clue={query}&pageNumber={page}"
        print(f"\n🔎 Searching '{query}' — Page {page}")
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")

        listings = soup.select("div.MuiPaper-root.MuiCard-root")
        if not listings:
            print("No listings found.")
            break

        for card in listings:
            name_tag = card.select_one("a.business-name, a.MuiTypography-root.MuiLink-root")
            if not name_tag:
                continue

            name = name_tag.get_text(strip=True)
            link = BASE_URL + name_tag.get("href", "")

            if link in seen_urls:
                continue
            seen_urls.add(link)

            normalized_name = name.strip().lower().replace(".", "").replace(",", "")

            if normalized_name in seen_names:
                continue

            seen_names.add(normalized_name)

            # Visit detail page
            detail_res = requests.get(link, headers=headers)
            detail_soup = BeautifulSoup(detail_res.text, "html.parser")

            phone_tag = detail_soup.select_one("a.click-to-call")
            phone = phone_tag.get_text(strip=True).replace("Phone", "").replace("Call", "").strip() if phone_tag else None
            addr_tag = detail_soup.select_one(".listing-address")
            address = addr_tag.get_text(strip=True) if addr_tag else None
            web_tag = detail_soup.select_one(".contact-url")
            website = web_tag.get("href") if web_tag else None

            is_active, abn = check_abn_active(name, address)

            if is_active:
                print(f"✅ ACTIVE: {name}")
                active_businesses.append({
                    "Name": name,
                    "Phone": phone,
                    "Address": address,
                    "Website": website,
                    "ABN": abn,
                    "URL": link
                })
            else:
                print(f"❌ Skipped (inactive or no ABN): {name}")

            time.sleep(DELAY)

    return active_businesses


# === MAIN ===
keywords = [
    # 🪵 Woodworking / Timber Processing
    "timber mill",
    "sawmill",
    "wood processing plant",
    "timber flooring manufacturer",
    "furniture factory",
    "joinery workshop",
    "wood veneer manufacturer",
    "CNC woodworking shop",
    "timber products manufacturer",
    "timber joinery business",
    "wood machining",
    "wood panel manufacturer",
    "timber cladding producer",
    "timber furniture production",
    "timber fabrication plant",

    # 🪚 Cabinet Makers / Joinery Workshops
    "cabinet maker",
    "kitchen manufacturer",
    "joinery business",
    "custom furniture maker",
    "wardrobe manufacturer",
    "shopfitting company",
    "interior fitout contractor",
    "furniture design studio",
    "bespoke joinery",
    "carpentry workshop",
    "cabinet fabrication",
    "cabinet installation business",
    "kitchen joiner",
    "timber joinery workshop",
    "custom cabinetry factory",

    # ♻️ Recycling / Waste Management Facilities
    "recycling plant",
    "metal recycling facility",
    "plastic recycling plant",
    "scrap metal yard",
    "waste processing facility",
    "waste transfer station",
    "materials recovery facility",
    "e-waste recycling plant",
    "tyre recycling",
    "battery recycling",
    "waste sorting facility",
    "industrial waste services",
    "construction waste recycling",
    "green waste processing",
    "recycling services company"
]

results = []
for kw in keywords:
    results.extend(scrape_businesses(kw))

# === SAVE TO CSV ===
import csv
with open("leads.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["Name", "Phone", "Address", "Website", "ABN", "URL"])
    writer.writeheader()
    writer.writerows(results)

print(f"\n✅ Done! Saved {len(results)} active businesses to active_egl_leads.csv")
