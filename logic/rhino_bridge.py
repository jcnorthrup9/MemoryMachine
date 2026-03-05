import rhinoscriptsyntax as rs
import csv
import json

# Path to your local data
DATA_PATH = r"D:\MemoryMachine\data\master_log.csv"
CONFIG_PATH = r"D:\MemoryMachine\logic\publication.json"

def build_memory_machine():
    with open(DATA_PATH, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Extract basic spatial data
            name = row['Residence']
            year = row['Year']
            
            # Placeholder: Create a point at a scaled coordinate 
            # (Mapping Lat/Lon to Rhino units)
            point = [float(year), 0, 0] 
            rs.AddTextDot(name, point)
            
            # Logic for drawing: This is where we will add 
            # your specific footprint rules from the JSON
            print("Processing: {} ({})".format(name, year))

if __name__ == "__main__":
    build_memory_machine()