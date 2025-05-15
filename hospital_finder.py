import argparse
import logging
import os
from datetime import datetime
import json

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

def run_pricing_term_analysis():
    """
    Analyze hospital websites to discover pricing terms and navigation depth in a single crawl
    """
    import logging
    import json
    import re
    from collections import Counter
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("pricing_term_analysis.log"),
            logging.StreamHandler()  # Also output to console
        ]
    )
    logger = logging.getLogger(__name__)
    
    # Cities to analyze
    cities_states = [
        ("Los Angeles", "CA"), 
        ("Chicago", "IL"),
        ("Boston", "MA")
    ]
    
    # Known pricing terms to start with
    known_pricing_terms = [
        "price", "pricing", "cost", "charge", "fee", "rate", 
        "estimate", "financial", "bill", "payment", "transparency",
        "chargemaster", "standard charges"
    ]
    
    # Initialize results
    results = {
        "by_region": {},
        "term_frequency": Counter(),
        "new_terms_discovered": [],
        "navigation_depth": {},
        "overall_stats": {}
    }
    
    # Words that often appear near pricing terms
    context_words = set()
    total_hospitals = 0
    hospitals_with_websites = 0
    hospitals_with_pricing_pages = 0
    
    logger.info("Starting pricing term analysis across hospital websites")
    
    for city, state in cities_states:
        region_key = f"{city}, {state}"
        logger.info(f"Analyzing hospitals in {region_key}")
        
        # Find hospitals in this region
        hospitals = find_hospitals(city, state)
        total_hospitals += len(hospitals)
        
        region_results = {
            "total_hospitals": len(hospitals),
            "hospitals_with_websites": 0,
            "hospitals_with_pricing": 0,
            "avg_navigation_depth": None,
            "term_frequency": Counter(),
            "hospital_details": []
        }
        
        navigation_depths = []
        
        # Process each hospital
        for hospital in hospitals:
            hospital_detail = {
                "name": hospital["name"],
                "has_website": False,
                "pricing_page_depth": None,
                "pricing_terms_found": [],
                "potential_new_terms": []
            }
            
            if not hospital.get('website'):
                region_results["hospital_details"].append(hospital_detail)
                continue
                
            hospitals_with_websites += 1
            region_results["hospitals_with_websites"] += 1
            hospital_detail["has_website"] = True
            
            logger.info(f"Crawling website for {hospital['name']}: {hospital['website']}")
            
            try:
                # Single crawl of the website
                pages = crawl_hospital_website(hospital['website'], max_depth=4, max_pages=30)
                
                # Track pricing terms and their context
                found_pricing_page = False
                min_pricing_depth = float('inf')
                term_counts = Counter()
                
                # Analyze each page
                for page in pages:
                    text = page['text'].lower()
                    url = page['url'].lower()
                    depth = page['depth']
                    
                    # Check for known pricing terms
                    for term in known_pricing_terms:
                        if term in text or term in url:
                            # Found a pricing term
                            term_counts[term] += 1
                            
                            # If this is our first pricing term on this site, mark as pricing page
                            if not found_pricing_page:
                                found_pricing_page = True
                                min_pricing_depth = depth
                                hospitals_with_pricing_pages += 1
                                region_results["hospitals_with_pricing"] += 1
                            else:
                                min_pricing_depth = min(min_pricing_depth, depth)
                            
                            # Find words surrounding the pricing terms for context
                            for match in re.finditer(r'\b' + re.escape(term) + r'\b', text):
                                start = max(0, match.start() - 30)
                                end = min(len(text), match.end() + 30)
                                context = text[start:end]
                                
                                # Find potential new pricing terms in the context
                                context_words_list = [w for w in re.findall(r'\b[a-z]{4,15}\b', context) 
                                                    if w not in known_pricing_terms and len(w) > 3]
                                context_words.update(context_words_list)
                                
                                # Add potential new terms to this hospital's results
                                hospital_detail["potential_new_terms"].extend(context_words_list)
                
                # Record the findings for this hospital
                if found_pricing_page:
                    hospital_detail["pricing_page_depth"] = min_pricing_depth
                    navigation_depths.append(min_pricing_depth)
                    region_results["term_frequency"].update(term_counts)
                    results["term_frequency"].update(term_counts)
                    
                    # Record found terms
                    hospital_detail["pricing_terms_found"] = [term for term, count in term_counts.items() if count > 0]
            
            except Exception as e:
                logger.error(f"Error analyzing {hospital['name']}: {e}")
            
            # Add this hospital's details to the region results
            region_results["hospital_details"].append(hospital_detail)
        
        # Calculate average navigation depth for this region
        if navigation_depths:
            region_results["avg_navigation_depth"] = sum(navigation_depths) / len(navigation_depths)
            results["navigation_depth"][region_key] = {
                "average": region_results["avg_navigation_depth"],
                "min": min(navigation_depths),
                "max": max(navigation_depths),
                "distribution": {
                    "0": sum(1 for d in navigation_depths if d == 0),
                    "1": sum(1 for d in navigation_depths if d == 1),
                    "2": sum(1 for d in navigation_depths if d == 2),
                    "3": sum(1 for d in navigation_depths if d == 3),
                    "4+": sum(1 for d in navigation_depths if d >= 4)
                }
            }
        
        # Save this region's results
        results["by_region"][region_key] = region_results
    
    # Discover potential new pricing terms
    # First, count all context words
    context_word_counts = Counter(context_words)
    
    # Filter to find words that appear frequently near pricing terms but aren't in our known list
    potential_new_terms = [word for word, count in context_word_counts.most_common(50) 
                          if count > 3 and word not in known_pricing_terms]
    
    results["new_terms_discovered"] = potential_new_terms
    
    # Calculate overall statistics
    results["overall_stats"] = {
        "total_hospitals": total_hospitals,
        "hospitals_with_websites": hospitals_with_websites,
        "hospitals_with_pricing_pages": hospitals_with_pricing_pages,
        "pricing_information_rate": (hospitals_with_pricing_pages / total_hospitals * 100) if total_hospitals else 0,
        "most_common_terms": results["term_frequency"].most_common(10),
    }
    
    # Save the results
    with open("pricing_term_analysis.json", "w") as f:
        # Counter objects need to be converted to dict for JSON serialization
        serializable_results = json.loads(json.dumps(results, default=lambda obj: obj if not isinstance(obj, Counter) else dict(obj)))
        json.dump(serializable_results, f, indent=2)
    
    logger.info(f"Analysis complete. Found pricing information on {hospitals_with_pricing_pages} out of {total_hospitals} hospitals.")
    logger.info(f"Most common pricing terms: {results['term_frequency'].most_common(5)}")
    logger.info(f"Potential new pricing terms discovered: {', '.join(potential_new_terms[:10])}")
    
    return results

