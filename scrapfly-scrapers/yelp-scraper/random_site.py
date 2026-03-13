import os
import random
import subprocess
import time

LA_NEIGHBORHOODS = [
    "West Adams, Los Angeles, CA",
    "Koreatown, Los Angeles, CA",
    "Silver Lake, Los Angeles, CA",
    "Arts District, Los Angeles, CA",
    "Echo Park, Los Angeles, CA",
    "Boyle Heights, Los Angeles, CA",
    "Crenshaw, Los Angeles, CA",
    "Little Tokyo, Los Angeles, CA"
]

def choose_and_scrape():
    site = random.choice(LA_NEIGHBORHOODS)
    print("\n" + "="*50)
    print(f"🏛️  MEMORY MACHINE: SITE SELECTION")
    print(f"📍 TARGET: {site}")
    print("="*50)
    
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            print(f"🚀 Attempt {attempt + 1}...")
            cmd = ["python", "scraper.py", "--search", "Cafe", "--location", site]
            
            subprocess.run(cmd, check=True)
            print("\n✅ Process finished successfully.")
            break # Exit retry loop on success
            
        except subprocess.CalledProcessError:
            if attempt < max_retries:
                wait_time = 15
                print(f"❌ Attempt failed. Cooling down for {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                print("\n❌ All attempts failed. Yelp's firewall is currently too high.")

if __name__ == "__main__":
    choose_and_scrape()