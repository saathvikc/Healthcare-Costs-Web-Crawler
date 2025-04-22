import os
import logging
import time
from datetime import datetime

class Logger:
    def __init__(self, log_dir='logs'):
        """
        Initialize the logger.
        
        Args:
            log_dir (str): Directory to store log files
        """
        # Use absolute path if log_dir is relative
        if not os.path.isabs(log_dir):
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), log_dir)
            
        # Create logs directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Generate timestamp for log files
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Configure loggers
        self.crawl_logger = self._setup_logger(
            'crawl_logger', 
            os.path.join(log_dir, f'crawl_{timestamp}.log'),
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        self.data_logger = self._setup_logger(
            'data_logger', 
            os.path.join(log_dir, f'data_{timestamp}.log'),
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        self.error_logger = self._setup_logger(
            'error_logger', 
            os.path.join(log_dir, f'error_{timestamp}.log'),
            '%(asctime)s - %(levelname)s - %(message)s'
        )

    def _setup_logger(self, name, log_file, format_str):
        """Set up a logger with specified configuration"""
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(format_str))
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        
        return logger
    
    def log_visited(self, url, depth, hospital_name="Unknown"):
        """Log a visited URL"""
        self.crawl_logger.info(f"Visited URL: {url} (depth: {depth}, hospital: {hospital_name})")
    
    def log_skipped(self, url, reason):
        """Log a skipped URL"""
        self.crawl_logger.info(f"Skipped URL: {url} - Reason: {reason}")
    
    def log_extracted_data(self, url, data):
        """Log extracted data"""
        self.data_logger.info(f"Data extracted from URL: {url}")
        for cpt_code, info in data.items():
            if cpt_code != 'hospital_info':  # Skip the hospital info in this log
                self.data_logger.info(f"  CPT {cpt_code}: {info}")
    
    def log_hospital_info(self, url, hospital_info):
        """Log extracted hospital information"""
        self.data_logger.info(f"Hospital info from URL: {url}")
        for key, value in hospital_info.items():
            if value:  # Only log non-empty values
                self.data_logger.info(f"  {key}: {value}")
    
    def log_error(self, url, error_message):
        """Log an error"""
        self.error_logger.error(f"Error processing URL: {url} - {error_message}")