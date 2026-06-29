# Rhino Forensic Trace Plan

This plan details the steps to execute a Python script in Rhino 3D to create the 'FORENSIC_TRACES' layer, draw a rectangle representing a 1988 trailer footprint, and add a labeled entry node.

## Objectives
- Create layer `FORENSIC_TRACES` and set color to Red.
- Draw a 12' x 60' rectangle at `(0,0,0)`.
- Add a point at `(6, 30)` (center of the rectangle).
- Label the point `Entry_Node`.

## Proposed Python Script
```python
import rhinoscriptsyntax as rs

def convert_to_doc_units(value_in_feet):
    # Rhino Unit Systems:
    # 2 = Millimeters, 3 = Centimeters, 4 = Meters
    # 8 = Inches, 9 = Feet
    unit_sys = rs.UnitSystem()
    if unit_sys == 9: # Feet
        return value_in_feet
    elif unit_sys == 8: # Inches
        return value_in_feet * 12.0
    elif unit_sys == 4: # Meters
        return value_in_feet * 0.3048
    elif unit_sys == 2: # Millimeters
        return value_in_feet * 304.8
    else:
        # Fallback to feet if unknown or just return value
        return value_in_feet

def main():
    layer_name = 'FORENSIC_TRACES'
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, [255, 0, 0])
    else:
        rs.LayerColor(layer_name, [255, 0, 0])
    
    rs.CurrentLayer(layer_name)
    
    # 12 feet by 60 feet
    width = convert_to_doc_units(12)
    length = convert_to_doc_units(60)
    
    # Draw rectangle at origin (0,0,0)
    plane = rs.WorldXYPlane()
    rect_id = rs.AddRectangle(plane, width, length)
    
    # Add point at (6, 30) feet
    px = convert_to_doc_units(6)
    py = convert_to_doc_units(30)
    pt_pos = [px, py, 0]
    pt_id = rs.AddPoint(pt_pos)
    
    # Label it: Name the object and add a visible TextDot
    rs.ObjectName(pt_id, "Entry_Node")
    rs.AddTextDot("Entry_Node", pt_pos)
    
    print("Layer 'FORENSIC_TRACES' created/updated.")
    print("Rectangle 12'x60' drawn.")
    print("Point 'Entry_Node' added at (6', 30').")

if __name__ == "__main__":
    main()
```

## Implementation Step
Switch to `Code` mode and use the `execute_rhino_python` tool from the Rhino MCP server with the above script content.
