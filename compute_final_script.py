from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
import time
from math import log10
from rapidfuzz import process, fuzz
import re


def clean_name(s):
    if pd.isna(s):
        return ""
    s = str(s).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\b(p ty|pty|pty ltd|pty limited|ltd|limited|ltda|co|company|inc|plc|llc)\b", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Selenium Config
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
driver = webdriver.Chrome(options=chrome_options)


# Target Substances and Scores
TARGET_SUBSTANCES = [
    "Particulate Matter 10.0 um", "Particulate Matter 2.5 um",
    "Iron & compounds", "Manganese & compounds", "Zinc and compounds",
    "Chromium (III) compounds", "Chromium (VI) compounds",
    "Nickel & compounds", "Lead & compounds", "Copper & compounds",
    "Aluminium oxide", "Magnesium oxide fume", "Titanium dioxide",
    "Cobalt & compounds", "Beryllium & compounds", "Cadmium & compounds",
    "Antimony & compounds", "Arsenic & compounds", "Mercury & compounds",
    "Selenium & compounds", "Sulfur dioxide"
]

SUBSTANCE_SCORES = {
    "Particulate Matter 10.0 um": 6,
    "Particulate Matter 2.5 um": 6,
    "Iron & compounds": 3,
    "Manganese & compounds": 3,
    "Zinc and compounds": 3,
    "Chromium (III) compounds": 3,
    "Chromium (VI) compounds": 3,
    "Nickel & compounds": 3,
    "Lead & compounds": 3,
    "Copper & compounds": 3,
    "Aluminium oxide": 2,
    "Magnesium oxide fume": 2,
    "Titanium dioxide": 2,
    "Cobalt & compounds": 2,
    "Beryllium & compounds": 2,
    "Cadmium & compounds": 2,
    "Antimony & compounds": 2,
    "Arsenic & compounds": 2,
    "Mercury & compounds": 2,
    "Selenium & compounds": 2,
    "Sulfur dioxide": 2
}


# Load Data
facilities_df = pd.read_csv("facilities.csv")
if "latest_report_url" not in facilities_df.columns or "facility_name" not in facilities_df.columns:
    raise ValueError("facilities.csv must contain 'facility_name' and 'latest_report_url' columns")

tender_df = pd.read_csv("prime_companies_ranked.csv")
if "registered_business_name" not in tender_df.columns or "tender_score" not in tender_df.columns:
    raise ValueError("prime_companies_ranked.csv must contain 'registered_business_name' and 'tender_score' columns")

tender_df["registered_business_name"] = tender_df["registered_business_name"].astype(str)
tender_df["name_clean"] = tender_df["registered_business_name"].apply(clean_name)
tender_df["tender_score"] = pd.to_numeric(tender_df["tender_score"], errors="coerce").fillna(0)

tender_name_list = tender_df["name_clean"].tolist()
tender_map_exact = dict(zip(tender_df["name_clean"], tender_df["tender_score"]))

all_data = []


# Scrape Each Facility
for idx, row in facilities_df.iterrows():
    name = row["facility_name"]
    url = row["latest_report_url"]
    state = row["state"] if "state" in row else ""

    print(f"[{idx+1}/{len(facilities_df)}] Processing {name}")

    if state != "VIC":
        print("Skipping non-VIC facility.")
        continue

    try:
        driver.get(url)
        time.sleep(2)
    except Exception as e:
        print(f"Failed to load URL: {e}")
        continue

    try:
        emissions_tab = driver.find_element(By.ID, "facility-emission-result-tab")
        emissions_tab.click()
        time.sleep(2)
    except Exception:
        pass

    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", id="substanceWithEmission")
    if not table:
        print("Emissions table not found.")
        continue

    rows = table.find("tbody").find_all("tr")
    facility_has_target = False

    for tr in rows:
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue

        substance = cells[0].get_text(strip=True)
        total_emission_str = cells[6].get_text(strip=True).replace(",", "")

        try:
            total_emission = float(total_emission_str)
        except ValueError:
            continue

        if substance in TARGET_SUBSTANCES and total_emission > 0:
            facility_has_target = True
            base_score = SUBSTANCE_SCORES.get(substance, 1)
            emission_weight = 1 + (log10(total_emission + 1) / 10)
            weighted_score = base_score * emission_weight

            all_data.append({
                "facility_name": name,
                "Substance": substance,
                "Total (kg)": total_emission,
                "Weighted Score": round(weighted_score, 2)
            })

    if not facility_has_target:
        print("No target emissions found.")


