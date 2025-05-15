import re
from urllib.parse import urlparse
from typing import List, Dict, Any

from hospital_crawler import (
    find_hospitals, 
    crawl_hospital_website, 
    setup_logging,
    _get_city_coordinates, 
    calculate_distance
)

def calculate_search_metrics(hospitals: List[Dict[str, Any]], all_prices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate success metrics for the hospital price search."""
    # Count hospitals with websites
    hospitals_with_websites = sum(1 for hospital in hospitals if hospital.get('website'))
    
    # Count successful price discoveries
    successful_hospitals = len(all_prices)
    
    # Calculate success rates
    metrics = {
        "total_hospitals": len(hospitals),
        "hospitals_with_websites": hospitals_with_websites,
        "hospitals_with_prices": successful_hospitals,
        "overall_success_rate": round(successful_hospitals / len(hospitals) * 100, 1) if hospitals else 0,
        "website_success_rate": round(successful_hospitals / hospitals_with_websites * 100, 1) if hospitals_with_websites else 0,
        "price_ranges": {}
    }
    
    # Calculate price statistics if any prices were found
    if all_prices:
        prices = [p["price"] for p in all_prices]
        metrics["price_min"] = min(prices)
        metrics["price_max"] = max(prices)
        metrics["price_avg"] = sum(prices) / len(prices)
        metrics["price_median"] = sorted(prices)[len(prices) // 2]
        metrics["price_range"] = metrics["price_max"] - metrics["price_min"]
        metrics["price_variance"] = round(sum((p - metrics["price_avg"])**2 for p in prices) / len(prices), 2)
    
    return metrics

def analyze_website_structure(city, state, cpt_code, procedure_name=None):
    """Analyze hospital website structure for pricing information accessibility."""
    output_paths = {
        "log_file": f"analysis_{city}_{state}_website_structure.log"
    }
    logger = setup_logging(output_paths["log_file"])
    
    hospitals = find_hospitals(city, state)
    results = {
        "total_hospitals": len(hospitals),
        "has_website": 0,
        "has_pricing_page": 0,
        "has_pdfs": 0,
        "click_depth": [],
        "keywords_found": {}
    }
    
    pricing_keywords = ["price", "transparency", "chargemaster", "cost", "billing"]
    
    for hospital in hospitals:
        if not hospital.get('website'):
            continue
            
        results["has_website"] += 1
        
        try:
            # Crawl website to limited depth
            pages = crawl_hospital_website(hospital['website'], max_depth=3, max_pages=20)
            
            # Check for pricing pages
            found_pricing_page = False
            pdf_links = []
            min_depth = float('inf')
            keywords_found = set()
            
            for page in pages:
                text = page['text'].lower()
                for keyword in pricing_keywords:
                    if keyword in text:
                        keywords_found.add(keyword)
                        min_depth = min(min_depth, page['depth'])
                        found_pricing_page = True
                
                # Check for PDFs
                if "pdf" in page['url'].lower() and any(k in text for k in pricing_keywords):
                    pdf_links.append(page['url'])
            
            if found_pricing_page:
                results["has_pricing_page"] += 1
                results["click_depth"].append(min_depth)
                
            if pdf_links:
                results["has_pdfs"] += 1
                
            # Track keyword frequency
            for keyword in keywords_found:
                results["keywords_found"][keyword] = results["keywords_found"].get(keyword, 0) + 1
                
        except Exception as e:
            logger.error(f"Error analyzing {hospital['name']}: {e}")
    
    # Calculate averages
    if results["click_depth"]:
        results["avg_click_depth"] = sum(results["click_depth"]) / len(results["click_depth"])
    else:
        results["avg_click_depth"] = None
        
    return results

def analyze_transparency_compliance(cities_states):
    """Compare hospital price transparency across different regions."""
    compliance_data = {}
    
    for city, state in cities_states:
        hospitals = find_hospitals(city, state)
        if not hospitals:
            continue
            
        region_data = {
            "total_hospitals": len(hospitals),
            "has_website": 0,
            "has_pricing_page": 0,
            "has_machine_readable_file": 0,
            "has_price_estimator": 0,
            "compliance_score": 0
        }
        
        for hospital in hospitals:
            if not hospital.get('website'):
                continue
                
            region_data["has_website"] += 1
            
            # Check website for compliance with price transparency regulation
            compliance_score = 0
            pages = crawl_hospital_website(hospital['website'], max_depth=2)
            
            # Look for machine-readable files (JSON, CSV, XML)
            machine_readable = any("machine" in p['text'].lower() and "readable" in p['text'].lower() 
                                or any(ext in p['url'] for ext in ['.json', '.csv', '.xml']) for p in pages)
            
            # Look for consumer-friendly price estimator
            estimator = any("estimator" in p['text'].lower() or "calculator" in p['text'].lower() for p in pages)
            
            if machine_readable:
                compliance_score += 1
                region_data["has_machine_readable_file"] += 1
                
            if estimator:
                compliance_score += 1
                region_data["has_price_estimator"] += 1
                
            region_data["compliance_score"] += compliance_score
            
        compliance_data[f"{city}, {state}"] = region_data
    
    return compliance_data

def analyze_geographic_distribution(city, state, radius_miles=20):
    """Analyze geographic distribution of hospitals in an area."""
    hospitals = find_hospitals(city, state)
    
    # Group by distance from city center
    distance_groups = {
        "0-5 miles": [],
        "5-10 miles": [],
        "10-20 miles": [],
        "20+ miles": []
    }
    
    # Calculate distance from city center for each hospital
    city_coords = _get_city_coordinates(city, state)
    if not city_coords:
        return None
        
    for hospital in hospitals:
        if 'latitude' in hospital and 'longitude' in hospital:
            # Calculate distance in miles
            distance = calculate_distance(
                city_coords['lat'], city_coords['lng'],
                hospital['latitude'], hospital['longitude']
            )
            
            # Assign to distance group
            if distance <= 5:
                distance_groups["0-5 miles"].append(hospital)
            elif distance <= 10:
                distance_groups["5-10 miles"].append(hospital)
            elif distance <= 20:
                distance_groups["10-20 miles"].append(hospital)
            else:
                distance_groups["20+ miles"].append(hospital)
    
    return distance_groups

def analyze_hospital_metadata(cities_states):
    """Analyze metadata about hospitals across regions."""
    metadata = {}
    
    for city, state in cities_states:
        hospitals = find_hospitals(city, state)
        
        # Extract metadata
        websites_count = sum(1 for h in hospitals if h.get('website'))
        phone_count = sum(1 for h in hospitals if h.get('phone'))
        
        # Check website top-level domains and patterns
        domains = {}
        for hospital in hospitals:
            if hospital.get('website'):
                domain = urlparse(hospital['website']).netloc
                tld = domain.split('.')[-1] if '.' in domain else 'unknown'
                domains[tld] = domains.get(tld, 0) + 1
        
        metadata[f"{city}, {state}"] = {
            "total_hospitals": len(hospitals),
            "with_website_pct": (websites_count / len(hospitals) * 100) if hospitals else 0,
            "with_phone_pct": (phone_count / len(hospitals) * 100) if hospitals else 0,
            "domain_distribution": domains
        }
    
    return metadata

def analyze_website_content(city, state, keywords=None):
    """Analyze hospital website content for specific keywords and readability."""
    if keywords is None:
        keywords = [
            "price", "cost", "billing", "insurance", "financial", "pay",
            "estimate", "calculator", "transparency", "charges"
        ]
    
    hospitals = find_hospitals(city, state)
    results = []
    
    for hospital in hospitals:
        if not hospital.get('website'):
            continue
            
        pages = crawl_hospital_website(hospital['website'], max_depth=2, max_pages=15)
        
        # Analyze keyword frequency
        keyword_counts = {k: 0 for k in keywords}
        total_text_length = 0
        readability_scores = []
        
        for page in pages:
            text = page['text'].lower()
            total_text_length += len(text)
            
            # Count keywords
            for keyword in keywords:
                keyword_counts[keyword] += text.count(keyword)
                
            # Calculate basic readability (ratio of words to sentences)
            sentences = len(re.split(r'[.!?]', text))
            words = len(text.split())
            if sentences > 0:
                readability = words / sentences
                readability_scores.append(readability)
        
        # Calculate keyword density per 1000 words
        keyword_density = {}
        words_per_1000 = total_text_length / 1000
        for keyword, count in keyword_counts.items():
            keyword_density[keyword] = count / words_per_1000 if words_per_1000 > 0 else 0
            
        avg_readability = sum(readability_scores) / len(readability_scores) if readability_scores else 0
        
        results.append({
            "hospital_name": hospital['name'],
            "website": hospital['website'],
            "keyword_density": keyword_density,
            "avg_readability": avg_readability,
            "pages_crawled": len(pages)
        })
        
    return results