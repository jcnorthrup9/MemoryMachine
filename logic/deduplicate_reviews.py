import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TXT_PATH = os.path.join(BASE_DIR, 'data', 'bottega_louie_reviews.txt')

def clean_reviews():
    if not os.path.exists(TXT_PATH):
        print(f"❌ Error: Could not find {TXT_PATH}")
        return

    with open(TXT_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split the text by double newlines to isolate each block of text
    blocks = content.split('\n\n')
    
    seen_fingerprints = set()
    unique_blocks = []
    duplicate_count = 0

    for block in blocks:
        clean_block = block.strip()
        
        # Skip empty blocks or useless Yelp UI artifacts
        if not clean_block or clean_block.lower() == "read more":
            if clean_block.lower() == "read more":
                duplicate_count += 1
            continue
            
        # Create a uniform fingerprint (lowercased, standardized spaces) to catch slight variations
        fingerprint = " ".join(clean_block.lower().split())

        if fingerprint in seen_fingerprints:
            duplicate_count += 1
        else:
            seen_fingerprints.add(fingerprint)
            unique_blocks.append(clean_block)

    # Write the cleaned data back to the file
    with open(TXT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(unique_blocks))

    print(f"✅ Scanning complete.")
    print(f"🧹 Removed {duplicate_count} duplicate blocks (including 'Read more' artifacts and repetitive updates).")
    print(f"📄 Cleaned data saved to {TXT_PATH}.")

if __name__ == "__main__":
    clean_reviews()