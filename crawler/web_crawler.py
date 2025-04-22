import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import time
from collections import deque
from tqdm import tqdm

class WebCrawler:
    def __init__(self, seed_urls, hospital_info=None, max_depth=3, delay=1.0, max_pages=100, user_agent=None, logger=None):
        """
        Initialize the BFS web crawler.
        
        Args:
            seed_urls (dict): Dictionary mapping URLs to hospital information
            hospital_info (dict): Hospital information by URL
            max_depth (int): Maximum depth to crawl (default 3)
            delay (float): Delay between requests in seconds (be respectful)
            max_pages (int): Maximum pages to crawl
            user_agent (str): User agent string to use in requests
            logger: Logger object for logging information
        """
        self.max_depth = max_depth
        self.delay = delay
        self.max_pages = max_pages
        self.logger = logger
        self.hospital_info = hospital_info or {}
        
        self.visited = set()
        self.queue = deque()
        
        # Add seed URLs with depth 0
        for url in seed_urls:
            self.queue.append((url, 0))
            # Store hospital info for this URL
            if url in seed_urls and url not in self.hospital_info:
                self.hospital_info[url] = seed_urls[url]
            
        self.headers = {
            'User-Agent': user_agent or 'HealthcareCostFinder/1.0 (Research Project)'
        }
        
        # Keywords to look for in URLs and content
        self.healthcare_keywords = [
            'price', 'cost', 'fee', 'charge', 'pricing',
            'estimate', 'hospital', 'clinic', 'medical', 'healthcare',
            'procedure', 'surgery', 'diagnostic', 'treatment', 'cpt',
            'insurance', 'price-transparency', 'cash-price',
            'patient-cost', 'billing'
        ]

    def is_relevant_url(self, url):
        """Check if URL seems relevant to healthcare costs."""
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        
        # Skip common non-relevant file types
        if any(path_lower.endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.gif']):
            return False
            
        # Check for healthcare-related keywords in URL
        url_lower = url.lower()
        return any(keyword in url_lower for keyword in self.healthcare_keywords)

    def get_hospital_for_url(self, url):
        """Determine which hospital a URL belongs to"""
        parsed_url = urlparse(url)
        url_domain = parsed_url.netloc
        
        # Check if we have an exact match
        if url in self.hospital_info:
            return self.hospital_info[url]
            
        # Check if we have a domain match
        for seed_url, hospital in self.hospital_info.items():
            seed_domain = urlparse(seed_url).netloc
            if url_domain == seed_domain:
                return hospital
                
        return None

    def crawl(self, page_parser, cost_extractor):
        """
        Start crawling using BFS algorithm.
        
        Args:
            page_parser: Object that can parse pages for links and content
            cost_extractor: Object that can extract cost information
        
        Returns:
            dict: Extracted healthcare cost information
        """
        results = {}
        pages_crawled = 0
        
        with tqdm(total=self.max_pages, desc="Crawling") as pbar:
            while self.queue and pages_crawled < self.max_pages:
                url, depth = self.queue.popleft()
                
                # Skip if we've seen this URL or if it's too deep
                if url in self.visited:
                    if self.logger:
                        self.logger.log_skipped(url, "Already visited")
                    continue
                
                if depth > self.max_depth:
                    if self.logger:
                        self.logger.log_skipped(url, f"Exceeds max depth ({self.max_depth})")
                    continue
                
                # Skip if URL doesn't seem relevant
                if not self.is_relevant_url(url):
                    self.visited.add(url)
                    if self.logger:
                        self.logger.log_skipped(url, "Not relevant to healthcare costs")
                    continue
                    
                # Get hospital information for this URL
                hospital = self.get_hospital_for_url(url)
                if not hospital and depth > 0:  # Allow seed URLs without hospital info
                    self.visited.add(url)
                    if self.logger:
                        self.logger.log_skipped(url, "Not associated with a known hospital")
                    continue
                
                # Try to fetch the page
                try:
                    response = requests.get(url, headers=self.headers, timeout=10)
                    if response.status_code == 200:
                        # Mark as visited
                        self.visited.add(url)
                        pages_crawled += 1
                        pbar.update(1)
                        
                        if self.logger:
                            hospital_name = hospital['name'] if hospital else "Unknown Hospital"
                            self.logger.log_visited(url, depth, hospital_name)
                        
                        # Extract content
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Extract links for BFS, but only from the same hospital domain
                        if depth < self.max_depth:
                            links = page_parser.extract_links(soup, url)
                            for link in links:
                                # Only add links from the same hospital domain
                                link_hospital = self.get_hospital_for_url(link)
                                if link_hospital and link_hospital.get('id') == hospital.get('id'):
                                    if link not in self.visited:
                                        self.queue.append((link, depth + 1))
                                        self.hospital_info[link] = hospital
                        
                        # Extract cost information
                        page_results = cost_extractor.extract_costs(soup, url)
                        if page_results:
                            # Store results along with hospital information
                            if url not in results:
                                results[url] = {}
                                
                            results[url].update(page_results)
                            results[url]['hospital_info'] = hospital
                            
                            if self.logger:
                                self.logger.log_extracted_data(url, page_results)
                                if hospital:
                                    self.logger.log_hospital_info(url, hospital)
                        
                        # Be polite and wait
                        time.sleep(self.delay)
                    else:
                        # Non-200 status code
                        self.visited.add(url)
                        if self.logger:
                            self.logger.log_error(url, f"HTTP Status: {response.status_code}")
                        
                except Exception as e:
                    if self.logger:
                        self.logger.log_error(url, str(e))
                    else:
                        print(f"Error crawling {url}: {str(e)}")
                    self.visited.add(url)
        
        return results