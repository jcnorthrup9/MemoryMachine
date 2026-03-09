import rhinoscriptsyntax as rs
import System.Drawing

def main():
    # Delete previous geometry on the old layer
    old_layer = 'MEM_MACHINE_BASE'
    if rs.IsLayer(old_layer):
        objs = rs.ObjectsByLayer(old_layer)
        if objs:
            rs.DeleteObjects(objs)
        # Optionally remove the old layer
        # rs.DeleteLayer(old_layer)

    # Create EXTERIOR_SHELL layer (Silver)
    layer_name = 'EXTERIOR_SHELL'
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, color=System.Drawing.Color.Silver)
    rs.CurrentLayer(layer_name)

    # 1. Exterior Rectangle (13.33' x 52')
    # Using feet as units. Origin at (0,0,0)
    length = 52.0
    width = 13.3333 # 13'-4"
    rs.AddRectangle(rs.WorldXYPlane(), length, width)

    # 2. Main Interior Partitions (Referencing trailer_floorPlan.jpg)
    # Master Bedroom Wall (Left side)
    # Master Bedroom is 11'-10" x 10'-4"
    # The wall separating the bedroom from the utility/bath seems to be at X = 11.833'
    bedroom_wall_x = 11.8333
    rs.AddLine([bedroom_wall_x, 0, 0], [bedroom_wall_x, width, 0])

    # Bathroom Wall (Center)
    # Bathroom/Utility area follows the Master Bedroom.
    # Looking at the plan, Bedroom #2 is 9'-4" wide.
    # The Living Room is 12'-0" wide.
    # The Kitchen/Dining area is roughly the remainder.
    # Let's place the Bathroom/Utility right wall (separating from Bedroom #2)
    # Calculation: 52' - 12' (Living Room) - 9.33' (Bed 2) - 1.5' (Kitchen overlap)?
    # Let's use the Master Bedroom (11.83') + Utility/Bath area (approx 10') = 21.83'
    bath_wall_x = 21.8333
    rs.AddLine([bath_wall_x, 0, 0], [bath_wall_x, width, 0])

    # Kitchen Counter / Living Room Boundary
    # Living room is 12'-0" wide. 
    # Entrance is at the far right. 
    # The wall separating Bed #2 from Living Room:
    bed2_wall_x = 31.1666 # 21.83 + 9.33
    rs.AddLine([bed2_wall_x, 0, 0], [bed2_wall_x, width, 0])
    
    # Kitchen counter boundary (far right area)
    # The Kitchen area is marked by a counter that turns.
    # Let's draw the vertical partition that separates Living Room from Kitchen.
    kitchen_wall_x = 43.1666 # 31.16 + 12.0
    rs.AddLine([kitchen_wall_x, 0, 0], [kitchen_wall_x, width, 0])

    print('Refined refined geometry created.')

if __name__ == "__main__":
    main()
