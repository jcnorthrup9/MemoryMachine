import rhinoscriptsyntax as rs
import json

# Logic: Array the JSON assets into a visual library
def create_asset_gallery(data_path):
    with open(data_path) as f:
        data = json.load(f)
    
    for i, asset in enumerate(data['public_space_assets']):
        x_offset = i * 20
        # Placeholder Geometry Logic based on Spatial Type
        if asset['spatial_type'] == "Vertical_Kinetic":
            h = asset['parameters']['height_range'][1]
            rs.AddCylinder(rs.pt2cp([x_offset, 0, 0]), h, asset['parameters']['footprint_radius'])
        
        rs.AddTextDot(asset['name'], [x_offset, 0, -2])

# create_asset_gallery('spatial_assets.json')