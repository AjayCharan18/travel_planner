import streamlit as st
import re
import random
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# API Configuration
GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY')
TRIPADVISOR_API_KEY = os.getenv('TRIPADVISOR_API_KEY')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
SERPER_API_KEY = os.getenv('SERPER_API_KEY')

# Destination Database
DESTINATION_DATABASE = {
    "paris": {
        "description": "The City of Light, famous for its art, fashion, and cuisine",
        "must_see": ["Eiffel Tower", "Louvre Museum", "Notre-Dame Cathedral"],
        "transport": {
            "metro": "Efficient subway system (buy carnet of 10 tickets)",
            "walking": "Most central areas are walkable"
        }
    },
    "rome": {
        "description": "The Eternal City, home to ancient ruins and delicious pasta",
        "must_see": ["Colosseum", "Trevi Fountain", "Vatican City"],
        "transport": {
            "metro": "Limited but useful lines (buy daily pass)",
            "walking": "Best way to explore the historic center"
        }
    },
    "tokyo": {
        "description": "A vibrant metropolis blending ultramodern and traditional culture",
        "must_see": ["Senso-ji Temple", "Shibuya Crossing", "Tokyo Skytree"],
        "transport": {
            "metro": "Efficient subway system (get Pasmo card)",
            "taxis": "Expensive but convenient at night"
        }
    }
}

# Initialize session state
def init_session_state():
    if 'conversation' not in st.session_state:
        st.session_state.conversation = [
            {"role": "assistant", "content": "🌍 Welcome to your AI Travel Planner! Where would you like to go?"}
        ]
    if 'user_info' not in st.session_state:
        st.session_state.user_info = {
            'destination': None,
            'duration': None,
            'budget': None,
            'purpose': None,
            'interests': None,
            'dietary_restrictions': None,
            'mobility_concerns': None,
            'accommodation_preference': None,
            'itinerary': None
        }
    if 'current_question' not in st.session_state:
        st.session_state.current_question = 'get_destination'
    if 'used_web_search' not in st.session_state:
        st.session_state.used_web_search = False

# Check API keys and show warnings
def check_api_keys():
    missing_keys = []
    if not GOOGLE_PLACES_API_KEY:
        missing_keys.append("Google Places")
    if not TRIPADVISOR_API_KEY:
        missing_keys.append("TripAdvisor")
    if not WEATHER_API_KEY:
        missing_keys.append("Weather")
    if not SERPER_API_KEY:
        missing_keys.append("Serper (Web Search)")
    
    if missing_keys:
        st.warning(f"Note: Some features may be limited without API keys for: {', '.join(missing_keys)}")

# Web Search Functions
def web_search(query, num_results=3):
    try:
        if SERPER_API_KEY:
            return serper_api_search(query, num_results)
        else:
            return fallback_google_search(query, num_results)
    except Exception as e:
        st.error(f"Web search error: {str(e)}")
        return []

