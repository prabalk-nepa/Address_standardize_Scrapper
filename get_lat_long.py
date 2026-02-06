import pandas as pd
import requests
import time

def geocode_address(address):
    """
    Geocode an address using Nominatim (OpenStreetMap) API
    
    Args:
        address: Street address to geocode
    
    Returns:
        tuple: (latitude, longitude) or (None, None) if failed
    """
    base_url = "https://nominatim.openstreetmap.org/search"
    
    params = {
        'q': address,
        'format': 'json',
        'limit': 1
    }
    
    headers = {
        'User-Agent': 'AddressGeocoder/1.0'  # Nominatim requires a user agent
    }
    
    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data and len(data) > 0:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            return lat, lon
        else:
            print(f"No results found for '{address}'")
            return None, None
            
    except Exception as e:
        print(f"Error geocoding '{address}': {str(e)}")
        return None, None

def main():
    # Read the CSV file
    input_file = "C:\\Users\\praba\\Downloads\\businesses_from_pdf.csv"  # Change this to your CSV filename
    df = pd.read_csv(input_file)
    
    # Create new columns for latitude and longitude
    df['Latitude'] = None
    df['Longitude'] = None
    
    # Geocode each address
    for idx, row in df.iterrows():
        address = row['Address']
        print(f"Geocoding: {address}")
        
        lat, lng = geocode_address(address)
        
        df.at[idx, 'Latitude'] = lat
        df.at[idx, 'Longitude'] = lng
        
        # Add delay to respect Nominatim's usage policy (max 1 request per second)
        time.sleep(1.5)
    
    # Save the results to a new CSV file
    output_file = 'businesses_with_coordinates.csv'
    df.to_csv(output_file, index=False)
    
    print(f"\nGeocoding complete! Results saved to {output_file}")
    print(f"\nSummary:")
    print(f"Total addresses: {len(df)}")
    print(f"Successfully geocoded: {df['Latitude'].notna().sum()}")
    print(f"Failed: {df['Latitude'].isna().sum()}")

if __name__ == "__main__":
    main()