# Healthcare-Costs-Web-Crawler
Web crawler to search for pricing information for various hospitals across regions to identify the practicality of price transparency

## Project Focus
We built a crawler that assesses the ease of accessing price transparency information across hospital websites in major U.S. cities. Rather than focusing solely on whether pricing data exists, we investigated how deeply it is buried, what terminology hospitals use to describe it, and which cities and hospitals are more transparent than others.

## Running the System

### Requirements
Python 3.8+
Install required packages:
pip install -r requirements.txt

Execute the full crawl:
python hospital_finder.py

This will run the main analysis for the 10 pre-determined cities in the code.

This will generate:
pricing_term_analysis.json — aggregated crawl results
pricing_term_analysis.log — full crawl log

Additionally, cities to crawl for can be determined with the command-line input
python hospital_finder.py --cities “City, State Abbv.” 
This can be run for any number of cities at a given time and will give the same outputs as mentioned above.

## What the Project Does and Why It Works
At its core, this project implements a robust and principled breadth-first search crawler to assess the accessibility of healthcare pricing information across hospital websites. While many systems focus on extracting structured pricing data, we focused instead on a more foundational question: how hard is it to even find where pricing information lives?
We start with a curated list of hospitals from ten major U.S. cities, each mapped to its website. For each hospital, our system initiates a controlled crawl:
Depth-limited to 3 levels to simulate a reasonable user journey (patients don’t click through 10 pages—if pricing isn’t nearby, it’s effectively hidden).
Capped at 25 pages per hospital to ensure fairness across different site sizes and avoid overloading any single domain.
Guided by healthcare-specific search terms, handpicked from real CMS regulations, hospital pricing portals, and published billing statements (e.g., “transparency,” “fee,” “cost estimator,” “chargemaster”).
The crawler executes a goal-directed breadth-first search, meaning it prioritizes breadth across major page types but filters links using keyword relevance to focus on billing- or cost-related content. Each page is evaluated for:
Presence of Pricing Language: Pages are scanned for a curated set of pricing-related keywords derived from CMS transparency guidelines and industry-standard chargemasters—terms like “price,” “fee,” “transparency,” and “cost estimator.”
Navigational Burden: The crawler records the number of clicks from the homepage required to find any pricing-related content. This metric directly mirrors the user effort needed to find cost information in a real-world setting.


The goal is not to extract exact prices, but to answer: Is there any signal on this hospital’s website that points a patient toward price transparency? This is semantic accessibility — a prerequisite to all downstream uses of pricing data. 
All data is written to a structured JSON format, recording term frequency, click depth, and hospital-level metadata. This allows us to generate aggregate views at the city level, trace patterns in hospital language use, and statistically compare institutional accessibility. This system doesn’t just collect surface statistics — it mirrors patient behavior. The technical decisions we made about crawl depth, link filtering, and term detection are not arbitrary: they are grounded in how users behave and how hospitals publish information. And by focusing on what’s findable rather than what’s buried in PDFs, we target a real-world gap in most transparency efforts — discoverability.

