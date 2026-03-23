import cv2
import numpy as np
import os
import csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMAGE_PATH = os.path.join(DATA_DIR, 'pershing_satellite.jpg')
OUTPUT_CSV = os.path.join(DATA_DIR, 'extracted_trees.csv')

def extract_trees_from_satellite():
    if not os.path.exists(IMAGE_PATH):
        print(f"⚠️ No satellite image found at {IMAGE_PATH}.")
        print("Generating a simulated satellite map for testing...")
        img = np.zeros((1100, 660, 3), dtype=np.uint8)
        img[:] = (50, 50, 50) # Concrete grey background
        # Draw simulated green tree clusters
        cv2.circle(img, (150, 200), 20, (0, 100, 0), -1)
        cv2.circle(img, (180, 240), 25, (0, 120, 0), -1)
        cv2.circle(img, (100, 300), 18, (0, 90, 0), -1)
        cv2.circle(img, (400, 800), 30, (0, 150, 0), -1)
        cv2.imwrite(IMAGE_PATH, img)
        
    print(f"🔎 Scanning satellite image: {IMAGE_PATH}")
    img = cv2.imread(IMAGE_PATH)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Define color range for vegetation/trees (Green hues)
    lower_green = np.array([25, 40, 40])
    upper_green = np.array([85, 255, 255])

    # Isolate the green pixels
    mask = cv2.inRange(hsv, lower_green, upper_green)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Map pixel dimensions to our Rhino site dimensions (330x550 ft)
    img_h, img_w = img.shape[:2]
    site_width_ft, site_height_ft = 330.0, 550.0

    trees = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 20:  # Filter out noise/small pixels
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                # Pixel Centroid
                cX, cY = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                # Translate to Rhino Space (Invert Y axis)
                rhino_x = (cX / img_w) * site_width_ft
                rhino_y = ((img_h - cY) / img_h) * site_height_ft
                radius = (np.sqrt(area) / img_w) * site_width_ft
                trees.append({'X': round(rhino_x, 2), 'Y': round(rhino_y, 2), 'Radius': round(radius, 2)})
                
                # Draw the AI's detection on the image for our records (Red circle & label)
                cv2.circle(img, (cX, cY), int(np.sqrt(area)), (0, 0, 255), 2)
                cv2.putText(img, "TREE", (cX - 15, cY - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    # Save the analyzed screenshot
    analysis_path = os.path.join(DATA_DIR, 'pershing_satellite_analyzed.jpg')
    cv2.imwrite(analysis_path, img)

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['X', 'Y', 'Radius'])
        writer.writeheader()
        writer.writerows(trees)

    print(f"✅ Successfully extracted {len(trees)} organic assets via Computer Vision.")
    print(f"📸 Saved AI vision overlay to {analysis_path}")
    print(f"📄 Saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    extract_trees_from_satellite()