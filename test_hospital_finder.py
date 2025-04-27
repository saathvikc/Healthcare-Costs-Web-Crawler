from utils.hospital_finder import find_hospitals

def test_hospital_finder():
    """
    Simple test function to find hospitals in different cities
    """
    test_cases = [
        ("Chicago", "IL")
    ]
    
    for city, state in test_cases:
        print(f"\nTesting: {city}, {state}")
        hospitals = find_hospitals(city, state, limit=5)
        
        if hospitals:
            print(f"Found {len(hospitals)} hospitals:")
            for i, hospital in enumerate(hospitals, 1):
                print(f"{i}. {hospital['name']}")
                print(f"   Address: {hospital['address']}")
                print(f"   Coordinates: ({hospital['latitude']}, {hospital['longitude']})")
                if hospital['phone']:
                    print(f"   Phone: {hospital['phone']}")
                if hospital['website']:
                    print(f"   Website: {hospital['website']}")
        else:
            print(f"No hospitals found in {city}, {state}")

if __name__ == "__main__":
    test_hospital_finder()