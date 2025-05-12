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
        
        if results["best_price"] is not None:
            f.write(f"BEST PRICE FOUND: ${results['best_price']:.2f}\n")
            f.write(f"Hospital: {results['hospital_name']}\n")
            f.write(f"Address: {results['hospital_address']}\n")
            f.write(f"Source: {results['source_url']}\n\n")
            
            f.write("ALL PRICES FOUND:\n")
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
        A list of dictionaries containing information about crawled pages:
        - url: The page URL
        - title: Page title
        - text: Page text content (cleaned)
        - depth: The depth level of the page
    """
    if not url:
        return []
    
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
        
        headers = {
            "User-Agent": "HospitalInfoCrawler/1.0"
        }
        
        while queue and page_count < max_pages:
            current_url, depth = queue.popleft()
            
            # Stop if we've reached the maximum depth
            if depth > max_depth:
                continue
            
            try:
                # Add delay to be respectful
                time.sleep(1)
                
                # Fetch page content
                response = requests.get(current_url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract page information
                title = soup.title.string.strip() if soup.title else "No title"
                
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
                print(f"Crawled {page_count}/{max_pages} pages: {current_url}")
                
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
                
            except Exception as e:
                print(f"Error crawling {current_url}: {e}")
                continue
        
        return results
        
    except Exception as e:
        print(f"Error starting crawl of {url}: {e}")
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
        A dictionary containing:
        - found: Boolean indicating if pricing was found
        - price: The price if found (or None)
        - currency: Currency of the price (default: USD)
        - source_url: URL where the pricing was found
        - context: Text surrounding the price information
    """
    if not url:
        return {"found": False, "price": None, "currency": "USD", "source_url": None, "context": None}
    
    # Terms to look for that might indicate pricing information
    price_page_keywords = [
        "price", "pricing", "cost", "charge", "fee", "rate", 
        "estimate", "financial", "bill", "payment", "transparency",
        "patient charges", "service charges"
    ]
    
    # Crawl the website focusing on pages likely to contain pricing
    pages = crawl_hospital_website(url, max_depth=max_depth, max_pages=20)
    relevant_pages = []
    
    # First pass: find pages likely to contain pricing information
    for page in pages:
        page_text = page['text'].lower()
        page_title = page['title'].lower()
        
        # Check if page has pricing-related terms
        is_pricing_page = any(keyword in page_text or keyword in page_title for keyword in price_page_keywords)
        
        # Check if page has the CPT code
        has_cpt_code = cpt_code in page_text
        
        # Check if page has the procedure name (if provided)
        has_procedure_name = True
        if procedure_name:
            has_procedure_name = procedure_name.lower() in page_text
            
        # Prioritize pages with pricing terms and either CPT code or procedure name
        if is_pricing_page and (has_cpt_code or has_procedure_name):
            relevant_pages.append(page)
    
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
    from bs4 import BeautifulSoup
    
    # Initialize result
    result = {
        "found": False,
        "price": None,
        "currency": "USD",
        "source_url": page['url'],
        "context": None
    }
    
    text = page['text']
    
    # Create a window around CPT code mentions
    cpt_positions = []
    for match in re.finditer(cpt_code, text):
        start_pos = max(0, match.start() - 200)
        end_pos = min(len(text), match.end() + 200)
        window = text[start_pos:end_pos]
        cpt_positions.append((window, start_pos, end_pos))
    
    # If procedure name is provided, also look for windows around it
    if procedure_name:
        for match in re.finditer(procedure_name, text, re.IGNORECASE):
            start_pos = max(0, match.start() - 200)
            end_pos = min(len(text), match.end() + 200)
            window = text[start_pos:end_pos]
            cpt_positions.append((window, start_pos, end_pos))
    
    # Look for price patterns in these windows
    for window, _, _ in cpt_positions:
        # Pattern for currency amounts
        price_matches = re.findall(r'[\$]?\s?([0-9,]+(?:\.[0-9]{2})?)', window)
        
        # If we find prices, extract the first one
        if price_matches:
            # Clean up the price and convert to float
            price_str = price_matches[0].replace(',', '')
            try:
                price = float(price_str)
                result["found"] = True
                result["price"] = price
                result["context"] = window
                return result
            except ValueError:
                # Not a valid price
                pass
    
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
            "all_prices": []
        }
    
    all_prices = []
    
    logger.info(f"Searching for pricing of CPT {cpt_code} ({procedure_name or 'no name'}) in {city}, {state}")
    logger.info(f"Found {len(hospitals)} hospitals to search")
    
    for hospital in hospitals:
        if hospital['website']:
            logger.info(f"Searching {hospital['name']}...")
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
                logger.info(f"✓ Found price: ${pricing['price']} at {hospital['name']}")
            else:
                logger.info(f"× No pricing found at {hospital['name']}")
                if pricing.get("pdf_links"):
                    logger.info(f"  Found potential PDF resources: {len(pricing['pdf_links'])}")
    
    # Find the best price
    if all_prices:
        best_price_info = min(all_prices, key=lambda x: x["price"])
        
        return {
            "best_price": best_price_info["price"],
            "hospital_name": best_price_info["hospital_name"],
            "hospital_address": best_price_info["hospital_address"],
            "source_url": best_price_info["source_url"],
            "context": best_price_info["context"],
            "all_prices": all_prices
        }
    else:
        logger.warning("No prices found for any hospitals")
        return {
            "best_price": None,
            "hospital_name": None,
            "hospital_address": None,
            "source_url": None,
            "context": None,
            "all_prices": []
        }


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
        
        # Save results to file
        save_results_to_file(best_price_info, output_paths["results_file"])
        
        if best_price_info["best_price"] is not None:
            logger.info(f"Best price found: ${best_price_info['best_price']:.2f} at {best_price_info['hospital_name']}")
            logger.info(f"Results saved to {output_paths['results_file']}")
        else:
            logger.info("No pricing information found for this procedure.")
            logger.info(f"Empty results saved to {output_paths['results_file']}")
            
    except Exception as e:
        logger.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()