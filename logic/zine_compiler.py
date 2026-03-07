import os

# RELATIVE PATHS
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
HTML_FILE = os.path.join(BASE_DIR, 'html', 'digitalPalimpsest.html')

def get_data(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    print(f"⚠️  WARNING: Could not find {filename} in the data folder.")
    return f"[MISSING DATA: {filename}]"

def compile_zine():
    print("\n--- Memory Machine: Compiling & Diagnosing ---")
    
    # 1. FETCH DATA
    system_data = get_data('system_manifest.txt')
    abstract = get_data('thesis_abstract.txt')
    narrative = get_data('1988_trailer_parsed.txt')
    json_data = get_data('1988_trailer_logic.json')
    binary = get_data('1988_trailer_binary_strata.txt')

    # 2. SAFELY SPLIT ABSTRACT (By whole words, not raw characters)
    words = abstract.split()
    if len(words) > 0:
        chunk = len(words) // 3 + 1
        abs_1 = " ".join(words[:chunk])
        abs_2 = " ".join(words[chunk:chunk*2])
        abs_3 = " ".join(words[chunk*2:])
    else:
        abs_1 = abs_2 = abs_3 = ""

    # 3. READ HTML FILE
    if not os.path.exists(HTML_FILE):
        print(f"❌ FATAL ERROR: Cannot find {HTML_FILE}")
        return
        
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    # 4. DIAGNOSTIC CHECK (Tells you what is missing in VS Code terminal)
    print("\n[ TAG CONNECTION CHECK ]")
    tags = ["{{SYSTEM_DATA}}", "{{ABSTRACT_1}}", "{{ABSTRACT_2}}", "{{ABSTRACT_3}}", "{{NARRATIVE_DATA}}", "{{JSON_DATA}}", "{{BINARY_DATA}}"]
    missing_tags = False
    for tag in tags:
        if tag in html:
            print(f"✅ Found: {tag}")
        else:
            print(f"❌ Missing: {tag} (Was the file already compiled?)")
            missing_tags = True
            
    if missing_tags:
        print("\n⚠️  HALTING BUILD: Missing tags detected.")
        print("Please paste the empty HTML template (with the {{TAGS}}) back into digitalPalimpsest.html and try again.\n")
        return

    # 5. PROCESS VIGNETTES
    snippets = narrative.split('---')
    vignette_html = "".join([f'<div class="vignette">{s.strip()}</div>' for s in snippets if s.strip()])

    # 6. INJECTION
    html = html.replace('{{ABSTRACT_1}}', abs_1)
    html = html.replace('{{ABSTRACT_2}}', abs_2)
    html = html.replace('{{ABSTRACT_3}}', abs_3)
    html = html.replace('{{SYSTEM_DATA}}', system_data)
    html = html.replace('{{NARRATIVE_DATA}}', vignette_html)
    html = html.replace('{{JSON_DATA}}', json_data)
    html = html.replace('{{BINARY_DATA}}', binary)

    # 7. SAVE OUTPUT
    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("\n✅ BUILD SUCCESSFUL. Data successfully injected into HTML!\n")

if __name__ == "__main__":
    compile_zine()