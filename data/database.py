import json
import os
import datetime

class ResultsDatabase:
    def __init__(self, db_file='healthcare_costs.json'):
        """
        Initialize the database.
        
        Args:
            db_file (str): Path to the JSON database file
        """
        self.db_file = db_file
        self.data = self._load_db()
        
    def _load_db(self):
        """Load existing database or create new one"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Error reading database file {self.db_file}, creating new database")
                return {}
        return {}
        
    def save_db(self):
        """Save database to disk"""
        with open(self.db_file, 'w') as f:
            json.dump(self.data, f, indent=2)
            
    def store_results(self, results, location, cpt_codes):
        """
        Store crawling results in the database
        
        Args:
            results (dict): Results from the crawler
            location (str): Patient location
            cpt_codes (list): List of CPT codes that were searched for
        """
        # Create a unique search ID
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        search_id = f"search_{timestamp}"
        
        self.data[search_id] = {
            'timestamp': datetime.datetime.now().isoformat(),
            'location': location,
            'cpt_codes': cpt_codes,
            'results': results
        }
        
        # Save changes
        self.save_db()
        return search_id
        
    def get_search_results(self, search_id=None):
        """
        Retrieve search results
        
        Args:
            search_id (str, optional): Specific search ID to retrieve
            
        Returns:
            dict: Search results
        """
        if search_id:
            return self.data.get(search_id)
        return self.data
    
    def find_best_price(self, cpt_code):
        """
        Find the best price for a specific CPT code
        
        Args:
            cpt_code (str): CPT code to look for
            
        Returns:
            dict: Best price information
        """
        best_price = float('inf')
        best_result = None
        
        for search_id, search_data in self.data.items():
            for url, url_data in search_data['results'].items():
                if cpt_code in url_data:
                    # Check if this is the best price
                    price = url_data[cpt_code]['min_price']
                    if price < best_price:
                        best_price = price
                        best_result = {
                            'url': url,
                            'price': price,
                            'hospital_info': url_data.get('hospital_info', {})
                        }
        
        return best_result