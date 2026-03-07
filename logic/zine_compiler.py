import os

# RELATIVE PATHS
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
HTML_FILE = os.path.join(BASE_DIR, 'html', 'digitalPalimpsest.html')

def get_data(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return f"[MISSING DATA: {filename}]"

def compile_zine():
    print("--- Memory Machine: Compiling Zine ---")
    
    # 1. FETCH DATA
    system_data = get_data('system_manifest.txt')
    abstract = get_data('thesis_abstract.txt')
    narrative = get_data('1988_trailer_parsed.txt')
    json_data = get_data('1988_trailer_logic.json')
    binary = get_data('1988_trailer_binary_strata.txt')

    # 2. SPLIT ABSTRACT (3 parts for Spreads 2 & 3)
    chunk = len(abstract) // 3 + 1
    abs_parts = [abstract[i:i+chunk] for i in range(0, len(abstract), chunk)]
    while len(abs_parts) < 3: abs_parts.append("")

    # 3. READ HTML FILE
    if not os.path.exists(HTML_FILE):
        print(f"❌ Error: Cannot find {HTML_FILE}")
        return
        
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    # 4. PROCESS VIGNETTES
    snippets = narrative.split('---')
    vignette_html = "".join([f'<div class="vignette">{s.strip()}</div>' for s in snippets if s.strip()])

    # 5. INJECTION
    html = html.replace('{{ABSTRACT_1}}', abs_parts[0])
    html = html.replace('{{ABSTRACT_2}}', abs_parts[1])
    html = html.replace('{{ABSTRACT_3}}', abs_parts[2])
    html = html.replace('{{SYSTEM_DATA}}', system_data)
    html = html.replace('{{NARRATIVE_DATA}}', vignette_html)
    html = html.replace('{{JSON_DATA}}', json_data)
    html = html.replace('{{BINARY_DATA}}', binary)

    # 6. SAVE OUTPUT OVER HTML FILE
    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ BUILD SUCCESSFUL. Open digitalPalimpsest.html to view.")

if __name__ == "__main__":
    compile_zine()