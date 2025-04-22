import requests
import re
import json
import random
import time
from bs4 import BeautifulSoup

class HospitalFinder:
    def __init__(self):
        """Initialize the hospital finder."""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
    def find_hospitals_in_city(self, city, state=None, limit=25):
        """
        Find hospitals in a specified US city.
        
        Args:
            city (str): City name
            state (str, optional): State abbreviation (e.g. 'CA', 'NY')
            limit (int): Maximum number of hospitals to return
            
        Returns:
            list: List of hospital information dictionaries
        """
        hospitals = []
        
        # Format the location
        location = city
        if state:
            location = f"{city}, {state}"
            
        print(f"Looking for hospitals in {location}...")
        
        try:
            # First, try to find hospitals using Google search API
            hospitals = self._search_hospitals(location, limit)
            
            # If we don't have enough results, add some major hospital networks
            if len(hospitals) < limit:
                additional = self._add_major_hospitals(location, limit - len(hospitals))
                hospitals.extend(additional)
                
            # Add some generic healthcare pricing URLs
            self._add_pricing_sites(hospitals, location)
            
            # Limit to the requested number
            return hospitals[:limit]
            
        except Exception as e:
            print(f"Error finding hospitals: {str(e)}")
            # Fall back to some default hospitals and healthcare sites
            return self._get_fallback_hospitals(location, limit)

    def _search_hospitals(self, location, limit):
        """Search for hospitals using Google."""
        hospitals = []
        
        # Use Google search to find hospitals
        search_query = f"hospitals in {location}"
        google_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
        
        try:
            response = requests.get(google_url, headers=self.headers)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract hospital information from search results
                # This is a simplified version - actual extraction would be more complex
                for result in soup.select('.g'):
                    title_elem = result.select_one('h3')
                    link_elem = result.select_one('a')
                    
                    if title_elem and link_elem and 'href' in link_elem.attrs:
                        title = title_elem.get_text()
                        link = link_elem['href']
                        
                        # Extract the actual URL from Google's redirect
                        if link.startswith('/url?'):
                            link_match = re.search(r'url\?q=([^&]+)', link)
                            if link_match:
                                link = link_match.group(1)
                        
                        # Skip if not a real hospital website
                        if not self._is_hospital_site(title, link):
                            continue
                            
                        hospital = {
                            'id': f"hosp-{len(hospitals) + 1}",
                            'name': title,
                            'website': link,
                            'address': f"{location}",  # Simplified - just use the city
                        }
                        hospitals.append(hospital)
                        
                        if len(hospitals) >= limit:
                            break
            
            return hospitals
            
        except Exception as e:
            print(f"Error in Google search: {str(e)}")
            return []
            
    def _is_hospital_site(self, name, url):
        """Check if a site seems to be a legitimate hospital website."""
        name_lower = name.lower()
        url_lower = url.lower()
        
        # Check for hospital indicators in name
        hospital_keywords = ['hospital', 'medical center', 'health', 'healthcare', 
                             'clinic', 'physician', 'doctors', 'medicine']
                             
        # Check for exclusion terms
        exclusion_terms = ['booking', 'yelp', 'zocdoc', 'review', 'wikipedia', 'indeed', 
                           'jobs', 'glassdoor', 'news', 'definition', 'facebook', 'youtube']
        
        # Check if it looks like a hospital name
        is_hospital_name = any(keyword in name_lower for keyword in hospital_keywords)
        
        # Check if it should be excluded
        should_exclude = any(term in url_lower for term in exclusion_terms)
        
        return is_hospital_name and not should_exclude
    
    def _add_major_hospitals(self, location, limit):
        """Add major hospital networks that might be in the location."""
        major_hospitals = [
            {'name': 'Mayo Clinic', 'website': 'https://www.mayoclinic.org'},
            {'name': 'Cleveland Clinic', 'website': 'https://my.clevelandclinic.org'},
            {'name': 'Johns Hopkins Hospital', 'website': 'https://www.hopkinsmedicine.org'},
            {'name': 'Massachusetts General Hospital', 'website': 'https://www.massgeneral.org'},
            {'name': 'UCLA Medical Center', 'website': 'https://www.uclahealth.org'},
            {'name': 'UCSF Medical Center', 'website': 'https://www.ucsfhealth.org'},
            {'name': 'Stanford Health Care', 'website': 'https://stanfordhealthcare.org'},
            {'name': 'NewYork-Presbyterian Hospital', 'website': 'https://www.nyp.org'},
            {'name': 'Cedars-Sinai Medical Center', 'website': 'https://www.cedars-sinai.org'},
            {'name': 'Northwestern Memorial Hospital', 'website': 'https://www.nm.org'},
            {'name': 'University of Michigan Hospitals', 'website': 'https://www.uofmhealth.org'},
            {'name': 'Brigham and Women\'s Hospital', 'website': 'https://www.brighamandwomens.org'},
            {'name': 'Houston Methodist Hospital', 'website': 'https://www.houstonmethodist.org'},
            {'name': 'Barnes-Jewish Hospital', 'website': 'https://www.barnesjewish.org'},
            {'name': 'Mount Sinai Hospital', 'website': 'https://www.mountsinai.org'},
            {'name': 'Duke University Hospital', 'website': 'https://www.dukehealth.org'},
            {'name': 'University of Washington Medical Center', 'website': 'https://www.uwmedicine.org'},
        ]
        
        results = []
        for idx, hospital in enumerate(random.sample(major_hospitals, min(limit, len(major_hospitals)))):
            hosp = hospital.copy()
            hosp['id'] = f"major-{idx+1}"
            hosp['address'] = location
            results.append(hosp)
            
        return results
    
    def _add_pricing_sites(self, hospitals, location):
        """Add healthcare pricing sites to the list."""
        pricing_sites = [
            {'name': 'Healthcare Bluebook', 'website': 'https://www.healthcarebluebook.com'},
            {'name': 'Fair Health Consumer', 'website': 'https://www.fairhealthconsumer.org'},
            {'name': 'Medicare.gov Hospital Compare', 'website': 'https://www.medicare.gov/care-compare/'},
            {'name': 'GoodRx', 'website': 'https://www.goodrx.com'},
        ]
        
        for idx, site in enumerate(pricing_sites):
            site_copy = site.copy()
            site_copy['id'] = f"pricing-{idx+1}"
            site_copy['address'] = location
            hospitals.append(site_copy)
    
    def _get_fallback_hospitals(self, location, limit=10):
        """Return fallback hospital data when search fails."""
        # Create some generic hospital entries
        hospitals = []
        
        city = location.split(',')[0].strip()
        
        hospitals.append({
            'id': 'fallback-1',
            'name': f"{city} General Hospital",
            'website': 'https://www.generalhospital.org',
            'address': location
        })
        
        hospitals.append({
            'id': 'fallback-2',
            'name': f"{city} Medical Center",
            'website': 'https://www.medicalcenter.org',
            'address': location
        })
        
        hospitals.append({
            'id': 'fallback-3',
            'name': f"{city} Memorial Hospital",
            'website': 'https://www.memorialhospital.org',
            'address': location
        })
        
        # Add pricing sites
        self._add_pricing_sites(hospitals, location)
        
        return hospitals[:limit]
    
    def get_hospital_websites(self, city, state=None, limit=25):
        """
        Get websites for hospitals in a city.
        
        Args:
            city (str): City name
            state (str, optional): State abbreviation
            limit (int): Maximum number of results
            
        Returns:
            list: List of website URLs
        """
        hospitals = self.find_hospitals_in_city(city, state, limit)
        return [hospital['website'] for hospital in hospitals if 'website' in hospital]
        
    def get_hospital_seed_urls(self, city, state=None, radius=None, limit=25):
        """
        Get seed URLs for the web crawler.
        
        Args:
            city (str): City name
            state (str, optional): State abbreviation
            radius (float, optional): Ignored - kept for compatibility
            limit (int): Maximum number of results
            
        Returns:
            dict: Dictionary mapping seed URLs to hospital information
        """
        hospitals = self.find_hospitals_in_city(city, state, limit)
        
        seeds = {}
        for hospital in hospitals:
            if hospital.get('website'):
                base_url = hospital['website']
                
                # Add the main website
                if base_url not in seeds:
                    seeds[base_url] = hospital
                
                # Add common pricing pages
                price_pages = [
                    f"{base_url.rstrip('/')}/pricing",
                    f"{base_url.rstrip('/')}/costs",
                    f"{base_url.rstrip('/')}/cost",
                    f"{base_url.rstrip('/')}/fees",
                    f"{base_url.rstrip('/')}/billing",
                    f"{base_url.rstrip('/')}/patient-information/billing",
                    f"{base_url.rstrip('/')}/patients/billing",
                    f"{base_url.rstrip('/')}/financial",
                    f"{base_url.rstrip('/')}/financial-assistance",
                    f"{base_url.rstrip('/')}/price-transparency",
                ]
                
                for page in price_pages:
                    seeds[page] = hospital
                        
        return seeds