# Compute Rankings
if not all_data:
    print("No target emissions found in any facility.")
    driver.quit()
    raise SystemExit

data_df = pd.DataFrame(all_data)
summary_df = (
    data_df.groupby("facility_name")
    .agg(Emission_Weighted_Score=("Weighted Score", "sum"))
    .reset_index()
)
summary_df["name_clean"] = summary_df["facility_name"].apply(clean_name)
summary_df["tender_score_exact"] = summary_df["name_clean"].map(tender_map_exact).fillna(0)


# Fuzzy Matching for Tender Scores
choices = tender_name_list
tender_lookup_df = tender_df.set_index("name_clean")

matched_name_list = []
match_score_list = []
tender_score_list = []

for n, exact_score in zip(summary_df["name_clean"], summary_df["tender_score_exact"]):
    if exact_score and exact_score > 0:
        matched_name_list.append(n)
        match_score_list.append(100.0)
        tender_score_list.append(exact_score)
        continue

    if not n:
        matched_name_list.append("")
        match_score_list.append(0.0)
        tender_score_list.append(0.0)
        continue

    match = process.extractOne(n, choices, scorer=fuzz.token_set_ratio)
    if match:
        matched_clean_name, score, _ = match
        score = round(score, 2)
        if score >= 65:
            matched_name_list.append(matched_clean_name)
            match_score_list.append(score)
            tender_score_list.append(float(tender_lookup_df.loc[matched_clean_name, "tender_score"]))
        else:
            matched_name_list.append("")
            match_score_list.append(score)
            tender_score_list.append(0.0)
    else:
        matched_name_list.append("")
        match_score_list.append(0.0)
        tender_score_list.append(0.0)

summary_df["matched_name"] = matched_name_list
summary_df["match_score"] = match_score_list
summary_df["tender_score"] = tender_score_list


# Normalize and Combine Scores
summary_df["Emission_Scaled"] = summary_df["Emission_Weighted_Score"] / summary_df["Emission_Weighted_Score"].max()
summary_df["Tender_Scaled"] = summary_df["tender_score"] / (summary_df["tender_score"].max() or 1)

summary_df["Final_Score"] = (
    (summary_df["Emission_Scaled"] * 0.7 + summary_df["Tender_Scaled"] * 0.3)
).round(2)


def relevance_label(score):
    if score >= 0.5:
        return "High"
    elif score >= 0.25:
        return "Medium"
    else:
        return "Low"


summary_df["Relevance"] = summary_df["Final_Score"].apply(relevance_label)
summary_df = summary_df.sort_values(by="Final_Score", ascending=False)


# Save Outputs (with clean float formatting)
summary_df.to_csv("egl_clean_air_facility_rankings.csv", index=False, float_format="%.2f")

ranked_facilities = pd.merge(
    summary_df[["facility_name", "Final_Score", "Relevance", "tender_score", "matched_name", "match_score"]],
    facilities_df,
    on="facility_name",
    how="left"
).sort_values(by="Final_Score", ascending=False)

ranked_facilities.to_csv("facilities_ranked.csv", index=False, float_format="%.2f")

summary_df[
    ["facility_name", "name_clean", "tender_score_exact", "matched_name", "match_score", "tender_score"]
].to_csv("tender_matches_debug.csv", index=False, float_format="%.2f")

print("\n Done. Outputs generated:")
print(" - egl_clean_air_facility_rankings.csv")
print(" - facilities_ranked.csv")
print(" - tender_matches_debug.csv\n")

driver.quit()
