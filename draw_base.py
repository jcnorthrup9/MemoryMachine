import rhinoscriptsyntax as rs

def main():
    # Set layer name
    layer_name = 'MEM_MACHINE_BASE'
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name)
    rs.CurrentLayer(layer_name)

    # Exterior Boundary Dimensions: 52'-0" x 13'-4"
    # Assuming feet as units for the geometry
    length = 52.0
    width = 13.3333 # 13 + 4/12

    # Define corners
    p1 = [0, 0, 0]
    p2 = [length, 0, 0]
    p3 = [length, width, 0]
    p4 = [0, width, 0]

    # Draw exterior boundary
    rs.AddPolyline([p1, p2, p3, p4, p1])

    # Draw main longitudinal interior wall
    # Based on the plan, there's a wall running length-wise (horizontally in the image)
    # The Living Room is 12'-8" in one dimension. 13'4" - 12'8" = 8" wall/gap? 
    # Actually, looking at the dimensions: "12'-0\" X 12'-8\"" for the living room.
    # If the total width is 13'4", a 12'8" room suggests a wall at 12'8" from one side.
    # The longitudinal wall separates the bedrooms/living room from the top edge (Utility/Kitchen/Bath area).
    # Let's place it at 12.666 feet (12'8") from the bottom edge.
    
    wall_y = 12.6666
    wall_start = [0, wall_y, 0]
    wall_end = [length, wall_y, 0]
    rs.AddLine(wall_start, wall_end)

    print('Geometry created successfully.')

if __name__ == "__main__":
    main()
