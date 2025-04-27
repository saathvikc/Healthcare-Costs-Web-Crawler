import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urljoin, urlparse
import re
import time
import random
from collections import deque

class HospitalWebCrawler:
    def __init__(self, max_pages: int = 20, delay: float = 1.0):
        """
        Initialize the hospital web crawler.
        
        Args:
            max_pages: Maximum number of pages to crawl per hospital website
            delay: Delay between requests in seconds (to be respectful)
        """
        self.max_pages = max_pages
        self.delay = delay
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        # Keywords that might indicate cost-related pages
        self.cost_keywords = [
            'price', 'cost', 'charge', 'billing', 'financial', 'payment', 
            'insurance', 'transparency', 'estimat', 'fee', 'patient', 'surgery',
            'procedure', 'cpt', 'service', 'cash', 'pricing'
        ]
        
    def crawl_hospital_site(self, hospital: Dict[str, Any], cpt_code: str) -> Dict[str, Any]:
        """
        Crawl a hospital website to find cost information for a specific CPT code using BFS.
        
        Args:
            hospital: Hospital dictionary containing website URL
            cpt_code: The CPT code to search for
            
        Returns:
            Updated hospital dictionary with cost information if found
        """
        website = hospital.get("website")
        if not website:
            hospital["cost_info"] = {"status": "No website available"}
            return hospital
            
        # Ensure URL has proper scheme
        if not website.startswith(('http://', 'https://')):
            website = 'https://' + website
            
        try:
            # BFS queue for URLs
            queue = deque([website])
            visited_urls = set([website])
            pages_crawled = 0
            base_domain = urlparse(website).netloc
            
            while queue and pages_crawled < self.max_pages:
                current_url = queue.popleft()
                pages_crawled += 1
                
                try:
                    print(f"Crawling: {current_url}")
                    response = requests.get(current_url, headers=self.headers, timeout=10)
                    if response.status_code != 200:
                        continue
                        
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # First check if this page contains cost information
                    cost_info = self._find_cost_info(soup, cpt_code, current_url)
                    if cost_info:
                        hospital["cost_info"] = cost_info
                        return hospital
                    
                    # Find and prioritize links
                    links = self._extract_and_prioritize_links(soup, current_url, base_domain, cpt_code)
                    
                    # Add unvisited links to the queue
                    for link_url, _ in links:
                        if link_url not in visited_urls and urlparse(link_url).netloc == base_domain:
                            queue.append(link_url)
                            visited_urls.add(link_url)
                    
                    # Be nice to the server
                    time.sleep(self.delay + random.uniform(0, 0.5))
                    
                except Exception as e:
                    print(f"Error crawling {current_url}: {e}")
                    continue
            
            # If we've crawled everything and found nothing
            hospital["cost_info"] = {"status": "Cost information not found", 
                                    "searched_pages": pages_crawled}
            return hospital
            
        except Exception as e:
            hospital["cost_info"] = {"status": f"Error crawling website: {str(e)}"}
            return hospital
    
    def _extract_and_prioritize_links(self, soup: BeautifulSoup, base_url: str, 
                                     base_domain: str, cpt_code: str) -> List[tuple]:
        """
        Extract links from the page and prioritize them based on relevance to cost information.
        
        Returns:
            List of tuples (url, priority_score)
        """
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            # Skip empty, javascript, and anchor links
            if not href or href.startswith(('javascript:', '#', 'tel:', 'mailto:')):
                continue
                
            full_url = urljoin(base_url, href)
            parsed_url = urlparse(full_url)
            
            # Skip external links and common irrelevant paths
            if (parsed_url.netloc != base_domain or
                any(ext in parsed_url.path.lower() for ext in 
                    ['.jpg', '.png', '.gif', '.pdf', '.mp3', '.mp4'])):
                continue
            
            # Calculate priority score based on link text and URL
            link_text = link.get_text().lower().strip()
            url_text = parsed_url.path.lower()
            
            priority = 0
            
            # Check for CPT code in link text or URL
            if cpt_code in link_text or cpt_code in url_text:
                priority += 50
            
            # Check for cost-related keywords in link text
            for keyword in self.cost_keywords:
                if keyword in link_text:
                    priority += 10
                if keyword in url_text:
                    priority += 5
            
            # PDF files with pricing information
            if parsed_url.path.lower().endswith('.pdf'):
                if any(kw in link_text for kw in self.cost_keywords):
                    priority += 15
            
            # Machine-readable files often contain pricing data
            if any(ext in parsed_url.path.lower() for ext in ['.csv', '.xlsx', '.json', '.xml']):
                if any(kw in link_text for kw in self.cost_keywords):
                    priority += 20
            
            links.append((full_url, priority))
        
        # Sort by priority (highest first)
        return sorted(links, key=lambda x: x[1], reverse=True)
            
    def _find_cost_info(self, soup: BeautifulSoup, cpt_code: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Find cost information in the HTML based on the CPT code.
        
        Args:
            soup: BeautifulSoup object of the page
            cpt_code: CPT code to search for
            url: URL of the current page
            
        Returns:
            Dictionary with cost information or None if not found
        """
        page_text = soup.get_text().lower()
        
        # Quick check if page might contain relevant information
        if cpt_code not in page_text and not any(kw in page_text for kw in ['price', 'cost', 'charge']):
            return None
        
        # Look for tables that might contain CPT codes and prices
        tables = soup.find_all('table')
        for table in tables:
            table_text = table.get_text().lower()
            if cpt_code in table_text and any(cost_term in table_text for cost_term in ['price', 'cost', 'charge', '$', 'fee']):
                # Extract the row with our CPT code
                for row in table.find_all('tr'):
                    row_text = row.get_text().lower()
                    if cpt_code in row_text:
                        # Try to extract the cost value
                        cost_match = re.search(r'\$([\d,]+(\.\d{2})?)', row_text)
                        if cost_match:
                            return {
                                "status": "found",
                                "cost": cost_match.group(0),
                                "source_url": url,
                                "type": "table"
                            }
        
        # Check for machine-readable files (JSON, CSV, XML) that might contain pricing information
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            link_text = link.get_text().lower()
            if any(ext in href.lower() for ext in ['.csv', '.xlsx', '.json', '.xml']):
                if any(term in link_text for term in ['price', 'cost', 'charge', 'transparency']):
                    return {
                        "status": "potential_file_found",
                        "file_url": urljoin(url, href),
                        "file_type": href.split('.')[-1],
                        "source_url": url
                    }
        
        # Check for specific divs or sections that might contain pricing info
        for tag in soup.find_all(['div', 'section', 'p', 'span']):
            tag_text = tag.get_text().lower()
            if cpt_code in tag_text and any(term in tag_text for term in ['price', 'cost', 'charge', '$']):
                # Try to find cost near the CPT code
                context = self._extract_context(tag_text, cpt_code)
                cost_match = re.search(r'\$([\d,]+(\.\d{2})?)', context)
                if cost_match:
                    return {
                        "status": "found",
                        "cost": cost_match.group(0),
                        "source_url": url,
                        "type": "text",
                        "context": context
                    }
        
        return None
    
    def _extract_context(self, text: str, keyword: str, context_chars: int = 200) -> str:
        """Extract text around a keyword for context"""
        keyword_pos = text.find(keyword)
        if keyword_pos == -1:
            return ""
        
        start = max(0, keyword_pos - context_chars)
        end = min(len(text), keyword_pos + len(keyword) + context_chars)
        return text[start:end]