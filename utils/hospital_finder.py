import requests
from geopy.geocoders import Nominatim
import time
import json

class HospitalFinder:
    def __init__(self, api_key=None):
        """
        Initialize the hospital finder.
        
        Args:
            api_key (str, optional): Google Places API key (if available)
        """
        self.api_key = api_key
        self.geocoder = Nominatim(user_agent="healthcare-cost-finder")
        
    def _geocode_location(self, location):
        """Convert address to coordinates"""
        try:
            location_data = self.geocoder.geocode(location)
            if location_data:
                return (location_data.latitude, location_data.longitude)
            return None
        except Exception as e:
            print(f"Error geocoding location: {str(e)}")
            return None
    
    def find_nearby_hospitals(self, location, radius=10, limit=10):
        """
        Find hospitals near a location using OpenStreetMap data.
        
        Args:
            location (str): Address or coordinates
            radius (float): Radius in miles (converted to km for API)
            limit (int): Maximum number of results
            
        Returns:
            list: List of hospital information dictionaries
        """
        # First geocode the location
        coords = self._geocode_location(location)
        if not coords:
            print(f"Could not geocode location: {location}")
            return []
            
        # Convert radius from miles to km (Overpass API uses meters)
        radius_km = radius * 1.60934
        radius_m = int(radius_km * 1000)
        
        # Query Overpass API for hospitals and medical centers
        overpass_url = "https://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json];
        (
          node["amenity"="hospital"](around:{radius_m},{coords[0]},{coords[1]});
          way["amenity"="hospital"](around:{radius_m},{coords[0]},{coords[1]});
          relation["amenity"="hospital"](around:{radius_m},{coords[0]},{coords[1]});
          node["healthcare"="hospital"](around:{radius_m},{coords[0]},{coords[1]});
          way["healthcare"="hospital"](around:{radius_m},{coords[0]},{coords[1]});
          relation["healthcare"="hospital"](around:{radius_m},{coords[0]},{coords[1]});
          
          node["amenity"="clinic"](around:{radius_m},{coords[0]},{coords[1]});
          way["amenity"="clinic"](around:{radius_m},{coords[0]},{coords[1]});
          relation["amenity"="clinic"](around:{radius_m},{coords[0]},{coords[1]});
        );
        out body;
        >;
        out skel qt;
        """
        
        try:
            response = requests.post(overpass_url, data={"data": overpass_query})
            response.raise_for_status()  # Raise exception for HTTP errors
            data = response.json()
            
            hospitals = []
            for element in data.get("elements", []):
                if "tags" in element:
                    tags = element["tags"]
                    hospital = {
                        'id': element.get("id"),
                        'name': tags.get("name", "Unknown Hospital"),
                        'address': self._format_address(tags),
                        'phone': tags.get("phone", None),
                        'website': tags.get("website", None)
                    }
                    
                    # Add coordinates
                    if element["type"] == "node":
                        hospital["lat"] = element.get("lat")
                        hospital["lon"] = element.get("lon")
                    
                    # Only add hospitals with names
                    if hospital['name'] != "Unknown Hospital":
                        hospitals.append(hospital)
                        
                    # Stop when limit is reached
                    if len(hospitals) >= limit:
                        break
            
            # For hospitals without websites, try to find them using search engines
            for hospital in hospitals:
                if not hospital.get('website'):
                    hospital['website'] = self._find_website(hospital['name'], location)
            
            return hospitals
            
        except Exception as e:
            print(f"Error finding hospitals: {str(e)}")
            return []
    
    def _format_address(self, tags):
        """Format an address from OSM tags"""
        address_parts = []
        
        # Try to get structured address first
        if "addr:housenumber" in tags and "addr:street" in tags:
            address_parts.append(f"{tags['addr:housenumber']} {tags['addr:street']}")
        
        # Add city, state, etc.
        if "addr:city" in tags:
            address_parts.append(tags["addr:city"])
        if "addr:state" in tags:
            address_parts.append(tags["addr:state"])
        if "addr:postcode" in tags:
            address_parts.append(tags["addr:postcode"])
            
        # If we have a full address, use it
        if address_parts:
            return ", ".join(address_parts)
            
        # Fall back to the "address" tag if it exists
        if "address" in tags:
            return tags["address"]
            
        # No address found
        return None
    
    def _find_website(self, hospital_name, location):
        """Try to find a hospital's website using a search engine API or web scraping"""
        # This would typically use a search engine API like Google Custom Search
        # For now, we'll just append domain names to hospital names as a simple heuristic
        
        # Clean up the name
        clean_name = hospital_name.lower()
        clean_name = clean_name.replace("hospital", "").replace("medical center", "").strip()
        clean_name = clean_name.replace(" ", "")
        
        # Generate possible domains
        possible_websites = [
            f"http://www.{clean_name}.org",
            f"http://www.{clean_name}.com",
            f"http://www.{clean_name}hospital.org",
            f"http://www.{clean_name}hospital.com",
        ]
        
        # In a real implementation, you would verify these websites actually exist
        # For now, just return the first option as a placeholder
        return possible_websites[0] if possible_websites else None
        
    def get_hospital_websites(self, location, radius=10, limit=10):
        """
        Get websites for hospitals near a location.
        
        Args:
            location (str): Address or coordinates
            radius (float): Radius in miles
            limit (int): Maximum number of results
            
        Returns:
            list: List of website URLs
        """
        hospitals = self.find_nearby_hospitals(location, radius, limit)
        return [hospital['website'] for hospital in hospitals if hospital.get('website')]
        
    def get_hospital_seed_urls(self, location, radius=10, limit=10):
        """
        Get seed URLs for the web crawler.
        
        Args:
            location (str): Address or coordinates
            radius (float): Radius in miles
            limit (int): Maximum number of results
            
        Returns:
            dict: Dictionary mapping seed URLs to hospital information
        """
        hospitals = self.find_nearby_hospitals(location, radius, limit)
        
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