import os
import logging
import re
from datetime import datetime
import glob
import uuid

class Logger:
    def __init__(self, log_dir='logs', cpt_codes=None, location=None):
        """
        Initialize the logger.
        
        Args:
            log_dir (str): Directory to store log files
            cpt_codes (list): List of CPT codes being searched
            location (str): Location being searched (city, state)
        """
        # Use absolute path if log_dir is relative
        if not os.path.isabs(log_dir):
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), log_dir)
            
        # Create logs directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Format location and CPT codes for folder name
        location_part = "unknown_location"
        if location:
            # Replace spaces and commas with underscores, remove other special chars
            location_part = re.sub(r'[^\w\s,]', '', location).replace(' ', '_').replace(',', '_').lower()
        
        cpt_part = "no_cpt"
        if cpt_codes and len(cpt_codes) > 0:
            # Join CPT codes with hyphens, limit to first 3 codes if there are many
            if len(cpt_codes) <= 3:
                cpt_part = "-".join(cpt_codes)
            else:
                cpt_part = f"{'-'.join(cpt_codes[:3])}_plus_{len(cpt_codes) - 3}_more"
        
        # Create a timestamp for the search
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create a unique folder for this search
        search_folder = f"{location_part}_{cpt_part}_{timestamp}"
        self.search_dir = os.path.join(log_dir, search_folder)
        
        # Create a counter to handle duplicate folder names
        counter = 1
        original_search_dir = self.search_dir
        while os.path.exists(self.search_dir):
            self.search_dir = f"{original_search_dir}_{counter}"
            counter += 1
            
        # Create the search directory
        os.makedirs(self.search_dir, exist_ok=True)
        
        # Define log filenames 
        crawl_filename = "crawl.log"
        data_filename = "data.log"
        error_filename = "error.log"
        hospital_filename = "hospitals.log"
        summary_filename = "summary.log"
        
        # Configure loggers
        self.crawl_logger = self._setup_logger(
            'crawl_logger', 
            os.path.join(self.search_dir, crawl_filename),
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        self.data_logger = self._setup_logger(
            'data_logger', 
            os.path.join(self.search_dir, data_filename),
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        self.error_logger = self._setup_logger(
            'error_logger', 
            os.path.join(self.search_dir, error_filename),
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        self.hospital_logger = self._setup_logger(
            'hospital_logger',
            os.path.join(self.search_dir, hospital_filename),
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        self.summary_logger = self._setup_logger(
            'summary_logger',
            os.path.join(self.search_dir, summary_filename),
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Log basic information
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.summary_logger.info(f"Search started at {timestamp}")
        self.summary_logger.info(f"Location: {location}")
        self.summary_logger.info(f"CPT Codes: {', '.join(cpt_codes) if cpt_codes else 'None'}")
        
        # Also log to each individual log file
        self.crawl_logger.info(f"Search started at {timestamp}")
        self.crawl_logger.info(f"Location: {location}")
        self.crawl_logger.info(f"CPT Codes: {', '.join(cpt_codes) if cpt_codes else 'None'}")
        
        self.data_logger.info(f"Search started at {timestamp}")
        self.data_logger.info(f"Location: {location}")
        self.data_logger.info(f"CPT Codes: {', '.join(cpt_codes) if cpt_codes else 'None'}")
        
        # Keep track of logged hospitals
        self.logged_hospitals = set()

    def _setup_logger(self, name, log_file, format_str):
        """Set up a logger with specified configuration"""
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(format_str))
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        
        # Remove any existing handlers to avoid duplicate logging
        if logger.hasHandlers():
            logger.handlers.clear()
            
        logger.addHandler(handler)
        
        return logger
    
    def log_visited(self, url, depth, hospital_name="Unknown"):
        """Log a visited URL"""
        self.crawl_logger.info(f"Visited URL: {url} (depth: {depth}, hospital: {hospital_name})")
        
        # Also log the hospital if it's not been logged yet
        if hospital_name != "Unknown" and hospital_name not in self.logged_hospitals:
            self.log_hospital(hospital_name, url)
            self.logged_hospitals.add(hospital_name)
    
    def log_hospital(self, name, url):
        """Log a hospital being checked"""
        self.hospital_logger.info(f"Hospital: {name} - Main URL: {url}")
    
    def log_hospitals_list(self, hospitals):
        """Log a list of hospitals that will be checked"""
        self.hospital_logger.info(f"Found {len(hospitals)} hospitals to check:")
        for i, hospital in enumerate(hospitals, 1):
            name = hospital.get('name', 'Unknown Hospital')
            website = hospital.get('website', 'No website')
            self.hospital_logger.info(f"{i}. {name}: {website}")
        
        # Also add to summary
        self.summary_logger.info(f"Found {len(hospitals)} hospitals to check")
        
    def log_skipped(self, url, reason):
        """Log a skipped URL"""
        self.crawl_logger.info(f"Skipped URL: {url} - Reason: {reason}")
    
    def log_extracted_data(self, url, data):
        """Log extracted data"""
        self.data_logger.info(f"Data extracted from URL: {url}")
        for cpt_code, info in data.items():
            if cpt_code != 'hospital_info':  # Skip the hospital info in this log
                self.data_logger.info(f"  CPT {cpt_code}: {info}")
                
                # Add to summary as well
                if 'min_price' in info:
                    self.summary_logger.info(f"Found price for CPT {cpt_code}: ${info['min_price']:.2f} at {url}")
    
    def log_hospital_info(self, url, hospital_info):
        """Log extracted hospital information"""
        self.data_logger.info(f"Hospital info from URL: {url}")
        for key, value in hospital_info.items():
            if value:  # Only log non-empty values
                self.data_logger.info(f"  {key}: {value}")
    
    def log_error(self, url, error_message):
        """Log an error"""
        self.error_logger.error(f"Error processing URL: {url} - {error_message}")
    
    def log_search_complete(self, results_count, search_id):
        """Log search completion information"""
        self.summary_logger.info(f"Crawling complete - found cost information on {results_count} pages")
        self.summary_logger.info(f"Results saved with search ID: {search_id}")
        
    def log_best_prices(self, best_prices):
        """Log best prices found for each CPT code"""
        self.summary_logger.info("Best prices found:")
        for cpt_code, info in best_prices.items():
            if info:
                self.summary_logger.info(f"CPT {cpt_code}: ${info['price']:.2f} at {info['hospital_info'].get('name', 'Unknown Hospital')}")
            else:
                self.summary_logger.info(f"CPT {cpt_code}: No prices found")
    
    def get_search_dir(self):
        """Return the search directory path"""
        return self.search_dir