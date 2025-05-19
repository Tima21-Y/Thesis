"""
Script to Analyze Eye Fixation Distances Relative to Building Coordinates

This script processes eye-tracking fixation data and interpolated GPS data
to compute the distance between the viewer and buildings they were fixating on.
The building coordinates are extracted from a KMZ (KML-compressed) file.

Main Functions:
> Parse KMZ to extract coordinates of buildings.
> Align timestamps of GPS and fixation data.
> Calculate geodesic distances between fixation locations and building coordinates.
> Visualize distributions of fixation distances and building fixation frequency.

Dependencies:
> pandas
> numpy
> matplotlib
> seaborn
> geopy
> xml.etree.ElementTree (standard lib)
> zipfile (standard lib)
> re (standard lib)
> os (standard lib)
"""

import pandas as pd
from geopy.distance import geodesic
import zipfile
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import re
import numpy as np
import os
import seaborn as sns

# Paths
gps_dir = 'thesis/data/raw/documents-export-2025-04-08'
fix_dir = 'thesis/data/raw/final_labeling_data_frame_nr_NOT_sorted'
kmz_path = 'thesis/data/raw/Building Labels (2).kmz'

#  Extract KML from KMZ
house_coords = {}  # house_id -> (lat, lon, name)
kml_file = None
with zipfile.ZipFile(kmz_path, 'r') as z:
    for name in z.namelist():
        if name.endswith('.kml'):
            kml_file = name
            z.extract(name, ".")
            break
# Parse extracted KML file to populate `house_coords`
if kml_file:
    namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}
    tree = ET.parse(kml_file)
    root = tree.getroot()
    # Look for Placemark elements that contain coordinates and names
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

#  Process all matching file pairs
all_results = []

for expl in range(1, 6):          # Expl_1 to Expl_5
    for et in range(1, 3 + 1):    # ET_1 to ET_3
        gps_filename = f"cleaned-interpol-Expl_{expl}_ET_{et}.csv"
        fix_filename = f"fixation_GPS_Expl_{expl}_ET_{et}_labelled.xlsx"

        gps_path = os.path.join(gps_dir, gps_filename)
        fix_path = os.path.join(fix_dir, fix_filename)

        if not (os.path.exists(gps_path) and os.path.exists(fix_path)):
            print(f"Skipping pair: {gps_filename} and {fix_filename}")
            continue

        print(f"Processing: {gps_filename} and {fix_filename}")

        # Load GPS
        gps_df = pd.read_csv(gps_path)
        gps_df['synced_time'] = pd.to_datetime(gps_df['synced_time'], errors='coerce')
        gps_df = gps_df.dropna(subset=['latitude', 'longitude', 'synced_time']).sort_values(by='synced_time')

        # Load Fixation
        fix_df = pd.read_excel(fix_path)
        fix_df['start_timestamp_ns'] = pd.to_datetime(fix_df['start_timestamp_ns'], unit='ns', errors='coerce')
        fix_df = fix_df.dropna(subset=['start_timestamp_ns'])
        fix_df = fix_df[(fix_df['house_nr'] != 0) & (fix_df['house_nr'].isin(house_coords.keys()))]

        # Helper to find nearest GPS point in time
        def find_closest_position(ts):
            idx = (gps_df['synced_time'] - ts).abs().idxmin()
            return gps_df.loc[idx, ['latitude', 'longitude']]

        # Calculate distances
        for _, row in fix_df.iterrows():
            fixation_time = row['start_timestamp_ns']
            house_id = row['house_nr']
            if house_id in house_coords:
                target_lat, target_lon, building_name = house_coords[house_id]
                person_coords = find_closest_position(fixation_time)
                distance_m = geodesic(
                    (person_coords['latitude'], person_coords['longitude']),
                    (target_lat, target_lon)
                ).meters
                all_results.append({
                    'expl': expl,
                    'et': et,
                    'house_nr': house_id,
                    'building_name': building_name,
                    'fixation_time': fixation_time,
                    'person_position': (person_coords['latitude'], person_coords['longitude']),
                    'target_position': (target_lat, target_lon),
                    'distance_m': distance_m
                })

#  Combine into DataFrame
distance_df = pd.DataFrame(all_results)

#  Visualization: Histogram of All Distances
plt.figure(figsize=(10, 6))
plt.hist(distance_df['distance_m'], bins=np.arange(0, 105, 5), color='coral', edgecolor='black')
plt.xticks(np.arange(0, 105, 5))
plt.xlim(0, 100)
plt.title('Distribution of Fixation Distances (All Files)')
plt.xlabel('Distance to Fixated Object (meters)')
plt.ylabel('Number of Fixations')
plt.tight_layout()
plt.show()

#  Visualization: Top 10 Most Fixated Buildings
plt.figure(figsize=(10, 6))
top_buildings = distance_df['building_name'].value_counts().head(10)
sns.barplot(x=top_buildings.values, y=top_buildings.index, palette='viridis')
plt.title('Top 10 Most Fixated Buildings')
plt.xlabel('Number of Fixations')
plt.ylabel('Building')
plt.tight_layout()
plt.show()

#  Visualization: Average Fixation Distance per Building (Top 15)
avg_distance = distance_df.groupby('building_name')['distance_m'].mean().sort_values()
plt.figure(figsize=(10, 6))
avg_distance.head(15).plot(kind='barh', color='teal', edgecolor='black')
plt.title('Average Fixation Distance per Building (Top 15)')
plt.xlabel('Average Distance (meters)')
plt.ylabel('Building')
plt.tight_layout()
plt.show()

#  Print table of fixation counts per building
fixation_counts = distance_df['building_name'].value_counts()
print("Fixation counts per building:")
print(fixation_counts)


# Visualization 4: Distance Distributions by Exploration
explorations = sorted(distance_df['expl'].unique())
for expl in explorations:
    plt.figure(figsize=(8, 4))
    subset = distance_df[distance_df['expl'] == expl]
    plt.hist(subset['distance_m'], bins=np.arange(0, 105, 5), color='skyblue', edgecolor='black')
    plt.title(f'Distance Distribution - Exploration {expl}')
    plt.xlabel('Distance (meters)')
    plt.ylabel('Number of Fixations')
    plt.tight_layout()
    plt.show()
