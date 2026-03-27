import os
import datetime
import shutil
import sys

# =======================================================================
# ⚙️ CONFIGURATION
# Change this path to the actual location of your Obsidian Vault!
# For example: r"C:\Users\jcnor\Documents\Obsidian Vault"
# =======================================================================
OBSIDIAN_VAULT_DIR = r"C:\SCI_Arc\SP26\Obsidian\SP26" 

LOG_FOLDER_NAME = "dailyNotes"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def send_to_obsidian(source_file="WEEKLY_UPDATE.md"):
    source_path = os.path.join(BASE_DIR, source_file)
    
    if not os.path.exists(source_path):
        print(f"❌ Error: Could not find {source_file} in {BASE_DIR}")
        return

    # Create the target directory inside Obsidian if it doesn't exist
    target_dir = os.path.join(OBSIDIAN_VAULT_DIR, LOG_FOLDER_NAME)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        print(f"❌ Error creating folder in Obsidian Vault. Is the path correct?\nPath: {OBSIDIAN_VAULT_DIR}\nError: {e}")
        return

    # Generate a filename based on today's date
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    target_filename = f"{today_str}_MemoryMachine_Log.md"
    target_path = os.path.join(target_dir, target_filename)

    # Read the current update
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Append it to today's log in Obsidian (creates it if it doesn't exist)
    with open(target_path, 'a', encoding='utf-8') as f:
        f.write(f"\n\n---\n## Log Entry: {datetime.datetime.now().strftime('%I:%M %p')}\n\n")
        f.write(content)
        f.write("\n")

    print(f"✅ Successfully sent log to Obsidian: {target_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        send_to_obsidian(sys.argv[1])
    else:
        send_to_obsidian("WEEKLY_UPDATE.md")