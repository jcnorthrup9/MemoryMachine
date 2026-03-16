import os, random, subprocess, time

LOCS = ["Arts District, CA", "Little Tokyo, CA", "Boyle Heights, CA", "Echo Park, CA"]

def choose_and_scrape():
    site = random.choice(LOCS)
    print(f"TARGET: {site}")
    for attempt in range(3):
        try:
            # We call the other script
            subprocess.run(["python", "scraper.py", "--search", "Cafe", "--location", site], check=True)
            print("DONE")
            break
        except:
            print("Retrying...")
            time.sleep(10)

if __name__ == "__main__":
    choose_and_scrape()