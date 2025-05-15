import requests
import json
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import time
import argparse
import logging
from datetime import datetime
import os
import re
import random
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


def setup_logging(log_file="hospital_finder.log"):
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also output to console
        ]
    )
    return logging.getLogger(__name__)


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


def find_hospitals(city: str, state: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Find hospitals in a specified city and state.
    
    Args:
        city: Name of the city
        state: Name of the state or state abbreviation
        limit: Maximum number of results to return (default: 10)
        
    Returns:
        A list of dictionaries containing hospital information, each with:
        - name: Name of the hospital
        - address: Full address
        - latitude: Latitude coordinate
        - longitude: Longitude coordinate
        - phone: Phone number (if available)
        - website: Website URL (if available)
        - distance: Distance from city center in kilometers (if available)
    """
    # Step 1: Get coordinates for the city
    city_coordinates = _get_city_coordinates(city, state)
    if not city_coordinates:
        return []
    
    # Step 2: Search for hospitals near these coordinates
    hospitals = _find_nearby_hospitals(
        city_coordinates["lat"],
        city_coordinates["lng"],
        limit
    )
    
    return hospitals


def _get_city_coordinates(city: str, state: str) -> Optional[Dict[str, float]]:
    """
    Get the latitude and longitude coordinates for a city.
    
    Args:
        city: Name of the city
        state: Name of the state
        
    Returns:
        Dictionary with 'lat' and 'lng' keys or None if geocoding failed
    """

    try:
        base_url = "https://nominatim.openstreetmap.org/search"
        params = {
            "city": city,
            "state": state,
            "country": "USA",
            "format": "json",
            "limit": 1
        }
        
        headers = {
            "User-Agent": "HospitalFinderApp/1.0"  # Required by Nominatim ToS
        }
        
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        
        results = response.json()
        if results:
            return {
                "lat": float(results[0]["lat"]),
                "lng": float(results[0]["lon"])
            }
        return None
    
    except Exception as e:
        print(f"Error getting coordinates for {city}, {state}: {e}")
        return None


def _find_nearby_hospitals(lat: float, lng: float, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Find hospitals near the specified coordinates.
    
    Args:
        lat: Latitude coordinate
        lng: Longitude coordinate
        limit: Maximum number of results to return
        
    Returns:
        List of hospital information dictionaries
    """
    # Using Overpass API (OpenStreetMap data)
    
    try:
        # Overpass query to find hospitals within approximately 30km radius (increased from 15km)
        # This larger radius works better for larger cities like Chicago
        query = f"""
        [out:json];
        node["amenity"="hospital"](around:30000,{lat},{lng});
        out body {limit};
        """
        
        overpass_url = "https://overpass-api.de/api/interpreter"
        response = requests.post(overpass_url, data={"data": query})
        response.raise_for_status()
        
        results = response.json()
        hospitals = []
        
        # If no hospitals found, try with additional tags that might be used for hospitals
        if not results.get("elements", []):
            query = f"""
            [out:json];
            (
              node["amenity"="hospital"](around:30000,{lat},{lng});
              node["healthcare"="hospital"](around:30000,{lat},{lng});
              node["building"="hospital"](around:30000,{lat},{lng});
            );
            out body {limit};
            """
            response = requests.post(overpass_url, data={"data": query})
            response.raise_for_status()
            results = response.json()
        
        for element in results.get("elements", []):
            if element["type"] == "node":
                tags = element.get("tags", {})
                hospital_name = tags.get("name", "Unknown Hospital")
                
                # Format address from available fields
                address_parts = []
                if "addr:housenumber" in tags and "addr:street" in tags:
                    address_parts.append(f"{tags['addr:housenumber']} {tags['addr:street']}")
                elif "addr:street" in tags:
                    address_parts.append(tags["addr:street"])
                
                if "addr:city" in tags:
                    address_parts.append(tags["addr:city"])
                
                if "addr:postcode" in tags:
                    address_parts.append(tags["addr:postcode"])
                
                address = ", ".join(address_parts) if address_parts else "Address unknown"
                
                hospitals.append({
                    "name": hospital_name,
                    "address": address,
                    "latitude": element["lat"],
                    "longitude": element["lon"],
                    "phone": tags.get("phone", None),
                    "website": tags.get("website", None),
                })
                
        return hospitals[:limit]
    
    except Exception as e:
        print(f"Error finding hospitals: {e}")
        return []


def crawl_hospital_website(url: str, max_depth: int = 3, max_pages: int = 100) -> List[Dict[str, Any]]:
    """
    Crawl a hospital website using BFS up to a specified depth.
    
    Args:
        url: The starting URL (hospital website)
        max_depth: Maximum depth to crawl (default: 3)
        max_pages: Maximum number of pages to crawl (default: 100)
        
    Returns:
        A list of dictionaries containing information about crawled pages
    """
    if not url:
        return []
    
    logger = logging.getLogger(__name__)
    
    # Normalize the starting URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # Parse the domain from the URL to stay within the same website
        domain = urlparse(url).netloc
        
        # Initialize data structures
        queue = deque([(url, 0)])  # (url, depth)
        visited = set([url])
        results = []
        page_count = 0
        
        # Create a session with retry capability
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"]
        )
        session.mount("http://", HTTPAdapter(max_retries=retries))
        session.mount("https://", HTTPAdapter(max_retries=retries))
        
        headers = {
            "User-Agent": random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
            ]),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        
        while queue and page_count < max_pages:
            current_url, depth = queue.popleft()
            
            # Stop if we've reached the maximum depth
            if depth > max_depth:
                continue
            
            try:
                # Add random delay to be respectful (0.5-2 seconds)
                time.sleep(random.uniform(0.5, 2))
                
                # Skip non-HTML resources
                if any(current_url.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx']):
                    continue
                
                # Skip certain URL patterns
                if re.search(r'(calendar|login|signin|signup|contact|feedback|search|404|403|500)', current_url, re.IGNORECASE):
                    continue
                
                # Fetch page content
                logger.debug(f"Fetching: {current_url}")
                response = session.get(current_url, headers=headers, timeout=15)
                response.raise_for_status()
                
                # Check if it's actually HTML
                content_type = response.headers.get('Content-Type', '').lower()
                if 'text/html' not in content_type:
                    logger.debug(f"Skipping non-HTML content: {current_url} ({content_type})")
                    continue
                
                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract page information
                title = soup.title.string.strip() if soup.title else "No title"
                
                # Remove script, style, and other non-content elements
                for element in soup.find_all(['script', 'style', 'meta', 'noscript', 'header', 'footer']):
                    element.decompose()
                
                # Extract text content and clean it
                text_content = soup.get_text(separator=' ', strip=True)
                # Remove excessive whitespace
                text_content = ' '.join(text_content.split())
                
                # Add page info to results
                results.append({
                    'url': current_url,
                    'title': title,
                    'text': text_content,
                    'depth': depth
                })
                
                page_count += 1
                logger.info(f"Crawled {page_count}/{max_pages} pages: {current_url}")
                
                # Only continue to find links if we haven't reached max depth
                if depth < max_depth:
                    # Find all links on the page
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        
                        # Skip certain links
                        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                            continue
                        
                        # Convert relative URLs to absolute URLs
                        full_url = urljoin(current_url, href)
                        
                        # Stay within the same domain
                        if urlparse(full_url).netloc != domain:
                            continue
                        
                        # Only add unvisited links to the queue
                        if full_url not in visited:
                            visited.add(full_url)
                            queue.append((full_url, depth + 1))
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error for {current_url}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Error crawling {current_url}: {e}")
                continue
        
        logger.info(f"Crawl completed. Visited {len(visited)} URLs, extracted content from {len(results)} pages")
        return results
        
    except Exception as e:
        logger.error(f"Error starting crawl of {url}: {e}")
        return []


def find_procedure_pricing(url: str, cpt_code: str, procedure_name: str = None, max_depth: int = 3) -> Dict[str, Any]:
    """
    Search a hospital website for pricing information related to a specific CPT code.
    
    Args:
        url: The hospital website URL
        cpt_code: The CPT code for the procedure
        procedure_name: Optional procedure name to search for
        max_depth: Maximum depth to crawl
        
    Returns:
        A dictionary containing pricing information
    """
    logger = logging.getLogger(__name__)
    
    if not url:
        return {"found": False, "price": None, "currency": "USD", "source_url": None, "context": None}
    
    # Enhanced terms to look for that might indicate pricing information
    price_page_keywords = [
        "price", "pricing", "cost", "charge", "fee", "rate", 
        "estimate", "financial", "bill", "payment", "transparency",
        "patient charges", "service charges", "chargemaster",
        "standard charges", "price list", "price transparency", "cost estimator"
    ]
    
    # First, check if the website has a dedicated pricing or transparency page
    # These are common URLs for hospital pricing pages
    transparency_urls = [
        "/pricing",
        "/prices",
        "/chargemaster",
        "/charges",
        "/price-transparency",
        "/standard-charges",
        "/patient-financial",
        "/cost-estimator",
        "/billing",
        "/financial-assistance"
    ]
    
    # Normalize the starting URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    
    # First try directly accessing common pricing URLs
    for path in transparency_urls:
        try:
            direct_url = urljoin(base_url, path)
            logger.info(f"Directly checking potential pricing page: {direct_url}")
            
            response = requests.get(direct_url, 
                                   headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}, 
                                   timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Remove script, style, and other non-content elements
                for element in soup.find_all(['script', 'style', 'meta', 'noscript']):
                    element.decompose()
                
                text = soup.get_text(separator=' ', strip=True).lower()
                
                # Check if this page contains pricing info and the CPT code
                if any(keyword in text for keyword in price_page_keywords):
                    logger.info(f"Found potential pricing page: {direct_url}")
                    page_info = {
                        'url': direct_url,
                        'title': soup.title.string if soup.title else "No title",
                        'text': text,
                        'depth': 0
                    }
                    
                    # Check for pricing on this specific page
                    price_info = _extract_price_from_page(page_info, cpt_code, procedure_name)
                    if price_info["found"]:
                        return price_info
        except Exception as e:
            logger.debug(f"Could not check {path}: {e}")
    
    # If direct URL checks fail, proceed with crawling
    logger.info(f"Starting website crawl: {url}")
    
    # Crawl the website focusing on pages likely to contain pricing
    pages = crawl_hospital_website(url, max_depth=max_depth, max_pages=30)  # Increased from 20 to 30
    relevant_pages = []
    
    # First pass: find pages likely to contain pricing information
    for page in pages:
        page_text = page['text'].lower()
        page_title = page['title'].lower()
        page_url = page['url'].lower()
        
        # Check if page has pricing-related terms
        is_pricing_page = any(keyword in page_text or keyword in page_title or keyword in page_url 
                              for keyword in price_page_keywords)
        
        # Check if page has the CPT code
        has_cpt_code = cpt_code in page_text
        
        # Check if page has the procedure name (if provided)
        has_procedure_name = True
        if procedure_name:
            has_procedure_name = procedure_name.lower() in page_text
            
        # Prioritize pages with pricing terms and either CPT code or procedure name
        if is_pricing_page and (has_cpt_code or has_procedure_name):
            relevant_pages.append(page)
        # Also add pages that VERY likely contain pricing even without specific mention
        elif ("price list" in page_text or "price transparency" in page_text or 
              "chargemaster" in page_text or "standard charges" in page_text):
            relevant_pages.append(page)
    
    logger.info(f"Found {len(relevant_pages)} pages that might contain pricing information")
    
    # Process relevant pages to extract pricing information
    for page in relevant_pages:
        price_info = _extract_price_from_page(page, cpt_code, procedure_name)
        if price_info["found"]:
            return price_info
    
    # If no specific pricing found in relevant pages, look for PDF links
    pdf_links = _find_pdf_pricing_resources(pages, cpt_code, procedure_name)
    if pdf_links:
        return {
            "found": False,
            "price": None,
            "currency": "USD",
            "source_url": None,
            "context": f"Pricing information might be available in these documents: {', '.join(pdf_links[:3])}",
            "pdf_links": pdf_links
        }
            
    return {"found": False, "price": None, "currency": "USD", "source_url": None, "context": None}


def _extract_price_from_page(page: Dict[str, Any], cpt_code: str, procedure_name: str = None) -> Dict[str, Any]:
    """
    Extract price information from a page for a specific CPT code and procedure.
    
    Args:
        page: Dictionary containing page information
        cpt_code: The CPT code to search for
        procedure_name: Optional procedure name to search for
        
    Returns:
        Dictionary with price information
    """
    import re
    
    # Initialize result
    result = {
        "found": False,
        "price": None,
        "currency": "USD",
        "source_url": page['url'],
        "context": None
    }
    
    text = page['text'].lower()
    url = page['url'].lower()
    
    # Check if this page is likely to contain pricing information
    pricing_indicators = [
        'price', 'cost', 'charge', 'fee', 'rate', 'pricing', 'estimate',
        'transparency', 'financial'
    ]
    
    is_pricing_page = any(indicator in text or indicator in url for indicator in pricing_indicators)
    if not is_pricing_page:
        return result
    
    # Prepare search terms
    cpt_code_pattern = re.compile(r'\b' + re.escape(cpt_code) + r'\b')
    
    # Create broader windows than before
    cpt_positions = []
    for match in cpt_code_pattern.finditer(text):
        start_pos = max(0, match.start() - 500)  # Increased window size
        end_pos = min(len(text), match.end() + 500)  # Increased window size
        window = text[start_pos:end_pos]
        cpt_positions.append((window, start_pos, end_pos))
    
    # If procedure name is provided, also look for windows around it
    if procedure_name:
        proc_name_pattern = re.compile(r'\b' + re.escape(procedure_name.lower()) + r'\b')
        for match in proc_name_pattern.finditer(text):
            start_pos = max(0, match.start() - 500)  # Increased window size
            end_pos = min(len(text), match.end() + 500)  # Increased window size
            window = text[start_pos:end_pos]
            cpt_positions.append((window, start_pos, end_pos))
    
    # Enhanced price pattern detection
    for window, _, _ in cpt_positions:
        # Pattern for currency amounts (multiple patterns to catch different formats)
        patterns = [
            r'[\$]?\s?([0-9,]+(?:\.[0-9]{2})?)',  # Basic price pattern
            r'cost[\s:]*[\$]?\s?([0-9,]+(?:\.[0-9]{2})?)',  # Cost: $XXX
            r'price[\s:]*[\$]?\s?([0-9,]+(?:\.[0-9]{2})?)',  # Price: $XXX
            r'charge[\s:]*[\$]?\s?([0-9,]+(?:\.[0-9]{2})?)',  # Charge: $XXX
            r'fee[\s:]*[\$]?\s?([0-9,]+(?:\.[0-9]{2})?)',     # Fee: $XXX
            r'rate[\s:]*[\$]?\s?([0-9,]+(?:\.[0-9]{2})?)',    # Rate: $XXX
        ]
        
        for pattern in patterns:
            price_matches = re.findall(pattern, window)
            
            # If we find prices, extract and filter them
            if price_matches:
                valid_prices = []
                for price_str in price_matches:
                    # Clean up the price and convert to float
                    price_str = price_str.replace(',', '')
                    try:
                        price = float(price_str)
                        # Filter out unreasonable prices (too low or too high)
                        if 10 <= price <= 50000:  # Most medical procedures cost between $10 and $50,000
                            valid_prices.append((price, window))
                    except ValueError:
                        # Not a valid price
                        pass
                
                # If we found valid prices, return the most reasonable one
                if valid_prices:
                    # Sort by price (choose middle price to avoid extremes)
                    valid_prices.sort(key=lambda x: x[0])
                    if len(valid_prices) > 2:
                        # Choose the middle price
                        chosen_price, context = valid_prices[len(valid_prices)//2]
                    else:
                        # For 1-2 prices, choose the first (lowest)
                        chosen_price, context = valid_prices[0]
                        
                    result["found"] = True
                    result["price"] = chosen_price
                    result["context"] = context
                    return result
    
    return result


def _find_pdf_pricing_resources(pages: List[Dict[str, Any]], cpt_code: str, procedure_name: str = None) -> List[str]:
    """
    Find URLs to PDF resources that might contain pricing information.
    
    Args:
        pages: List of pages from website crawl
        cpt_code: The CPT code being searched
        procedure_name: Optional procedure name
        
    Returns:
        List of URLs to potential pricing PDFs
    """
    pdf_urls = []
    
    # Keywords that suggest a PDF might contain pricing information
    pricing_keywords = ["price", "charge", "cost", "rate", "fee", "financial", "transparency"]
    
    for page in pages:
        try:
            # Re-download the page to parse links specifically (faster than re-crawling)
            response = requests.get(page['url'], headers={"User-Agent": "HospitalInfoCrawler/1.0"}, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all links
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                link_text = link.get_text().lower()
                
                # Check if it's a PDF link
                is_pdf = href.endswith('.pdf') or 'pdf' in href.lower()
                
                # Check if link text suggests pricing information
                has_price_keyword = any(keyword in link_text for keyword in pricing_keywords)
                
                if is_pdf and has_price_keyword:
                    full_url = urljoin(page['url'], href)
                    if full_url not in pdf_urls:
                        pdf_urls.append(full_url)
                        
        except Exception as e:
            print(f"Error checking for PDFs on {page['url']}: {e}")
            continue
    
    return pdf_urls


def find_best_procedure_price(city: str, state: str, cpt_code: str, procedure_name: str = None, max_depth: int = 3) -> Dict[str, Any]:
    """
    Finds the best (lowest) price for a medical procedure across hospitals in a given location.
    
    Args:
        city: Name of the city
        state: Name of the state or abbreviation
        cpt_code: CPT code for the procedure
        procedure_name: Optional name of the procedure (improves search accuracy)
        max_depth: Maximum depth for website crawling
        
    Returns:
        Dictionary containing pricing information
    """
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
    
    # Calculate search metrics
    metrics = calculate_search_metrics(hospitals, all_prices)
    
    # Create detailed report for hospitals with unsuccessful searches
    unsuccessful_hospitals = [
        {
            "name": attempt["hospital_name"], 
            "has_website": attempt["has_website"],
            "has_pdfs": attempt.get("has_pdfs", False),
            "error": attempt.get("error", None)
        } 
        for attempt in search_attempts if not attempt["success"]
    ]
    
    # Find the best price
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


def calculate_search_metrics(hospitals: List[Dict[str, Any]], all_prices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate success metrics for the hospital price search.
    
    Args:
        hospitals: List of hospitals searched
        all_prices: List of prices found
        
    Returns:
        Dictionary with search metrics
    """
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


def setup_output_directories(city: str, state: str, cpt_code: str, output_dir: str = "results") -> Dict[str, str]:
    """
    Create output directory structure based on search parameters and return file paths.
    
    Args:
        city: City name
        state: State name
        cpt_code: CPT code
        output_dir: Base output directory
        
    Returns:
        Dictionary with file paths for logs and results
    """
    # Create sanitized folder name from parameters
    folder_name = f"{city.replace(' ', '_')}_{state.upper()}_{cpt_code}"
    folder_path = os.path.join(output_dir, folder_name)
    
    # Create directory if it doesn't exist
    os.makedirs(folder_path, exist_ok=True)
    
    # Define file paths
    log_file = os.path.join(folder_path, "search.log")
    results_file = os.path.join(folder_path, "results.txt")
    
    return {
        "log_file": log_file,
        "results_file": results_file,
        "folder_path": folder_path
    }


def main():
    # Set up command line argument parser
    parser = argparse.ArgumentParser(
        description="Find the best price for a medical procedure across hospitals in a specified location."
    )
    parser.add_argument("city", help="City to search in")
    parser.add_argument("state", help="State to search in (full name or abbreviation)")
    parser.add_argument("cpt_code", help="CPT code for the medical procedure")
    parser.add_argument("--procedure-name", help="Name of the procedure (optional, improves search accuracy)")
    parser.add_argument("--output-dir", default="results", help="Base output directory")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum crawl depth")
    
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