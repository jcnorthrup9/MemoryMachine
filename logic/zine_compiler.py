import os

# RELATIVE PATHS FOR PORTABILITY
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
HTML_FILE = os.path.join(BASE_DIR, 'html', 'digitalPalimpsest.html')


def get_data(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return f"[ERROR: {filename} NOT FOUND]"


def compile_zine():
    print("--- Memory Machine: Compiling Portable Zine ---")

    # 1. Fetch live docs
    system_data = get_data('system_manifest.txt')  # Create this for TOC/Diagrams
    abstract = get_data('thesis_abstract.txt')
    narrative = get_data('1988_trailer_parsed.txt')
    json_data = get_data('1988_trailer_logic.json')
    binary = get_data('1988_trailer_binary_strata.txt')

    # 2. Open Template
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    # 3. Injection Logic
    html = html.replace('{{SYSTEM_DATA}}', system_data)
    html = html.replace('{{ABSTRACT_DATA}}', abstract)
    html = html.replace('{{NARRATIVE_DATA}}', narrative)
    html = html.replace('{{JSON_DATA}}', json_data)
    html = html.replace('{{BINARY_DATA}}', binary)

    # 4. Save
    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print("✅ PORTABLE BUILD SUCCESSFUL.")


if __name__ == "__main__":
    compile_zine()