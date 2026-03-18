import os
import re
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def extract_spatial_info():
    txt_path = os.path.join(DATA_DIR, 'ot_johnson_data.txt')
    json_path = os.path.join(DATA_DIR, 'anonymized_ot_johnson_data.json')
    output_path = os.path.join(DATA_DIR, 'redacted_ot_johnson_data.txt')
    
    content = ""
    
    # 1. Read from TXT
    if os.path.exists(txt_path):
        with open(txt_path, 'r', encoding='utf-8') as f:
            content += f.read() + "\n\n"
    else:
        print(f"⚠️ Warning: Could not find {txt_path}")
        
    # 2. Read from JSON
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                # Extract text from various possible JSON structures
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                if isinstance(v, str): content += v + "\n"
                        elif isinstance(item, str):
                            content += item + "\n"
                elif isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list):
                            for item in v:
                                if isinstance(item, dict):
                                    for k2, v2 in item.items():
                                        if isinstance(v2, str): content += v2 + "\n"
                                elif isinstance(item, str):
                                    content += item + "\n"
            except Exception as e:
                print(f"❌ Error reading JSON: {e}")
    else:
        print(f"⚠️ Warning: Could not find {json_path}")
        
    if not content.strip():
        print("❌ Error: No content extracted from files.")
        return
        
    redacted_content = re.sub(r'(?i)o\.t\. johnson building|ot johnson|o\. t\. johnson|johnson block|johnson building', '[BUILDING NAME]', content)
    
    sentences = re.split(r'(?<=[.!?]) +|\n+', redacted_content)
    
    spatial_keywords = [
        'ceiling', 'wall', 'floor', 'marble', 'glass', 'lobby', 'elevator',
        'staircase', 'light', 'decor', 'ambiance', 'iron', 'brick', 'interior', 
        'exterior', 'space', 'architecture', 'facade', 'layout', 'corridor',
        'office', 'desk', 'seating', 'window', 'spacious', 'airy', 'building',
        'romanesque', 'historic', 'columns', 'glaze', 'vaulted', 'door', 'cornice',
        'history', 'built', 'opened', 'century', '1902', 'architect', 'designed',
        'past', 'era', 'former', 'original', 'memory', 'remains', '19th', '20th'
    ]
    
    extracted_sentences = []
    
    print("🔎 Scanning combined text for spatial data...")
    for sentence in sentences:
        sentence = sentence.strip()
        if any(keyword in sentence.lower() for keyword in spatial_keywords) and len(sentence) > 15:
            extracted_sentences.append(sentence)
                
    extracted_sentences = list(dict.fromkeys(extracted_sentences))
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n\n".join(extracted_sentences))
            
    print(f"✅ Extracted {len(extracted_sentences)} spatial descriptors.")
    print(f"✅ Saved recreation data to: {output_path}")

if __name__ == "__main__":
    extract_spatial_info()