def serper_api_search(query, num_results):
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = {
        'q': query,
        'num': num_results
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()
    results = response.json().get('organic', [])
    return [{
        'title': r.get('title'),
        'link': r.get('link'),
        'snippet': r.get('snippet')
    } for r in results]

def fallback_google_search(query, num_results):
    try:
        url = "https://www.google.com/search"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        params = {'q': query, 'num': num_results}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for g in soup.find_all('div', class_='g'):
            anchor = g.find('a')
            if anchor:
                title = g.find('h3')
                results.append({
                    'title': title.text if title else "No title",
                    'link': anchor['href'],
                    'snippet': ""
                })
        return results[:num_results]
    except Exception as e:
        st.error(f"Web search error: {str(e)}")
        return []

def scrape_website(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return {
            'headings': [h.get_text().strip() for h in soup.find_all(['h1', 'h2', 'h3'])],
            'content': [p.get_text().strip() for p in soup.find_all('p') if len(p.get_text().split()) > 5]
        }
    except Exception as e:
        st.error(f"Could not scrape website: {str(e)}")
        return None

def get_web_based_recommendations(destination, interests):
    try:
        query = f"Best {interests} in {destination} travel blog 2024"
        recommendations = []
        for result in web_search(query)[:3]:
            scraped = scrape_website(result['link'])
            if scraped:
                for heading in scraped['headings']:
                    if any(word in heading.lower() for word in ['best', 'top', 'must-see', 'recommend']):
                        recommendations.append({
                            'name': heading,
                            'type': 'attraction',
                            'source': result['link'],
                            'description': next((p for p in scraped['content'] if heading.lower() in p.lower()), "")
                        })
        st.session_state.used_web_search = True
        return recommendations[:5]
    except Exception as e:
        st.error(f"Error getting web recommendations: {str(e)}")
        return []

# API Helper Functions
def get_google_places(destination, query, budget_filter=None):
    try:
        if not GOOGLE_PLACES_API_KEY:
            raise ValueError("Google Places API key not configured")
            
        params = {
            'query': f"{query} in {destination}",
            'key': GOOGLE_PLACES_API_KEY
        }
        if budget_filter:
            params['maxprice'] = budget_filter
        
        response = requests.get("https://maps.googleapis.com/maps/api/place/textsearch/json", 
                              params=params, timeout=10)
        response.raise_for_status()
        results = response.json().get('results', [])
        
        if not results:
            return get_web_based_recommendations(destination, query)
        
        return [{
            'name': place.get('name'),
            'type': query,
            'rating': place.get('rating'),
            'price_level': place.get('price_level', 0),
            'location': place.get('formatted_address')
        } for place in results[:5]]
    except Exception as e:
        st.error(f"Error fetching Google Places data: {str(e)}")
        return get_web_based_recommendations(destination, query)

def get_tripadvisor_attractions(destination, interests):
    try:
        if not TRIPADVISOR_API_KEY:
            raise ValueError("TripAdvisor API key not configured")
            
        params = {
            'key': TRIPADVISOR_API_KEY,
            'searchQuery': destination,
            'category': 'attractions',
            'latLong': get_geocode(destination)
        }
        response = requests.get(
            "https://api.content.tripadvisor.com/api/v1/location/search",
            headers={"accept": "application/json"},
            params=params,
            timeout=10
        )
        response.raise_for_status()
        results = response.json().get('data', [])
        
        if interests:
            results = [r for r in results if any(i.lower() in r.get('name', '').lower() for i in interests)]
        
        return [{
            'name': place.get('name'),
            'type': 'attraction',
            'rating': place.get('rating'),
            'location': place.get('address_obj', {}).get('address_string')
        } for place in results[:5]]
    except Exception as e:
        st.error(f"Error fetching TripAdvisor data: {str(e)}")
        return get_web_based_recommendations(destination, interests or "attractions")

def get_weather_forecast(destination, date):
    try:
        if not WEATHER_API_KEY:
            return None
            
        geocode = get_geocode(destination)
        if not geocode:
            return None
            
        params = {
            'lat': geocode.split(',')[0],
            'lon': geocode.split(',')[1],
            'appid': WEATHER_API_KEY,
            'units': 'metric'
        }
        
        response = requests.get("https://api.openweathermap.org/data/2.5/forecast", params=params, timeout=10)
        response.raise_for_status()
        
        for forecast in response.json().get('list', []):
            if date in forecast.get('dt_txt', ''):
                weather = forecast.get('weather', [{}])[0]
                return {
                    'temp': forecast.get('main', {}).get('temp'),
                    'conditions': weather.get('description'),
                    'icon': weather.get('icon')
                }
        
        # Fallback to current weather
        current = requests.get("https://api.openweathermap.org/data/2.5/weather", params=params, timeout=10).json()
        weather = current.get('weather', [{}])[0]
        return {
            'temp': current.get('main', {}).get('temp'),
            'conditions': weather.get('description'),
            'icon': weather.get('icon')
        }
    except Exception as e:
        st.error(f"Error fetching weather data: {str(e)}")
        return None

def get_geocode(destination):
    try:
        if not GOOGLE_PLACES_API_KEY:
            raise ValueError("Google Places API key not configured")
            
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={'address': destination, 'key': GOOGLE_PLACES_API_KEY},
            timeout=10
        )
        response.raise_for_status()
        location = response.json().get('results', [{}])[0].get('geometry', {}).get('location')
        if location:
            return f"{location.get('lat')},{location.get('lng')}"
        
        # Fallback to known destinations
        if destination.lower() in DESTINATION_DATABASE:
            if "paris" in destination.lower():
                return "48.8566,2.3522"
            elif "rome" in destination.lower():
                return "41.9028,12.4964"
            elif "tokyo" in destination.lower():
                return "35.6762,139.6503"
        return None
    except Exception as e:
        st.error(f"Error geocoding destination: {str(e)}")
        return None

# Helper Functions
def extract_days(duration_str):
    try:
        if not duration_str:
            return 5
        duration_str = str(duration_str).lower()
        if "week" in duration_str:
            return 7
        if "month" in duration_str:
            return 30
        days_match = re.search(r'(\d+)', duration_str)
        return int(days_match.group(1)) if days_match else 5
    except Exception:
        return 5

def extract_budget(budget_str):
    try:
        if not budget_str:
            return 2000
        budget_str = str(budget_str).lower()
        if "luxury" in budget_str or "high" in budget_str:
            return 5000
        if "moderate" in budget_str or "medium" in budget_str:
            return 2500
        if "budget" in budget_str or "low" in budget_str or "cheap" in budget_str:
            return 1000
        budget_num = re.sub(r'[^\d]', '', budget_str)
        return int(budget_num) if budget_num else 2000
    except Exception:
        return 2000

def get_destination_info(destination, user_info):
    try:
        dest_info = {
            "description": f"A wonderful travel destination with many attractions",
            "must_see": [],
            "activities": [],
            "dining": [],
            "accommodation": []
        }
        
        # Check our database first
        dest_lower = destination.lower()
        if dest_lower in DESTINATION_DATABASE:
            dest_info.update(DESTINATION_DATABASE[dest_lower])
        
        # Get additional info from APIs
        interests = user_info.get('interests', '').split(', ') if user_info.get('interests') else None
        attractions = get_tripadvisor_attractions(destination, interests)
        if attractions:
            dest_info['must_see'] = [a['name'] for a in attractions[:5]]
        
        if interests:
            for interest in interests:
                dest_info['activities'].extend(get_google_places(destination, interest))
        
        budget_num = extract_budget(user_info.get('budget'))
        budget_filter = (1 if budget_num < 1500 else 
                        2 if budget_num < 3000 else 3)
        
        dining = get_google_places(destination, "restaurants", budget_filter)
        if dining:
            dest_info['dining'] = dining
        
        accommodation = get_google_places(
            destination, 
            user_info.get('accommodation_preference', 'hotel'), 
            budget_filter
        )
        if accommodation:
            dest_info['accommodation'] = accommodation
        
        # Fallback to web search if we don't have enough info
        if not dest_info['must_see']:
            web_recs = get_web_based_recommendations(destination, interests or "attractions")
            if web_recs:
                dest_info['must_see'] = [r['name'] for r in web_recs]
                dest_info['description'] = web_recs[0]['description'] if not dest_info['description'] else dest_info['description']
        
        return dest_info
    except Exception as e:
        st.error(f"Error getting destination info: {str(e)}")
        dest = destination.lower()
        if dest in DESTINATION_DATABASE:
            return DESTINATION_DATABASE[dest]
        dest_info['description'] = f"{destination.title()} is a popular travel destination."
        return dest_info

def filter_by_preferences(items, preferences):
    if not preferences or not items:
        return items
    
    filtered = []
    interests = preferences.get('interests', '').lower().split(', ') if preferences.get('interests') else []
    
    for item in items:
        if interests:
            item_name = item.get('name', '').lower()
            item_type = item.get('type', '').lower()
            if any(interest in item_name or interest in item_type for interest in interests):
                filtered.append(item)
                continue
                
        if 'dietary' in item and preferences.get('dietary_restrictions'):
            if preferences['dietary_restrictions'].lower() in item['dietary'].lower():
                filtered.append(item)
                continue
                
        if 'type' in item and preferences.get('accommodation_preference'):
            if preferences['accommodation_preference'].lower() in item['type'].lower():
                filtered.append(item)
                continue
    
    return filtered if filtered else items[:5]

def refine_vague_input(text, field):
    text_lower = text.lower()
    
    if field == "budget":
        if "moderate" in text_lower or "medium" in text_lower:
            return "For a moderate budget, I'd suggest $150-$200 per day. Does this range work for you?"
        if "low" in text_lower or "cheap" in text_lower or "budget" in text_lower:
            return "For a budget trip, I'd suggest $50-$100 per day. Does this range work for you?"
        if "high" in text_lower or "luxury" in text_lower or "expensive" in text_lower:
            return "For a luxury trip, I'd suggest $300+ per day. Does this range work for you?"
        if "some" in text_lower or "enough" in text_lower:
            return "Would you like me to suggest a budget range based on your destination?"
    
    if field == "duration":
        if "week" in text_lower:
            return "Would you like me to plan for 7 days (1 week)?"
        if "month" in text_lower:
            return "Would you like me to plan for 30 days (1 month)?"
        if "long" in text_lower or "extended" in text_lower:
            return "Would you like me to suggest an ideal duration for your destination?"
    
    if field == "interests":
        if "everything" in text_lower or "all" in text_lower:
            return "I'll include a mix of activities. Any particular favorites among these: cultural, adventure, food, relaxation?"
        if "some" in text_lower or "few" in text_lower:
            return "Would you like me to suggest a balanced mix of activities, or focus on specific types?"
        if "not sure" in text_lower or "don't know" in text_lower:
            return "I can suggest popular activities for your destination. Would you like that?"
    
    if field == "accommodation":
        if "surprise" in text_lower or "you choose" in text_lower:
            return "I can select a highly-rated option that fits your budget. Is that okay?"
        if "not sure" in text_lower or "don't know" in text_lower:
            return "Would you like me to suggest the best accommodation types for your destination?"
    
    return None

def extract_travel_info(text):
    info = {}
    if not text or not isinstance(text, str):
        return info
    
    text_lower = text.lower()
    
    # Destination extraction
    destination_match = re.search(
        r'(?:going to|visiting|travel(?:ing)? to|destination is?|in|trip to|heading to|visit|go to)\s*(.+?)(?:\s|,|\.|$)|^(paris|rome|london|new york|tokyo)\b',
        text_lower
    )
    if destination_match:
        dest = destination_match.group(1) or destination_match.group(2)
        if dest:
            info['destination'] = re.sub(r'[^a-zA-Z\s]', '', dest).strip().title()
    
    # Duration extraction
    duration_match = re.search(
        r'(\d+)\s?(?:day|week|month)s?\b|for\s(\d+)\s(?:day|week|month)s?\b|(\d+)-day',
        text_lower
    )
    if duration_match:
        duration = duration_match.group(1) or duration_match.group(2) or duration_match.group(3)
        if duration:
            info['duration'] = f"{duration} days"
    
    # Budget extraction
    budget_match = re.search(
        r'(?:budget|price|cost)\s?(?:of|is|around)?\s?(\$?\d+(?:,\d{3})*(?:\.\d{2})?)(?:\s|$)|(\d+)\s?(?:dollars|USD|EUR)|\$(\d+)|(low|moderate|medium|high|luxury)\s?budget',
        text_lower
    )
    if budget_match:
        budget = next((g for g in budget_match.groups() if g), None)
        if budget:
            info['budget'] = budget
    
    # Purpose extraction
    purpose_map = {
        r'\bvacation\b': 'Leisure',
        r'\bholiday\b': 'Leisure',
        r'\bbusiness\b': 'Business',
        r'\bwork\b': 'Business',
        r'\bhoneymoon\b': 'Honeymoon',
        r'\banniversary\b': 'Anniversary',
        r'\bfamily\b': 'Family',
        r'\bsolo\b': 'Solo',
        r'\bcouple\b': 'Romantic',
        r'\bfriends\b': 'Friends'
    }
    for pattern, purpose in purpose_map.items():
        if re.search(pattern, text_lower):
            info['purpose'] = purpose
            break
    
    # Interests extraction
    interests = []
    interest_map = {
        r'\bart\b': 'Art',
        r'\bmuseum\b': 'Art',
        r'\bhistory\b': 'History',
        r'\bhistorical\b': 'History',
        r'\bfood\b': 'Food',
        r'\bcuisine\b': 'Food',
        r'\beating\b': 'Food',
        r'\brestaurant\b': 'Food',
        r'\badventure\b': 'Adventure',
        r'\bhiking\b': 'Adventure',
        r'\boutdoor\b': 'Adventure',
        r'\brelax\b': 'Relaxation',
        r'\bspa\b': 'Relaxation',
        r'\bbeach\b': 'Relaxation',
        r'\bshop\b': 'Shopping',
        r'\bnature\b': 'Nature',
        r'\bpark\b': 'Nature',
        r'\bphotography\b': 'Photography',
        r'\barchitecture\b': 'Architecture'
    }
    for pattern, interest in interest_map.items():
        if re.search(pattern, text_lower):
            interests.append(interest)
    if interests:
        info['interests'] = ', '.join(list(set(interests)))
    
    # Dietary restrictions
    dietary_map = {
        r'\bvegetarian\b': 'Vegetarian',
        r'\bvegan\b': 'Vegan',
        r'\bgluten[\s-]?free\b': 'Gluten-free',
        r'\bkosher\b': 'Kosher',
        r'\bhalal\b': 'Halal',
        r'\blactose[\s-]?free\b': 'Dairy-free',
        r'\bnut[\s-]?free\b': 'Nut-free',
        r'\bpescatarian\b': 'Pescatarian'
    }
    for pattern, diet in dietary_map.items():
        if re.search(pattern, text_lower):
            info['dietary_restrictions'] = diet
            break
    
    # Mobility concerns
    mobility_map = {
        r'\bmobility\b': 'Limited mobility',
        r'\bwheelchair\b': 'Wheelchair accessible',
        r'\bdisability\b': 'Accessibility needed',
        r'\bwalking\s+difficult\b': 'Limited walking',
        r'\baccessibility\b': 'Accessibility needed',
        r'\bphysical\s+limitation\b': 'Limited mobility'
    }
    for pattern, mobility in mobility_map.items():
        if re.search(pattern, text_lower):
            info['mobility_concerns'] = mobility
            break
    
    # Accommodation preferences
    accom_map = {
        r'\bluxur\b': 'Luxury',
        r'\bboutique\b': 'Boutique',
        r'\bbudget\b': 'Budget',
        r'\bhostel\b': 'Hostel',
        r'\bairbnb\b': 'Vacation rental',
        r'\bcentral\b': 'Central location',
        r'\bquiet\b': 'Quiet area',
        r'\bresort\b': 'Resort',
        r'\bapartment\b': 'Apartment',
        r'\bguesthouse\b': 'Guesthouse',
        r'\bb&b\b': 'Bed and breakfast'
    }
    for pattern, accom in accom_map.items():
        if re.search(pattern, text_lower):
            info['accommodation_preference'] = accom
            break
    
    return info

def generate_detailed_itinerary(user_info):
    try:
        destination = user_info.get('destination', 'your destination')
        days = extract_days(user_info.get('duration', '5 days'))
        budget_num = extract_budget(user_info.get('budget', '$2000'))
        
        dest_info = get_destination_info(destination, user_info)
        activities = filter_by_preferences(dest_info.get('activities', []), user_info)
        dining = filter_by_preferences(dest_info.get('dining', []), user_info)
        accommodation = filter_by_preferences(dest_info.get('accommodation', []), user_info)
        
        itinerary = f"# ✈️ {destination.title()} {days}-Day Itinerary\n\n"
        itinerary += f"_{dest_info.get('description', 'A wonderful travel destination')}_\n\n"
        itinerary += "## 📝 Trip Overview\n"
        itinerary += f"- **Traveler**: {user_info.get('purpose', 'Leisure')} trip\n"
        itinerary += f"- **Interests**: {user_info.get('interests', 'General sightseeing')}\n"
        if user_info.get('dietary_restrictions'):
            itinerary += f"- **Dietary**: {user_info['dietary_restrictions']}\n"
        if user_info.get('mobility_concerns'):
            itinerary += f"- **Mobility**: {user_info['mobility_concerns']}\n"
        itinerary += f"- **Accommodation**: {user_info.get('accommodation_preference', 'Standard')}\n\n"
        
        itinerary += "## 🌟 Top Rated Attractions\n"
        for i, attraction in enumerate(dest_info.get('must_see', [])[:10], 1):
            itinerary += f"{i}. {attraction}\n"
        
        if activities:
            itinerary += "\n## 🎭 Recommended Activities\n"
            for item in activities[:8]:
                itinerary += f"- **{item.get('name')}**"
                if item.get('rating'):
                    itinerary += f" ⭐ {item.get('rating')}"
                if item.get('price_level'):
                    itinerary += f" {'$' * item.get('price_level', 1)}"
                if item.get('location'):
                    itinerary += f"\n  📍 {item.get('location')}"
                itinerary += "\n"
        
        if dining:
            itinerary += "\n## 🍽️ Dining Recommendations\n"
            for item in dining[:5]:
                itinerary += f"- **{item.get('name')}**"
                if item.get('rating'):
                    itinerary += f" ⭐ {item.get('rating')}"
                if item.get('price_level'):
                    itinerary += f" {'$' * item.get('price_level', 1)}"
                if item.get('location'):
                    itinerary += f"\n  📍 {item.get('location')}"
                itinerary += "\n"
        
        if accommodation:
            itinerary += "\n## 🏨 Accommodation Options\n"
            for item in accommodation[:3]:
                itinerary += f"- **{item.get('name')}**"
                if item.get('rating'):
                    itinerary += f" ⭐ {item.get('rating')}"
                if item.get('price_level'):
                    itinerary += f" {'$' * item.get('price_level', 1)}"
                if item.get('location'):
                    itinerary += f"\n  📍 {item.get('location')}"
                itinerary += "\n"
        
        itinerary += f"\n## 📅 Sample {days}-Day Schedule\n"
        base_date = datetime.now() + timedelta(days=7)
        
        for day in range(1, days + 1):
            trip_date = base_date + timedelta(days=day-1)
            date_str = trip_date.strftime("%A, %B %d")
            
            weather = get_weather_forecast(destination, trip_date.strftime("%Y-%m-%d"))
            weather_icon = f"https://openweathermap.org/img/wn/{weather.get('icon', '01d')}@2x.png" if weather else ""
            
            itinerary += f"\n**Day {day}: {date_str}**"
            if weather:
                itinerary += f" <img src='{weather_icon}' width='30'> {weather.get('temp', '?')}°C, {weather.get('conditions', '')}"
            itinerary += "\n"
            
            morning_acts = [act for act in activities if 'morning' in act.get('tags', [])] or activities
            morning_choice = random.choice([act.get('name') for act in morning_acts[:3]] or ['Explore the city'])
            itinerary += f"🌅 Morning: {morning_choice}\n"
            
            afternoon_acts = [act for act in activities if 'afternoon' in act.get('tags', [])] or activities
            afternoon_choice = random.choice([act.get('name') for act in afternoon_acts[:3]] or ['Visit local attractions'])
            itinerary += f"⛅ Afternoon: {afternoon_choice}\n"
            
            evening_options = []
            if dining:
                evening_options.append(f"Dinner at {random.choice([d.get('name') for d in dining[:3]])}")
            evening_options.extend(["Night walking tour", "Cultural performance", "Relax at your accommodation"])
            itinerary += f"🌇 Evening: {random.choice(evening_options)}\n"
        
        itinerary += f"\n## 💰 Budget Breakdown (${budget_num:,})\n"
        itinerary += f"- Accommodation: ${int(budget_num*0.4):,} (${int(budget_num*0.4/days):,}/night)\n"
        itinerary += f"- Food: ${int(budget_num*0.3):,} (${int(budget_num*0.3/days):,}/day)\n"
        itinerary += f"- Activities: ${int(budget_num*0.2):,}\n"
        itinerary += f"- Transportation: ${int(budget_num*0.1):,}\n"
        
        if 'transport' in dest_info:
            itinerary += "\n## 🚍 Transportation Tips\n"
            for mode, tip in dest_info['transport'].items():
                itinerary += f"- **{mode.title()}**: {tip}\n"
        
        if st.session_state.get('used_web_search'):
            itinerary += "\n*Note: Some recommendations were sourced from recent web searches.*"
        
        return itinerary
    except Exception as e:
        return f"⚠️ Error generating itinerary: {str(e)}"

def get_next_question(user_info):
    required_fields = [
        'destination', 'duration', 'budget', 'purpose', 'interests',
        'dietary_restrictions', 'mobility_concerns', 'accommodation_preference'
    ]
    
    for field in required_fields:
        if not user_info.get(field):
            return f"get_{field}"
    
    return "confirm_generate"

def handle_user_response(prompt):
    try:
        if not prompt or not isinstance(prompt, str):
            return "Please provide a valid travel request"
        
        # Extract info from user input
        extracted_info = extract_travel_info(prompt)
        st.session_state.user_info.update({k: v for k, v in extracted_info.items() if v is not None})
        
        # Add user message to conversation
        st.session_state.conversation.append({"role": "user", "content": prompt})
        
        # Check if we should generate itinerary
        if all(st.session_state.user_info.get(field) for field in 
            ['destination', 'duration', 'budget', 'purpose', 'interests']):
            
            if 'yes' in prompt.lower() or 'generate' in prompt.lower():
                with st.spinner("Creating your personalized itinerary..."):
                    itinerary = generate_detailed_itinerary(st.session_state.user_info)
                    st.session_state.user_info['itinerary'] = itinerary
                    return itinerary
            else:
                return "I have enough information to generate your itinerary. Would you like me to create it now?"
        
        # Handle special cases
        if (not st.session_state.user_info.get('dietary_restrictions') and 
            'food' not in (st.session_state.user_info.get('interests', '') or '').lower()):
            st.session_state.user_info['dietary_restrictions'] = 'None'
        
        # Determine next question
        next_q = get_next_question(st.session_state.user_info)
        
        # Handle vague inputs with clarification
        if next_q in ['get_budget', 'get_duration', 'get_interests', 'get_accommodation']:
            clarification = refine_vague_input(prompt, next_q.replace('get_', ''))
            if clarification:
                return clarification
        
        # Return appropriate question
        question_map = {
            'get_destination': "Where would you like to go?",
            'get_duration': "How many days will your trip be?",
            'get_budget': "What's your approximate budget for this trip?",
            'get_purpose': "Is this trip for leisure, business, or a special occasion?",
            'get_interests': "What are your main interests? (e.g., art, food, adventure)",
            'get_dietary_restrictions': "Any dietary restrictions we should consider?",
            'get_mobility_concerns': "Any mobility concerns we should account for?",
            'get_accommodation_preference': "What type of accommodation do you prefer?",
            'confirm_generate': "Would you like me to generate your itinerary now?"
        }
        
        return question_map.get(next_q, "How can I help you with your travel plans?")
    
    except Exception as e:
        return f"⚠️ Error processing your request: {str(e)}"

def reset_conversation():
    st.session_state.conversation = [
        {"role": "assistant", "content": "🌍 Welcome to your AI Travel Planner! Where would you like to go?"}
    ]
    st.session_state.user_info = {
        'destination': None,
        'duration': None,
        'budget': None,
        'purpose': None,
        'interests': None,
        'dietary_restrictions': None,
        'mobility_concerns': None,
        'accommodation_preference': None,
        'itinerary': None
    }
    st.session_state.current_question = 'get_destination'
    st.session_state.used_web_search = False

def main():
    st.set_page_config(
        page_title="✈️ AI Travel Planner Pro+",
        page_icon="🌍",
        layout="centered"
    )
    
    init_session_state()
    check_api_keys()
    
    st.title("✈️ AI Travel Planner Pro+")
    st.caption("Create your perfect personalized travel itinerary with real-time recommendations")
    
    # Sidebar with reset button
    with st.sidebar:
        st.header("Trip Details")
        if st.session_state.user_info.get('destination'):
            st.subheader(st.session_state.user_info['destination'])
            if st.session_state.user_info.get('duration'):
                st.write(f"**Duration:** {st.session_state.user_info['duration']}")
            if st.session_state.user_info.get('budget'):
                st.write(f"**Budget:** {st.session_state.user_info['budget']}")
        
        if st.button("🔄 Start New Trip"):
            reset_conversation()
            st.rerun()
    
    # Display conversation
    for msg in st.session_state.conversation:
        if msg["content"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
    
    # Handle user input
    if prompt := st.chat_input("Type your message here..."):
        with st.spinner("Planning your trip..."):
            response = handle_user_response(prompt)
            if response:
                st.session_state.conversation.append({"role": "assistant", "content": response})
                st.rerun()
    
    # Display itinerary if available
    if st.session_state.user_info.get('itinerary'):
        st.divider()
        st.markdown(st.session_state.user_info['itinerary'])
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "💾 Download Itinerary",
                st.session_state.user_info['itinerary'],
                file_name=f"{st.session_state.user_info.get('destination', 'travel').lower()}_itinerary.txt",
                mime="text/plain"
            )
        with col2:
            if st.button("✏️ Edit Trip Details"):
                reset_conversation()
                st.rerun()

if __name__ == "__main__":
    main()