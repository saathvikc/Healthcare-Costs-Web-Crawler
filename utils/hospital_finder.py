import requests
import json
from typing import List, Dict, Any, Optional


def find_hospitals(city: str, state: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Find hospitals in a specified city and state.
    
    Args:
        city: Name of the city
        state: Name of the state or state abbreviation
        limit: Maximum number of results to return (default: 10)
        
    Returns:
        A list of dictionaries containing hospital information, each with:
        - name: Name of the hospital
        - address: Full address
        - latitude: Latitude coordinate
        - longitude: Longitude coordinate
        - phone: Phone number (if available)
        - website: Website URL (if available)
        - distance: Distance from city center in kilometers (if available)
    """
    # Step 1: Get coordinates for the city
    city_coordinates = _get_city_coordinates(city, state)
    if not city_coordinates:
        return []
    
    # Step 2: Search for hospitals near these coordinates
    hospitals = _find_nearby_hospitals(
        city_coordinates["lat"],
        city_coordinates["lng"],
        limit
    )
    
    return hospitals


def _get_city_coordinates(city: str, state: str) -> Optional[Dict[str, float]]:
    """
    Get the latitude and longitude coordinates for a city.
    
    Args:
        city: Name of the city
        state: Name of the state
        
    Returns:
        Dictionary with 'lat' and 'lng' keys or None if geocoding failed
    """

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
            "User-Agent": "HospitalFinderApp/1.0"  # Required by Nominatim ToS
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
    """
    Find hospitals near the specified coordinates.
    
    Args:
        lat: Latitude coordinate
        lng: Longitude coordinate
        limit: Maximum number of results to return
        
    Returns:
        List of hospital information dictionaries
    """
    # Using Overpass API (OpenStreetMap data)
    
    try:
        # Overpass query to find hospitals within approximately 30km radius (increased from 15km)
        # This larger radius works better for larger cities like Chicago
        query = f"""
        [out:json];
        node["amenity"="hospital"](around:30000,{lat},{lng});
        out body {limit};
        """
        
        overpass_url = "https://overpass-api.de/api/interpreter"
        response = requests.post(overpass_url, data={"data": query})
        response.raise_for_status()
        
        results = response.json()
        hospitals = []
        
        # If no hospitals found, try with additional tags that might be used for hospitals
        if not results.get("elements", []):
            query = f"""
            [out:json];
            (
              node["amenity"="hospital"](around:30000,{lat},{lng});
              node["healthcare"="hospital"](around:30000,{lat},{lng});
              node["building"="hospital"](around:30000,{lat},{lng});
            );
            out body {limit};
            """
            response = requests.post(overpass_url, data={"data": query})
            response.raise_for_status()
            results = response.json()
        
        for element in results.get("elements", []):
            if element["type"] == "node":
                tags = element.get("tags", {})
                hospital_name = tags.get("name", "Unknown Hospital")
                
                # Format address from available fields
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


# Example usage:
if __name__ == "__main__":
    city = "Boston"
    state = "MA"
    hospitals = find_hospitals(city, state)
    
    print(f"Hospitals in {city}, {state}:")
    for hospital in hospitals:
        print(f"- {hospital['name']}: {hospital['address']}")