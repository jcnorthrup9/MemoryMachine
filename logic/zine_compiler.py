import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
HTML_FILE = os.path.join(BASE_DIR, 'html', 'digitalPalimpsest.html')


def get_data(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


def compile_zine():
    print("--- Memory Machine: Compiling Portable Zine ---")

    # FETCH DATA
    system_content = get_data('system_manifest.txt')
    abstract = get_data('thesis_abstract.txt')
    narrative = get_data('1988_trailer_parsed.txt')
    json_data = get_data('1988_trailer_logic.json')
    binary = get_data('1988_trailer_binary_strata.txt')

    # PARSE SYSTEM MANIFEST
    lines = system_content.split('\n')
    toc_start = next(i for i, line in enumerate(lines) if '01 // TABLE OF CONTENTS' in line)
    system_start = next(i for i, line in enumerate(lines) if '02 // SYSTEM PIPELINE LOGIC' in line)
    toc_data = '\n'.join(lines[toc_start:system_start]).strip()
    system_data = '\n'.join(lines[system_start:]).strip()

    # SPLIT ABSTRACT INTO 4 PARTS
    chunk = len(abstract) // 4
    abs_parts = [abstract[i:i + chunk] for i in range(0, len(abstract), chunk)]
    # Ensure we have exactly 4 parts
    while len(abs_parts) < 4: abs_parts.append("")

    # READ TEMPLATE
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    # PROCESS VIGNETTES
    snippets = narrative.split('---')
    vignette_html = "".join([f'<div class="vignette">{s.strip()}</div>' for s in snippets if s.strip()])

    # INJECTION
    html = html.replace('{{TOC_DATA}}', toc_data)
    html = html.replace('{{SYSTEM_DATA}}', system_data)
    html = html.replace('{{ABSTRACT_1}}', abs_parts[0])
    html = html.replace('{{ABSTRACT_2}}', abs_parts[1])
    html = html.replace('{{ABSTRACT_3}}', abs_parts[2])
    html = html.replace('{{ABSTRACT_4}}', abs_parts[3])
    html = html.replace('{{NARRATIVE_DATA}}', vignette_html)
    html = html.replace('{{JSON_DATA}}', json_data)
    html = html.replace('{{BINARY_DATA}}', binary)

    # SAVE
    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ FINAL BUILD SUCCESSFUL.")


if __name__ == "__main__":
    compile_zine()