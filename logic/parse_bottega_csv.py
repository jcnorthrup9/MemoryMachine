import os
import csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, 'data', 'bottega_massing.csv')
MD_PATH = os.path.join(BASE_DIR, 'data', 'bottega_spatial_data.md')

def translate_csv_to_md():
    if not os.path.exists(CSV_PATH):
        print(f"❌ Error: Could not find {CSV_PATH}")
        return

    with open(CSV_PATH, 'r', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        headers = next(reader, None)
        
        if not headers:
            print("❌ Error: CSV file is empty.")
            return

        md_content = "# Bottega Louie Spatial Data\n\n"
        md_content += f"| {' | '.join(headers)} |\n"
        md_content += f"|{'|'.join(['---'] * len(headers))}|\n"

        for row in reader:
            md_content += f"| {' | '.join(row)} |\n"

    with open(MD_PATH, 'w', encoding='utf-8') as mdfile:
        mdfile.write(md_content)
        
    print(f"✅ Successfully generated markdown file at: {MD_PATH}")

if __name__ == "__main__":
    translate_csv_to_md()