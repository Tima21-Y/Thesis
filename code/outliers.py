"""
Fixation Distance Outlier Detection and Image Annotation

This script:
1. Extracts geolocation data for labeled buildings from a KMZ file.
2. Loads GPS and fixation data for multiple exploratory trials.
3. Computes the distance (in meters) between the participant's position and the fixated building at each fixation.
4. Identifies statistical outliers based on fixation distances using the IQR method.
5. Retrieves image frames corresponding to outlier fixations.
6. Annotates those images with building name, house number, and distance.
7. Saves the annotated images to a folder.

Dependencies: pandas, geopy, matplotlib, Pillow, xml.etree.ElementTree, zipfile
"""

import os
import re
import zipfile
import pandas as pd
from geopy.distance import geodesic
import xml.etree.ElementTree as ET
import matplotlib
from PIL import Image, ImageDraw, ImageFont

# Set backend to open plot windows outside of PyCharm (optional)
matplotlib.use('TkAgg')



# Directory and File Paths
gps_dir = 'thesis/data/raw/documents-export-2025-04-08'
fix_dir = 'thesis/data/raw/final_labeling_data_frame_nr_NOT_sorted'
kmz_path = 'thesis/data/raw/Building Labels.kmz'
image_path = "thesis/data/raw/frame_images"

# Step 1: Extract Coordinates of Houses from KMZ (KML inside)
house_coords = {}
kml_file = None
#Unzip KMZ and extract the KML file
with zipfile.ZipFile(kmz_path, 'r') as z:
    for name in z.namelist():
        if name.endswith('.kml'):
            kml_file = name
            z.extract(name, ".")
            break

# Parse KML and extract coordinates
if kml_file:
    namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}
    tree = ET.parse(kml_file)
    root = tree.getroot()
    # Iterate through each building (Placemark) to extract its name and GPS coordinates
    for placemark in root.findall('.//kml:Placemark', namespaces):
        name_elem = placemark.find('kml:name', namespaces)
        coord_elem = placemark.find('.//kml:Point/kml:coordinates', namespaces)
        if name_elem is not None and coord_elem is not None:
            name_text = name_elem.text.strip()
            match = re.match(r'Punkt\s*(\d+)', name_text, re.IGNORECASE)
            if match:
                house_id = int(match.group(1))
                coords = coord_elem.text.strip()
                lon, lat, *_ = map(float, coords.split(','))
                house_coords[house_id] = (lat, lon, name_text)

#  Step 2: Process All Fixation and GPS File Pairs
all_results = []

# Iterate through Explorations (1–5) and Eye Tracker (ET) sessions (1–3)
for expl in range(1, 6):          # Expl_1 to Expl_5
    for et in range(1, 4):        # ET_1 to ET_3
        gps_filename = f"cleaned-interpol-Expl_{expl}_ET_{et}.csv"
        fix_filename = f"fixation_GPS_Expl_{expl}_ET_{et}_labelled.xlsx"

        gps_path = os.path.join(gps_dir, gps_filename)
        fix_path = os.path.join(fix_dir, fix_filename)
        # Skip files that don't exist
        if not (os.path.exists(gps_path) and os.path.exists(fix_path)):
            print(f"Skipping pair: {gps_filename} and {fix_filename}")
            continue

        print(f"Processing: {gps_filename} and {fix_filename}")
        #  Load and prepare GPS data
        gps_df = pd.read_csv(gps_path)
        gps_df['synced_time'] = pd.to_datetime(gps_df['synced_time'], errors='coerce')
        gps_df = gps_df.dropna(subset=['latitude', 'longitude', 'synced_time']).sort_values(by='synced_time')
        #Load and prepare fixation data
        fix_df = pd.read_excel(fix_path)
        fix_df['start_timestamp_ns'] = pd.to_datetime(fix_df['start_timestamp_ns'], unit='ns', errors='coerce')
        fix_df = fix_df.dropna(subset=['start_timestamp_ns'])
        # Only keep fixations that refer to valid house numbers
        fix_df = fix_df[(fix_df['house_nr'] != 0) & (fix_df['house_nr'].isin(house_coords.keys()))]


        # Match fixation to building and compute distance
        def find_closest_position(ts):
            idx = (gps_df['synced_time'] - ts).abs().idxmin()
            return gps_df.loc[idx, ['latitude', 'longitude']]

        for _, row in fix_df.iterrows():
            fixation_time = row['start_timestamp_ns']
            house_id = row['house_nr']
            if house_id in house_coords:
                target_lat, target_lon, building_name = house_coords[house_id]
                person_coords = find_closest_position(fixation_time)
                # Compute geodesic distance (in meters) between person and target house
                distance_m = geodesic(
                    (person_coords['latitude'], person_coords['longitude']),
                    (target_lat, target_lon)
                ).meters
                # Append all relevant info for this fixation
                all_results.append({
                    'expl': expl,
                    'et': et,
                    'house_nr': house_id,
                    'building_name': building_name,
                    'fixation_time': fixation_time,
                    'person_position': (person_coords['latitude'], person_coords['longitude']),
                    'target_position': (target_lat, target_lon),
                    'distance_m': distance_m,
                    'frame_nr': row.get('frame_nr'),
                    'session': row.get('session')
                })

# Step 3: Create DataFrame from All Fixation Distances
distance_df = pd.DataFrame(all_results)

#  Step 4: Identify Outliers Using IQR
# IQR = Q3 - Q1; Outliers are defined as values outside Q1 - 1.5*IQR or Q3 + 1.5*IQR
Q1 = distance_df['distance_m'].quantile(0.25)
Q3 = distance_df['distance_m'].quantile(0.75)
IQR = Q3 - Q1
# Extract rows with distances outside of the IQR threshold
outlier_df = distance_df[(distance_df['distance_m'] < Q1 - 1.5 * IQR) | (distance_df['distance_m'] > Q3 + 1.5 * IQR)]

print(f"\nIdentified {len(outlier_df)} outlier fixations based on distance.")
print(outlier_df[['building_name', 'distance_m', 'frame_nr', 'session']].head())

# Step 5: Annotate and Save Image Frames for Outliers
def plot_outlier_images(outlier_df, image_path):
    """
        Annotates image frames corresponding to outlier fixation distances with:
        - House number
        - Building name
        - Distance in meters

        Saves the annotated images into a local folder named 'outlier_frames_annotated'.
        """
    output_dir = "outlier_frames_annotated"
    os.makedirs(output_dir, exist_ok=True)

    for i, (_, row) in enumerate(outlier_df.iterrows()):
        session = str(row['session'])[:11]
        frame = int(row['frame_nr'])
        building = row['building_name']
        distance = row['distance_m']
        # Construct image path
        image_file = os.path.join(image_path, session, f"gaze_plot_frame_{frame}.jpg")

        try:
            # Open and prepare image
            img = Image.open(image_file).convert("RGB")
            draw = ImageDraw.Draw(img)

            # Set up font
            try:
                from PIL import ImageFont
                font = ImageFont.truetype("Arial.ttf", size=24)
            except:
                font = None  # Use default if Arial is not found

            house_nr = int(row['house_nr'])
            # Create annotation text
            text = f"House {house_nr} - {building} - {distance:.1f} m"

            draw.text((20, 20), text, fill="yellow", font=font)

            # Save the image
            save_path = os.path.join(output_dir, f"{session}_frame_{frame}_{building.replace(' ', '_')}.jpg")
            img.save(save_path)
            print(f"Saved: {save_path}")

        except FileNotFoundError:
            print(f"Image not found: {image_file}")
# Call function to process and save annotated outlier frames
plot_outlier_images(outlier_df, image_path)
