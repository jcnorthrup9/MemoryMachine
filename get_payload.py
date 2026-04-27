import requests
import json
import os

url = "http://localhost:8001/api/compile-blender-payload"

# Auto-detect the newest remixed SVG to prevent loading the 7-million line old one
site_name = "memory_machine_svg-color_1775605304222" # Fallback
remixed_dir = os.path.join("archive", "diagrams", "remixed_svgs")

if os.path.exists(remixed_dir):
    svg_files = [f for f in os.listdir(remixed_dir) if f.endswith('.svg')]
    if svg_files:
        # Grab the first available remixed SVG
        site_name = os.path.splitext(svg_files[0])[0]

# The directive we are sending to our Blender Memory Machine branch
payload_data = {
    "prompt": "Test generation mapping colors and layers to 3D meshes.",
    "site_name": site_name 
}

print("Fetching data from Memory Machine...")
try:
    response = requests.post(url, json=payload_data)

    if response.status_code == 200:
        with open("blender_handoff.json", "w") as f:
            json.dump(response.json(), f, indent=4)
        print("✅ Success! Payload saved to 'blender_handoff.json'")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
except requests.exceptions.ConnectionError:
    print("❌ Error: Could not connect to the server. Make sure 'python app_blender.py' is running in another terminal!")