import rhinoscriptsyntax as rs

def reconstruct_pershing_square_base():
    rs.EnableRedraw(False)
    
    # Create Context Layers
    rs.AddLayer("00_SITE::HARDSCAPE", (200, 200, 200))
    rs.AddLayer("00_SITE::ICONIC_GEO", (128, 0, 128))
    rs.AddLayer("00_SITE::SUBTERRANEAN_GARAGE", (60, 60, 60))
    rs.AddLayer("00_SITE::RAMPS", (100, 100, 100))
    
    # 1. Base plaza bounding (approx 330ft x 550ft block)
    plaza = rs.AddBox([[0,0,0], [330,0,0], [330,550,0], [0,550,0], [0,0,-10], [330,0,-10], [330,550,-10], [0,550,-10]])
    rs.ObjectLayer(plaza, "00_SITE::HARDSCAPE")
    
    # 1b. The 3-Story Underground Parking Garage
    garage = rs.AddBox([[10, 10, -10], [320, 10, -10], [320, 540, -10], [10, 540, -10], [10, 10, -45], [320, 10, -45], [320, 540, -45], [10, 540, -45]])
    rs.ObjectLayer(garage, "00_SITE::SUBTERRANEAN_GARAGE")
    
    # 1c. The Entrance Ramps (Olive St & Hill St)
    ramp_west = rs.AddBox([[0, 150, 0], [25, 150, 0], [25, 300, 0], [0, 300, 0], [0, 150, -15], [25, 150, -15], [25, 300, -15], [0, 300, -15]])
    rs.ObjectLayer(ramp_west, "00_SITE::RAMPS")
    ramp_east = rs.AddBox([[305, 250, 0], [330, 250, 0], [330, 400, 0], [305, 400, 0], [305, 250, -15], [330, 250, -15], [330, 400, -15], [305, 400, -15]])
    rs.ObjectLayer(ramp_east, "00_SITE::RAMPS")
    
    # 2. Legorreta's Purple Campanile Tower
    campanile = rs.AddBox([[150, 250, 0], [170, 250, 0], [170, 270, 0], [150, 270, 0], [150, 250, 120], [170, 250, 120], [170, 270, 120], [150, 270, 120]])
    rs.ObjectLayer(campanile, "00_SITE::ICONIC_GEO")
    rs.ObjectColor(campanile, (128, 0, 128))
    
    # 3. Yellow Aqueduct Wall
    wall = rs.AddBox([[160, 270, 0], [165, 270, 0], [165, 400, 0], [160, 400, 0], [160, 270, 25], [165, 270, 25], [165, 400, 25], [160, 400, 25]])
    rs.ObjectLayer(wall, "00_SITE::ICONIC_GEO")
    rs.ObjectColor(wall, (255, 200, 0))
    
    rs.AddTextDot("Pershing Square Current Conditions", [160, 275, 125])
    
    rs.ZoomExtents()
    rs.EnableRedraw(True)
    print("✅ Base conditions for Pershing Square reconstructed. Ready for intervention.")

if __name__ == "__main__":
    reconstruct_pershing_square_base()