import argparse
import logging
import os
import re
import json
import sys
from datetime import datetime
from collections import Counter

from hospital_crawler import find_hospitals, find_procedure_pricing, setup_logging, crawl_hospital_website
from hospital_analysis import (
    calculate_search_metrics, 
    analyze_transparency_compliance,
    analyze_website_structure, 
    analyze_geographic_distribution,
    analyze_hospital_metadata,
    analyze_website_content
)

def setup_output_directories(city: str, state: str, cpt_code: str, output_dir: str = "results"):
    """Create output directory structure based on search parameters and return file paths."""
    folder_name = f"{city.replace(' ', '_')}_{state.upper()}_{cpt_code}"
    folder_path = os.path.join(output_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    
    return {
        "log_file": os.path.join(folder_path, "search.log"),
        "results_file": os.path.join(folder_path, "results.txt"),
        "folder_path": folder_path
    }

def save_results_to_file(results, output_file="price_results.txt"):
    """Save the pricing results to a formatted text file"""
    with open(output_file, "w") as f:
        f.write("=== HOSPITAL PROCEDURE PRICING RESULTS ===\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Add search metrics section
        if "metrics" in results:
            metrics = results["metrics"]
            f.write("=== SEARCH METRICS ===\n")
            f.write(f"Total hospitals searched: {metrics['total_hospitals']}\n")
            f.write(f"Hospitals with websites: {metrics['hospitals_with_websites']}\n")
            f.write(f"Hospitals with prices found: {metrics['hospitals_with_prices']}\n")
            f.write(f"Overall success rate: {metrics['overall_success_rate']}%\n")
            f.write(f"Website search success rate: {metrics['website_success_rate']}%\n")
            
            if "price_min" in metrics:
                f.write("\n=== PRICE STATISTICS ===\n")
                f.write(f"Lowest price: ${metrics['price_min']:.2f}\n")
                f.write(f"Highest price: ${metrics['price_max']:.2f}\n")
                f.write(f"Average price: ${metrics['price_avg']:.2f}\n")
                f.write(f"Median price: ${metrics['price_median']:.2f}\n")
                f.write(f"Price range: ${metrics['price_range']:.2f}\n")
                f.write(f"Price variance: ${metrics['price_variance']:.2f}\n")
            f.write("\n")
        
        if results["best_price"] is not None:
            f.write("=== BEST PRICE FOUND ===\n")
            f.write(f"Price: ${results['best_price']:.2f}\n")
            f.write(f"Hospital: {results['hospital_name']}\n")
            f.write(f"Address: {results['hospital_address']}\n")
            f.write(f"Source: {results['source_url']}\n\n")
            
            f.write("=== ALL PRICES FOUND ===\n")
            for idx, price_info in enumerate(results["all_prices"], 1):
                f.write(f"{idx}. ${price_info['price']:.2f} - {price_info['hospital_name']}\n")
                f.write(f"   Address: {price_info['hospital_address']}\n")
                f.write(f"   Source: {price_info['source_url']}\n\n")
        else:
            f.write("No pricing information was found for this procedure.\n")
            f.write("Try searching with a different CPT code or procedure name.\n")

def find_best_procedure_price(city, state, cpt_code, procedure_name=None, max_depth=3):
    """Finds the best (lowest) price for a medical procedure across hospitals in a given location."""
    logger = logging.getLogger(__name__)
    
    hospitals = find_hospitals(city, state)
    
    if not hospitals:
        logger.warning(f"No hospitals found in {city}, {state}")
        return {
            "best_price": None,
            "hospital_name": None,
            "hospital_address": None,
            "source_url": None,
            "context": None,
            "all_prices": [],
            "metrics": {
                "total_hospitals": 0,
                "hospitals_with_websites": 0,
                "hospitals_with_prices": 0,
                "overall_success_rate": 0,
                "website_success_rate": 0
            }
        }
    
    all_prices = []
    search_attempts = []
    
    logger.info(f"Searching for pricing of CPT {cpt_code} ({procedure_name or 'no name'}) in {city}, {state}")
    logger.info(f"Found {len(hospitals)} hospitals to search")
    
    for hospital in hospitals:
        search_result = {"hospital_name": hospital["name"], "success": False, "has_website": False}
        
        if hospital.get('website'):
            search_result["has_website"] = True
            logger.info(f"Searching {hospital['name']}...")
            
            try:
                pricing = find_procedure_pricing(hospital['website'], cpt_code, procedure_name, max_depth)
                
                if pricing["found"]:
                    price_info = {
                        "price": pricing["price"],
                        "hospital_name": hospital["name"],
                        "hospital_address": hospital["address"],
                        "source_url": pricing["source_url"],
                        "context": pricing["context"]
                    }
                    all_prices.append(price_info)
                    search_result["success"] = True
                    search_result["price"] = pricing["price"]
                    logger.info(f"✓ Found price: ${pricing['price']} at {hospital['name']}")
                else:
                    logger.info(f"× No pricing found at {hospital['name']}")
                    if pricing.get("pdf_links"):
                        logger.info(f"  Found potential PDF resources: {len(pricing['pdf_links'])}")
                        search_result["has_pdfs"] = True
            
            except Exception as e:
                logger.error(f"Error searching {hospital['name']}: {e}")
                search_result["error"] = str(e)
        else:
            logger.info(f"× Skipping {hospital['name']} - No website available")
        
        search_attempts.append(search_result)
    
    metrics = calculate_search_metrics(hospitals, all_prices)
    
    unsuccessful_hospitals = [
        {
            "name": attempt["hospital_name"], 
            "has_website": attempt["has_website"],
            "has_pdfs": attempt.get("has_pdfs", False),
            "error": attempt.get("error", None)
        } 
        for attempt in search_attempts if not attempt["success"]
    ]
    
    if all_prices:
        best_price_info = min(all_prices, key=lambda x: x["price"])
        
        return {
            "best_price": best_price_info["price"],
            "hospital_name": best_price_info["hospital_name"],
            "hospital_address": best_price_info["hospital_address"],
            "source_url": best_price_info["source_url"],
            "context": best_price_info["context"],
            "all_prices": all_prices,
            "metrics": metrics,
            "unsuccessful_hospitals": unsuccessful_hospitals
        }
    else:
        logger.warning("No prices found for any hospitals")
        return {
            "best_price": None,
            "hospital_name": None,
            "hospital_address": None,
            "source_url": None,
            "context": None,
            "all_prices": [],
            "metrics": metrics,
            "unsuccessful_hospitals": unsuccessful_hospitals
        }

def run_comprehensive_analysis():
    """Run multiple types of analyses across different regions"""
    cities_states = [
        ("Los Angeles", "CA"), 
        ("Chicago", "IL"),
        ("Boston", "MA")
    ]
    
    # 1. Analyze website structure
    structure_results = {}
    for city, state in cities_states:
        structure_results[f"{city}, {state}"] = analyze_website_structure(city, state, "99213")
    
    # 2. Analyze compliance
    compliance_results = analyze_transparency_compliance(cities_states)
    
    # 3. Analyze hospital distribution
    distribution_results = {}
    for city, state in cities_states:
        distribution_results[f"{city}, {state}"] = analyze_geographic_distribution(city, state)
    
    # 4. Analyze metadata
    metadata_results = analyze_hospital_metadata(cities_states)
    
    # 5. Analyze website content
    content_results = {}
    for city, state in cities_states:
        content_results[f"{city}, {state}"] = analyze_website_content(city, state)
    
    # Save all results
    with open("comprehensive_analysis.json", "w") as f:
        json.dump({
            "structure": structure_results,
            "compliance": compliance_results,
            "distribution": distribution_results,
            "metadata": metadata_results,
            "content": content_results
        }, f, indent=2)

def analyze_hospital_pricing_terms(cities_states=None):
    """
    Analyze hospital websites for pricing terms and navigation depth in a single crawl
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("pricing_term_analysis.log"),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    
    # Default cities to analyze if none provided
    if not cities_states:
        cities_states = [
            ("Los Angeles", "CA"), 
            ("Chicago", "IL"),
            ("Boston", "MA"),
            ("New York", "NY"), 
            ("Houston", "TX"),
            ("Phoenix", "AZ"), 
            ("Philadelphia", "PA"),
            ("San Antonio", "TX"), 
            ("San Diego", "CA"),
            ("Dallas", "TX"), 
            ("San Jose", "CA")
        ]
    
    # Known pricing terms to look for
    pricing_terms = [
        "price", "cost", "charge", "fee", "bill", 
        "payment", "estimate", "transparency",
        "chargemaster", "financial"
    ]
    
    # Track overall results
    results = {
        "regions": {},
        "term_frequency": Counter(),
        "new_terms": [],
        "navigation_depth": {},
        "overall_stats": {}
    }
    
    # Overall counters
    total_hospitals = 0
    hospitals_with_websites = 0
    hospitals_with_pricing = 0
    context_words = set()
    
    logger.info(f"Starting analysis for {len(cities_states)} regions")
    
    # Analyze each region
    for city, state in cities_states:
        region_name = f"{city}, {state}"
        logger.info(f"Analyzing hospitals in {region_name}")
        
        # Get hospitals in this region
        hospitals = find_hospitals(city, state)
        total_hospitals += len(hospitals)
        
        # Initialize region results
        region_data = {
            "total": len(hospitals),
            "with_website": 0,
            "with_pricing": 0,
            "terms": Counter(),
            "hospitals": []
        }
        
        depths = []
        
        # Process each hospital
        for hospital in hospitals:
            # Basic hospital info
            hospital_data = {
                "name": hospital["name"],
                "has_website": False,
                "pricing_depth": None,
                "terms_found": []
            }
            
            # Skip if no website
            if not hospital.get('website'):
                region_data["hospitals"].append(hospital_data)
                continue
            
            # Count hospitals with websites
            hospitals_with_websites += 1
            region_data["with_website"] += 1
            hospital_data["has_website"] = True
            
            try:
                # Crawl the website (single pass)
                logger.info(f"Crawling {hospital['name']}: {hospital['website']}")
                pages = crawl_hospital_website(hospital['website'], max_depth=3, max_pages=25)
                
                # Track pricing info
                found_pricing = False
                min_depth = float('inf')
                found_terms = Counter()
                
                # Check each page
                for page in pages:
                    text = page['text'].lower()
                    url = page['url'].lower()
                    depth = page['depth']
                    
                    # Look for pricing terms
                    for term in pricing_terms:
                        if term in text or term in url:
                            # Count this term
                            found_terms[term] += 1
                            
                            # Mark as pricing page if first occurrence
                            if not found_pricing:
                                found_pricing = True
                                min_depth = depth
                                hospitals_with_pricing += 1
                                region_data["with_pricing"] += 1
                            else:
                                min_depth = min(min_depth, depth)
                            
                            # Find context around term for new term discovery
                            for match in re.finditer(r'\b' + re.escape(term) + r'\b', text):
                                start = max(0, match.start() - 30)
                                end = min(len(text), match.end() + 30)
                                context = text[start:end]
                                
                                # Extract potential new terms
                                new_words = [w for w in re.findall(r'\b[a-z]{4,15}\b', context) 
                                           if w not in pricing_terms and len(w) > 3]
                                context_words.update(new_words)
                
                # Record hospital results
                if found_pricing:
                    hospital_data["pricing_depth"] = min_depth
                    depths.append(min_depth)
                    hospital_data["terms_found"] = list(found_terms.keys())
                    
                    # Update term counts
                    region_data["terms"].update(found_terms)
                    results["term_frequency"].update(found_terms)
            
            except Exception as e:
                logger.error(f"Error analyzing {hospital['name']}: {e}")
            
            # Add this hospital's data
            region_data["hospitals"].append(hospital_data)
        
        # Calculate depth statistics for this region
        if depths:
            results["navigation_depth"][region_name] = {
                "avg": sum(depths) / len(depths),
                "min": min(depths),
                "max": max(depths),
                "distribution": {str(i): depths.count(i) for i in range(5)}
            }
            results["navigation_depth"][region_name]["distribution"]["5+"] = sum(1 for d in depths if d >= 5)
        
        # Save region results
        results["regions"][region_name] = region_data
    
    # Find potential new pricing terms
    word_counts = Counter(context_words)
    results["new_terms"] = [word for word, count in word_counts.most_common(30) if count > 2]
    
    # Calculate overall statistics
    results["overall_stats"] = {
        "total_hospitals": total_hospitals,
        "hospitals_with_websites": hospitals_with_websites,
        "hospitals_with_pricing": hospitals_with_pricing,
        "pricing_rate": round((hospitals_with_pricing / total_hospitals * 100), 1) if total_hospitals else 0,
        "top_terms": results["term_frequency"].most_common(10)
    }
    
    # Save results to file
    with open("pricing_term_analysis.json", "w") as f:
        json.dump(results, f, indent=2, default=lambda obj: dict(obj) if isinstance(obj, Counter) else obj)
    
    logger.info(f"Analysis complete. Found pricing on {hospitals_with_pricing}/{total_hospitals} hospitals")
    return results

def main():
    parser = argparse.ArgumentParser(
        description="Analyze hospital websites for pricing terms and navigation depth."
    )
    parser.add_argument("--cities", nargs='+', help="Cities to analyze (format: 'City,ST')")
    args = parser.parse_args()
    
    # Parse custom cities if provided
    cities_states = None
    if args.cities:
        cities_states = []
        for city_state in args.cities:
            if ',' in city_state:
                city, state = city_state.split(',', 1)
                cities_states.append((city.strip(), state.strip()))
    
    # Run analysis
    results = analyze_hospital_pricing_terms(cities_states)
    
    # Display summary
    print("\n=== HOSPITAL PRICING ANALYSIS ===")
    print(f"Total hospitals: {results['overall_stats']['total_hospitals']}")
    print(f"Hospitals with pricing: {results['overall_stats']['hospitals_with_pricing']}")
    print(f"Pricing information rate: {results['overall_stats']['pricing_rate']}%")
    
    print("\nTop pricing terms:")
    for term, count in results["overall_stats"]["top_terms"]:
        print(f"  - {term}: {count}")
    
    print("\nPotential new pricing terms:")
    for term in results["new_terms"][:10]:
        print(f"  - {term}")
    
    print("\nNavigation depth by region:")
    for region, depth in results["navigation_depth"].items():
        print(f"  {region}: {depth['avg']:.1f} clicks (range: {depth['min']}-{depth['max']})")
    
    print("\nDetailed results saved to pricing_term_analysis.json")

if __name__ == "__main__":
    main()