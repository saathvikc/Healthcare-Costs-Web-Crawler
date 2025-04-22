from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import time

class DistanceCalculator:
    def __init__(self):
        """Initialize the distance calculator"""
        self.geocoder = Nominatim(user_agent="healthcare-cost-finder")
        self.location_cache = {}
        
    def geocode_address(self, address):
        """
        Convert an address to latitude/longitude
        
        Args:
            address (str): Address to geocode
            
        Returns:
            tuple: (latitude, longitude) or None if geocoding failed
        """
        # Check cache first
        if address in self.location_cache:
            return self.location_cache[address]
            
        try:
            # Geocode the address
            location = self.geocoder.geocode(address)
            if location:
                result = (location.latitude, location.longitude)
                self.location_cache[address] = result
                # Be polite to the geocoding service
                time.sleep(1)
                return result
        except Exception as e:
            print(f"Error geocoding address '{address}': {str(e)}")
            
        return None
        
    def calculate_distance(self, address1, address2):
        """
        Calculate the distance between two addresses
        
        Args:
            address1 (str): First address
            address2 (str): Second address
            
        Returns:
            float: Distance in miles, or None if calculation failed
        """
        coords1 = self.geocode_address(address1)
        coords2 = self.geocode_address(address2)
        
        if coords1 and coords2:
            # Calculate distance in miles
            distance = geodesic(coords1, coords2).miles
            return distance
            
        return None
        
    def calculate_distances_to_hospitals(self, patient_address, hospital_addresses):
        """
        Calculate distances from a patient to multiple hospitals
        
        Args:
            patient_address (str): Patient's address
            hospital_addresses (dict): Dictionary mapping hospital IDs to addresses
            
        Returns:
            dict: Dictionary mapping hospital IDs to distances
        """
        results = {}
        
        patient_coords = self.geocode_address(patient_address)
        if not patient_coords:
            return results
            
        for hospital_id, address in hospital_addresses.items():
            hospital_coords = self.geocode_address(address)
            if hospital_coords:
                distance = geodesic(patient_coords, hospital_coords).miles
                results[hospital_id] = distance
                
        return results