import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(BASE_DIR, 'html', 'digitalPalimpsest.html')
BACKUP_PATH = os.path.join(BASE_DIR, 'archive', 'digitalPalimpsest_1988_trailer.html')

def backup():
    if os.path.exists(HTML_PATH):
        shutil.copy2(HTML_PATH, BACKUP_PATH)
        print(f"✅ BACKUP SUCCESSFUL: Saved to {BACKUP_PATH}")
    else:
        print("❌ No HTML file found to backup.")

if __name__ == "__main__":
    backup()