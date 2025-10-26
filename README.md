# Clean Air Facility Ranking Project

This project started as an experiment to help a friend find potential clients for his environmental company — they work with heavy industries to clean up air emissions and help businesses comply with environmental regulations.

At first, I had no specific dataset or model in mind. The idea was simple: **find companies producing a lot of air emissions, rank them by relevance, and see who might need his services most.**

Over time, this evolved into a fully automated data pipeline that scrapes emissions data, matches it to tender activity, and generates ranked leads based on environmental and commercial signals.

---

## The Idea

My friend’s company focuses on improving air quality and reducing industrial emissions.  
The challenge was figuring out **which businesses are most relevant** — not just any company, but ones that are:
- actively operating,
- producing measurable air pollutants, and
- financially or operationally active (e.g. through government tenders).

So my goal was to create a **data-driven ranking system** to identify and prioritise companies that likely have both high emissions and capacity to engage external services.

---

## The Process

### Step 1 — Finding businesses
Initially, I tried scraping **Yellow Pages** using keywords that matched heavy industry sectors.  
It worked in theory but failed in practice — many listings were outdated or inactive.

To fix that, I connected the scraper to the **ABN Lookup API** to filter only **active businesses**, based on their Australian Business Number.  
That early experiment became my first script, **`leads.py`**.

It gave me a working list of live businesses, but it wasn’t targeted enough. I needed real emission data.

---

### Step 2 — Real environmental data
The next step was to find a reliable dataset for pollution levels.  
Australia’s **National Pollutant Inventory (NPI)** turned out to be perfect, it tracks pollutants reported by industrial facilities each year.

So I built a scraper using **Selenium** and **BeautifulSoup** that visits each facility’s NPI page, opens their latest emissions report, and extracts emission quantities for a set of **target substances** (like particulate matter, lead, nickel, and sulfur dioxide).

Each pollutant was given a **relevance score** based on how serious or aligned it is with my friend’s work, for example, particulate matter got a higher weight than magnesium oxide.

I then applied a **logarithmic weighting** based on total emission amount to scale large emitters without letting them completely dominate the rankings.


### Step 3 — Commercial signal (tenders)
After the environmental data came the commercial layer.  
I pulled data from **AusTenders** to see which companies were currently winning or applying for government contracts, a good sign of financial health and ongoing operations.

Unfortunately, a few days after setting that up, AusTenders suddenly introduced **mandatory API tokens** (bad timing).  
So I exported the cleaned and normalized data I had into **`prime_companies_ranked.csv`** and used that as a static input going forward.

This CSV includes each company’s name and a normalized “tender score” derived from the number, size, and recency of their tenders.


### Step 4 — Merging it all
In **`compute_final_script.py`**, I brought both datasets together.

For each facility:
1. Scrape its emission data.
2. Sum up all relevant pollutant scores.
3. Clean the facility name and try to match it against the tender dataset using:
   - exact string matches, or  
   - fuzzy matching via **RapidFuzz** (to handle things like “EnergyAustralia Yallourn” vs “EnergyAustralia Yallourn Pty Ltd”).
4. Combine the two results into one **Final Score**, weighting:
   - **Emissions (70%)**
   - **Tender activity (30%)**

This produced a ranked CSV of facilities most relevant to the company’s services.


## The Output

The script outputs several files:
- **`clean_air_facility_rankings.csv`** the main ranking, showing each facility’s emission score, tender score, final score, and relevance label.
- **`facilities_ranked.csv`** the rankings merged with original facility data.

Each facility gets a **Final Score (0–100)** and a **Relevance** label (`High`, `Medium`, or `Low`).  
In practice, the “High” group tends to be large industrial plants, waste facilities, and power stations, exactly the kinds of leads my friend wanted.


## Challenges & Lessons Learned

- **APIs change fast.** AusTenders revoked open access halfway through the project, so I had to pivot quickly and work with a unfinished dataset.
- **Company names are very messy.** I spent a lot of time building regex-based cleaning and fuzzy matching to align “XYZ Steel Pty Ltd” with “XYZ Steel.”
- **Normalization matters.** Emission scores and tender scores exist on totally different scales, so normalizing both before combining was key.
- **Data != truth.** Just because a company has high emissions doesn’t mean they’re a good prospect, it’s merely a data signal. This project is about narrowing the search, not making assumptions.


## Limitations

- Some companies have no tenders, so they may be unfairly ranked even if financially stable.
- Facilities without up-to-date NPI data can skew their results.
- Only **Victorian (VIC)** facilities are processed by default, but this can be changed in the code.
- Name-matching isn’t perfect, manual mapping would still help in some cases.


## Reflection

What started as a simple lead generator became a small data engineering and analytics project:
- I learned how to combine **scraping**, **data cleaning**, **fuzzy logic**, and **weight-based scoring** into one workflow.
- It gave me a much deeper understanding of how **data pipelines** can automate research and ranking tasks.
- Most importantly, it actually produced **real, meaningful leads**, companies with both emissions problems and active operations.

If I continue this, I’d like to:
- Re-write the entire script removing **hard-coded files** and removing any **magic numbers**. 
- Add a **simple dashboard** to visualize the top-ranked companies,
- Bring back **AusTenders integration** via API tokens(If they allow access once more),
- And allow **custom weighting** via a config file.


## Final Thought

This project wasn’t meant to be a public tool, it’s more of a **personal proof of concept** that shows how data can be used creatively to solve real-world problems.

It combines environmental data, commercial data, and automation to turn open data into insight.

Even though it started as a way to help a friend, it ended up being a fun, complex little example of applied data science.
