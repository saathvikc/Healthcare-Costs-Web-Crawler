import sys
import os
import json
from typing import List, Dict, Any

# Add parent directory to path to enable imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crawler.web_crawler import HospitalWebCrawler
from crawler.page_parser import CostInfoParser
from utils.hospital_finder import find_hospitals

class SurgeryCostExtractor:
    def __init__(self, max_pages: int = 20, delay: float = 1.0):
        """
        Initialize the surgery cost extractor.
        
        Args:
            max_pages: Maximum number of pages to crawl per hospital website
            delay: Delay between requests in seconds
        """
        self.web_crawler = HospitalWebCrawler(max_pages=max_pages, delay=delay)
        self.page_parser = CostInfoParser()
    
    def extract_surgery_costs(self, city: str, state: str, cpt_code: str, 
                            max_hospitals: int = 5) -> List[Dict[str, Any]]:
        """
        Extract surgery cost information from hospitals in a specified city.
        
        Args:
            city: The city to search for hospitals
            state: The state to search for hospitals
            cpt_code: The CPT code for the surgery
            max_hospitals: Maximum number of hospitals to search
            
        Returns:
            List of hospital dictionaries with cost information
        """# filepath: /Users/saathvik/Info Retrieval HW/Info Retrieval Final Project/data/cost_extractor.py
import sys
import os
import json
from typing import List, Dict, Any

# Add parent directory to path to enable imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crawler.web_crawler import HospitalWebCrawler
from crawler.page_parser import CostInfoParser
from utils.hospital_finder import find_hospitals

class SurgeryCostExtractor:
    def __init__(self, max_pages: int = 20, delay: float = 1.0):
        """
        Initialize the surgery cost extractor.
        
        Args:
            max_pages: Maximum number of pages to crawl per hospital website
            delay: Delay between requests in seconds
        """
        self.web_crawler = HospitalWebCrawler(max_pages=max_pages, delay=delay)
        self.page_parser = CostInfoParser()
    
    def extract_surgery_costs(self, city: str, state: str, cpt_code: str, 
                            max_hospitals: int = 5) -> List[Dict[str, Any]]:
        """
        Extract surgery cost information from hospitals in a specified city.
        
        Args:
            city: The city to search for hospitals
            state: The state to search for hospitals
            cpt_code: The CPT code for the surgery
            max_hospitals: Maximum number of hospitals to search
            
        Returns:
            List of hospital dictionaries with cost information
        """