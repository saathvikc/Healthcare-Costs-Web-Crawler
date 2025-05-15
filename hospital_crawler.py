import requests
import re
import logging
import time
import random
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
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

def find_hospitals(city: str, state: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Find hospitals in a specified city and state."""
    city_coordinates = _get_city_coordinates(city, state)
    if not city_coordinates:
        return []
    
    hospitals = _find_nearby_hospitals(
        city_coordinates["lat"],
        city_coordinates["lng"],
        limit
    )
    
    return hospitals

def _get_city_coordinates(city: str, state: str) -> Optional[Dict[str, float]]:
    """Get the latitude and longitude coordinates for a city."""
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
            "User-Agent": "HospitalFinderApp/1.0"
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
    """Find hospitals near the specified coordinates."""
    try:
        # Query to find hospitals within approximately 30km radius
        query = f"""
        [out:json];
        (
          node["amenity"="hospital"](around:30000,{lat},{lng});
          node["healthcare"="hospital"](around:30000,{lat},{lng});
          node["building"="hospital"](around:30000,{lat},{lng});
        );
        out body {limit};
        """
        
        overpass_url = "https://overpass-api.de/api/interpreter"
        response = requests.post(overpass_url, data={"data": query})
        response.raise_for_status()
        results = response.json()
        
        hospitals = []
        for element in results.get("elements", []):
            if element["type"] == "node":
                tags = element.get("tags", {})
                hospital_name = tags.get("name", "Unknown Hospital")
                
                # Format address
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
    """Crawl a hospital website using BFS up to a specified depth."""
    if not url:
        return []
    
    logger = logging.getLogger(__name__)
    
    # Normalize the starting URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        domain = urlparse(url).netloc
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
            
            if depth > max_depth:
                continue
            
            try:
                # Add random delay to be respectful
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
                
                # Find links if not at max depth
                if depth < max_depth:
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        
                        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                            continue
                        
                        full_url = urljoin(current_url, href)
                        
                        if urlparse(full_url).netloc != domain:
                            continue
                        
                        if full_url not in visited:
                            visited.add(full_url)
                            queue.append((full_url, depth + 1))
                
            except Exception as e:
                logger.warning(f"Error processing {current_url}: {e}")
                continue
        
        logger.info(f"Crawl completed. Visited {len(visited)} URLs, extracted content from {len(results)} pages")
        return results
        
    except Exception as e:
        logger.error(f"Error starting crawl of {url}: {e}")
        return []

def find_procedure_pricing(url: str, cpt_code: str, procedure_name: str = None, max_depth: int = 3) -> Dict[str, Any]:
    """Search a hospital website for pricing information related to a specific CPT code."""
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
    
    # Common URLs for hospital pricing pages
    transparency_urls = [
        "/pricing", "/prices", "/chargemaster", "/charges", "/price-transparency",
        "/standard-charges", "/patient-financial", "/cost-estimator", "/billing"
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
                
                # Remove non-content elements
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
        except Exception:
            pass
    
    # Crawl the website focusing on pages likely to contain pricing
    logger.info(f"Starting website crawl: {url}")
    pages = crawl_hospital_website(url, max_depth=max_depth, max_pages=30)
    relevant_pages = []
    
    # Find pages likely to contain pricing information
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
        elif any(term in page_text for term in ["price list", "price transparency", "chargemaster", "standard charges"]):
            relevant_pages.append(page)
    
    logger.info(f"Found {len(relevant_pages)} pages that might contain pricing information")
    
    # Process relevant pages to extract pricing information
    for page in relevant_pages:
        price_info = _extract_price_from_page(page, cpt_code, procedure_name)
        if price_info["found"]:
            return price_info
    
    # Look for PDF links if no specific pricing found
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
    """Extract price information from a page for a specific CPT code and procedure."""
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
    
    # Create text windows around CPT code mentions
    cpt_positions = []
    for match in cpt_code_pattern.finditer(text):
        start_pos = max(0, match.start() - 500)
        end_pos = min(len(text), match.end() + 500)
        window = text[start_pos:end_pos]
        cpt_positions.append((window, start_pos, end_pos))
    
    # Also look for windows around procedure name if provided
    if procedure_name:
        proc_name_pattern = re.compile(r'\b' + re.escape(procedure_name.lower()) + r'\b')
        for match in proc_name_pattern.finditer(text):
            start_pos = max(0, match.start() - 500)
            end_pos = min(len(text), match.end() + 500)
            window = text[start_pos:end_pos]
            cpt_positions.append((window, start_pos, end_pos))
    
    # Search for price patterns in the text windows
    for window, _, _ in cpt_positions:
        # Multiple patterns to catch different price formats
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
            
            if price_matches:
                valid_prices = []
                for price_str in price_matches:
                    # Clean up the price and convert to float
                    price_str = price_str.replace(',', '')
                    try:
                        price = float(price_str)
                        # Filter out unreasonable prices
                        if 10 <= price <= 50000:  # Most medical procedures cost between $10 and $50,000
                            valid_prices.append((price, window))
                    except ValueError:
                        pass
                
                # If valid prices found, return the most reasonable one
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
    """Find URLs to PDF resources that might contain pricing information."""
    pdf_urls = []
    
    # Keywords that suggest a PDF might contain pricing information
    pricing_keywords = ["price", "charge", "cost", "rate", "fee", "financial", "transparency"]
    
    for page in pages:
        try:
            # Re-download the page to parse links
            response = requests.get(page['url'], headers={"User-Agent": "HospitalInfoCrawler/1.0"}, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all links
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                link_text = link.get_text().lower()
                
                # Check if it's a PDF link with pricing keywords
                is_pdf = href.endswith('.pdf') or 'pdf' in href.lower()
                has_price_keyword = any(keyword in link_text for keyword in pricing_keywords)
                
                if is_pdf and has_price_keyword:
                    full_url = urljoin(page['url'], href)
                    if full_url not in pdf_urls:
                        pdf_urls.append(full_url)
                        
        except Exception:
            continue
    
    return pdf_urls

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two geographic coordinates in miles."""
    # You can implement a haversine formula here or use a library like geopy
    # For simplicity, I'm not including the full implementation
    return 1  # Placeholder