def main():
    import sys
    
    # Check if analysis flag is present before parsing arguments
    if '--analysis' in sys.argv:
        # Create a simplified parser just for the analysis command
        parser = argparse.ArgumentParser(
            description="Run pricing term analysis across hospital websites."
        )
        parser.add_argument("--analysis", action="store_true", help="Run pricing term analysis")
        args = parser.parse_args()
        run_pricing_term_analysis()
        return
    
    # Regular parser for the search command with required arguments
    parser = argparse.ArgumentParser(
        description="Find the best price for a medical procedure across hospitals in a specified location."
    )
    parser.add_argument("city", help="City to search in")
    parser.add_argument("state", help="State to search in (full name or abbreviation)")
    parser.add_argument("cpt_code", help="CPT code for the medical procedure")
    parser.add_argument("--procedure-name", help="Name of the procedure (optional, improves search accuracy)")
    parser.add_argument("--output-dir", default="results", help="Base output directory")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum crawl depth")
    parser.add_argument("--analysis", action="store_true", help="Run comprehensive analysis instead of price search")
    
    args = parser.parse_args()
    
    # Setup output directories and file paths
    output_paths = setup_output_directories(args.city, args.state, args.cpt_code, args.output_dir)
    
    # Setup logging with the parameter-specific log file
    logger = setup_logging(output_paths["log_file"])
    
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Starting search at {timestamp}")
        logger.info(f"Parameters: City={args.city}, State={args.state}, CPT Code={args.cpt_code}, "
                   f"Procedure Name={args.procedure_name or 'not specified'}")
        
        # Find the best price
        best_price_info = find_best_procedure_price(
            args.city, 
            args.state, 
            args.cpt_code, 
            args.procedure_name,
            max_depth=args.max_depth
        )
        
        # Save search metadata to a summary file
        with open(os.path.join(output_paths["folder_path"], "search_info.txt"), "w") as f:
            f.write(f"Search performed: {timestamp}\n")
            f.write(f"City: {args.city}\n")
            f.write(f"State: {args.state}\n")
            f.write(f"CPT Code: {args.cpt_code}\n")
            f.write(f"Procedure Name: {args.procedure_name or 'Not specified'}\n")
            f.write(f"Crawl Depth: {args.max_depth}\n")
            
            # Add metrics to the search info file
            if "metrics" in best_price_info:
                metrics = best_price_info["metrics"]
                f.write("\nSearch Metrics:\n")
                f.write(f"  Total hospitals: {metrics['total_hospitals']}\n")
                f.write(f"  Success rate: {metrics['overall_success_rate']}%\n")
                
                if "price_min" in metrics and "price_max" in metrics:
                    f.write(f"  Price range: ${metrics['price_min']:.2f} - ${metrics['price_max']:.2f}\n")
        
        # Save results to file
        save_results_to_file(best_price_info, output_paths["results_file"])
        
        # Save detailed report about unsuccessful hospitals
        with open(os.path.join(output_paths["folder_path"], "unsuccessful_hospitals.txt"), "w") as f:
            f.write("=== HOSPITALS WHERE PRICE SEARCH FAILED ===\n\n")
            if "unsuccessful_hospitals" in best_price_info and best_price_info["unsuccessful_hospitals"]:
                for i, hospital in enumerate(best_price_info["unsuccessful_hospitals"], 1):
                    f.write(f"{i}. {hospital['name']}\n")
                    f.write(f"   Has website: {'Yes' if hospital['has_website'] else 'No'}\n")
                    if hospital['has_website']:
                        f.write(f"   Has PDF resources: {'Yes' if hospital['has_pdfs'] else 'No'}\n")
                    if hospital.get('error'):
                        f.write(f"   Error: {hospital['error']}\n")
                    f.write("\n")
            else:
                f.write("No unsuccessful searches - all hospitals provided pricing information.\n")
        
        if best_price_info["best_price"] is not None:
            logger.info(f"Best price found: ${best_price_info['best_price']:.2f} at {best_price_info['hospital_name']}")
            logger.info(f"Success rate: {best_price_info['metrics']['overall_success_rate']}%")
            logger.info(f"Results saved to {output_paths['results_file']}")
        else:
            logger.info("No pricing information found for this procedure.")
            logger.info(f"Overall success rate: 0%")
            logger.info(f"Empty results saved to {output_paths['results_file']}")
            
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()