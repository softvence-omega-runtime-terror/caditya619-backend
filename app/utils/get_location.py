from geopy.geocoders import Nominatim

geolocator = Nominatim(user_agent="vendor-location")

def get_location_name(latitude: float, longitude: float):
    try:
        location = geolocator.reverse((latitude, longitude), language="en")
        return location.address if location else None
    except Exception as e:
        print("Reverse geocoding error:", e)
        return None
