import os

assets_dir = r"D:\MemoryMachine\assets\precedents"
data_dir = r"D:\MemoryMachine\data"

os.makedirs(data_dir, exist_ok=True)

# Scan the precedents folder
for filename in os.listdir(assets_dir):
    if filename.endswith("_OSM.png"):
        # Extract site name (e.g., "HighLine_OSM.png" -> "HighLine")
        site_name = filename.replace("_OSM.png", "")
        md_path = os.path.join(data_dir, f"{site_name}.md")
        
        # Only create it if it doesn't already exist
        if not os.path.exists(md_path):
            # Add spaces before capital letters for the title (e.g., "HighLine" -> "High Line")
            formatted_name = ''.join([' ' + c if c.isupper() else c for c in site_name]).strip()
            
            content = f"""# SITE PRECEDENT: {formatted_name.upper()}
**Location:** TBD  
**Architect:** TBD  
**Concept:** TBD  

---

## 1. GEOMETRIC LOGIC
- **Feature 1:** Description of the primary geometric and structural logic.
- **Feature 2:** Description of secondary pathways or forms.

## 2. PROGRAMMATIC ZONES
| Zone ID | Label | Description |
| :--- | :--- | :--- |
| **SOFT_01** | Primary Softscape | Description of planting and green space. |
| **HARD_01** | Primary Hardscape | Description of paving, plazas, or structures. |
| **PROG_01** | Active Program | Description of active social nodes. |

## 3. SPATIAL RELATIONSHIPS
1. **The Primary Rule:** Define how the hardscape and softscape interact.
2. **The Edge Rule:** Define how the park interacts with its boundary.
"""
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ Created: {site_name}.md")
        else:
            print(f"⏭️ Skipped: {site_name}.md (Already exists)")