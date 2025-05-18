import pandas as pd
import folium
from folium.plugins import TimestampedGeoJson
from branca.element import MacroElement
from jinja2 import Template
import xml.etree.ElementTree as ET
import zipfile
import os
import itertools

# Define file paths for the folder with GPS CSVs and the KMZ with building markers
folder_path = 'data/raw/documents-export-2025-04-08'
kmz_path = 'data/raw/Building Labels.kmz'

# Initialize the folium map
m = folium.Map(location=[52.52, 13.405], zoom_start=18)  # Temporary location; will update later

# Get list of all CSV files in the specified folder
csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]

# Define a color palette and create a cycling iterator for consistent color assignment
color_palette = [
    'blue', 'red', 'green', 'orange', 'purple', 'pink',
    'brown', 'black', 'cyan', 'magenta'
]
color_cycle = itertools.cycle(color_palette)

first_point = None  # to set map center
legend_items = []   # to store legend entries

# Process each CSV file
for csv_file in csv_files:
    color = next(color_cycle)
    legend_items.append((csv_file, color))

    # Read CSV file into DataFrame
    df = pd.read_csv(os.path.join(folder_path, csv_file))

    # Drop rows missing critical columns
    df = df.dropna(subset=['latitude', 'longitude', 'synced_time'])
    # Convert synced_time to datetime, drop invalid entries
    df['synced_time'] = pd.to_datetime(df['synced_time'], errors='coerce')
    df = df.dropna(subset=['synced_time'])
    # Sort the data by timestamp
    df = df.sort_values(by='synced_time')
    # Format time strings for animation
    df['time_str'] = df['synced_time'].dt.strftime('%Y-%m-%dT%H:%M:%S')

    if df.empty:
        continue  # Skip empty or invalid files

    # Save first point to center map
    if not first_point:
        first_point = [df.iloc[0]['latitude'], df.iloc[0]['longitude']]
        m.location = first_point

    # Build GeoJSON features for animation
    features = []
    for _, row in df.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row['longitude'], row['latitude']],
            },
            "properties": {
                "time": row['time_str'],
                "popup": f"{csv_file} @ {row['time_str']}",
                "style": {
                    "color": color
                },
                "icon": "circle",
                "iconstyle": {
                    "fillColor": color,
                    "fillOpacity": 0.6,
                    "stroke": "true",
                    "radius": 6
                },
                "duration": 3000 # Duration for point visibility in ms
            }
        })

    # Construct a GeoJSON FeatureCollection
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    # Add animated timestamped GeoJSON layer to the map
    TimestampedGeoJson(
        data=geojson,
        period='PT1S', # One point per second
        transition_time=1500,  # Animation transition time
        loop=False,  # Do not loop the animation
        auto_play=True, # Start animation automatically
        add_last_point=True # Show final point
    ).add_to(m)

#  Create HTML for a floating legend box with colors and filenames
from branca.element import Element

legend_html = f"""
<div style="
    position: fixed;
    top: 50px;
    left: 50px;
    z-index: 9999;
    background-color: white;
    border: 2px solid gray;
    border-radius: 5px;
    padding: 10px;
    font-size: 13px;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
    max-height: 300px;
    overflow-y: auto;
">
<b>Legend</b><br>
{''.join([
    f'<div style="margin:4px 0;"><span style="display:inline-block; width:12px; height:12px; background:{color}; margin-right:6px; border:1px solid #000;"></span>{name}</div>'
    for name, color in legend_items
])}
</div>
"""
# Add the legend HTML to the map
m.get_root().html.add_child(Element(legend_html))


# Extract the KML file from the KMZ archive
kml_file = None
with zipfile.ZipFile(kmz_path, 'r') as z:
    for name in z.namelist():
        if name.endswith('.kml'):
            kml_file = name
            z.extract(name, ".")
            break # Only handle the first KML found

if kml_file:
    # Define KML namespace and parse the XML
    namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}
    tree = ET.parse(kml_file)
    root = tree.getroot()

    # Find and add all Placemark points (buildings, etc.)
    for placemark in root.findall('.//kml:Placemark', namespaces):
        name = placemark.find('kml:name', namespaces)
        coord_elem = placemark.find('.//kml:Point/kml:coordinates', namespaces)
        if coord_elem is not None:
            coords = coord_elem.text.strip()
            lon, lat, *_ = map(float, coords.split(','))
            folium.CircleMarker(
                location=[lat, lon],
                radius=3,
                tooltip=name.text if name is not None else '',
                color="gray",
                fill=True,
                fill_color="gray",
                fill_opacity=0.4,
                weight=0.5
            ).add_to(m)

# Export the map as an HTML file that can be opened in any browser
m.save('gps_movement_colored_by_file.html')
print("Saved: gps_movement_colored_by_file.html")
