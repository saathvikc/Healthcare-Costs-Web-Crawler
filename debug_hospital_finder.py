from hospital_finder import find_hospitals, _get_city_coordinates, _find_nearby_hospitals
import time
import json

def debug_hospital_finder(city: str, state: str):
    """
    Debug function to pinpoint issues with finding hospitals in a specific city
    """
    print(f"---------- DEBUG: {city}, {state} ----------")
    
    # Step 1: Test city coordinate lookup
    print("\nTesting city geocoding:")
    try:
        start_time = time.time()
        coordinates = _get_city_coordinates(city, state)
        elapsed = time.time() - start_time
        
        if coordinates:
            print(f"✅ City coordinates found in {elapsed:.2f}s: lat={coordinates['lat']}, lng={coordinates['lng']}")
        else:
            print(f"❌ Failed to find coordinates for {city}, {state}")
            print("Possible issues:")
            print("  - City name might be misspelled")
            print("  - API rate limiting")
            print("  - Network connectivity issues")
            return
    except Exception as e:
        print(f"❌ Error during geocoding: {e}")
        return
    
    # Step 2: Test hospital lookup with the coordinates
    print("\nTesting hospital lookup:")
    try:
        start_time = time.time()
        hospitals = _find_nearby_hospitals(coordinates["lat"], coordinates["lng"])
        elapsed = time.time() - start_time
        
        if hospitals:
            print(f"✅ Found {len(hospitals)} hospitals in {elapsed:.2f}s")
            # Show first 3 for sample
            for i, hospital in enumerate(hospitals[:3], 1):
                print(f"  {i}. {hospital['name']}")
        else:
            print(f"❌ No hospitals found near coordinates: {coordinates['lat']}, {coordinates['lng']}")
            print("Possible issues:")
            print("  - Search radius might be too small (currently 15km)")
            print("  - OpenStreetMap might not have hospital data for this region")
            print("  - API might be rate limiting requests")
            
            # Try with a larger radius
            print("\nTrying with a larger radius (30km):")
            custom_query = f"""
            [out:json];
            node["amenity"="hospital"](around:30000,{coordinates['lat']},{coordinates['lng']});
            out body 10;
            """
            print(f"Query: {custom_query}")
            
            try:
                import requests
                overpass_url = "https://overpass-api.de/api/interpreter"
                response = requests.post(overpass_url, data={"data": custom_query})
                response.raise_for_status()
                
                results = response.json()
                if results.get("elements", []):
                    print(f"✅ Found {len(results['elements'])} hospitals with larger radius")
                else:
                    print("❌ Still no hospitals found with larger radius")
                    
                    # Try searching for any medical facilities
                    print("\nTrying to find any healthcare facilities:")
                    broader_query = f"""
                    [out:json];
                    node["amenity"~"clinic|doctors|hospital|healthcare"](around:30000,{coordinates['lat']},{coordinates['lng']});
                    out body 10;
                    """
                    
                    response = requests.post(overpass_url, data={"data": broader_query})
                    response.raise_for_status()
                    results = response.json()
                    
                    if results.get("elements", []):
                        print(f"✅ Found {len(results['elements'])} healthcare facilities with broader search")
                    else:
                        print("❌ No healthcare facilities found at all - likely an API issue")
                        
            except Exception as e:
                print(f"Error during expanded search: {e}")
    except Exception as e:
        print(f"❌ Error during hospital lookup: {e}")
    
    print("\n---------- END DEBUG ----------")

if __name__ == "__main__":
    # Test Chicago specifically
    debug_hospital_finder("Chicago", "IL")
    
    # Compare with a known working city
    print("\n\n")
    debug_hospital_finder("Boston", "MA")