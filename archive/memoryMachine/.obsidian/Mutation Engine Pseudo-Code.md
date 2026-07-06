# MEMORY MACHINE: MIDTERM MUTATION ENGINE
# Core Objective: Translate urban pressures and archival data into surface excavations and vertical cassettes.

class MemoryMachineEngine:
    def __init__(self, site_grid, structural_capacity_map):
        self.grid = site_grid                           # 30x30 structural grid of Pershing Square / Garage
        self.structural_limits = structural_capacity_map # Max dead/live loads the garage lid can handle
        self.urban_assets = {}                          # Surrounding architectural data
        self.memory_archive = []                        # Qualitative archival sentiment vectors

    def ingest_urban_context(self, building_heights, hotel_proximity, transit_nodes, foot_traffic):
        """
        Phase 1: Ingest quantitative data vectors from the surrounding urban envelope.
        """
        for cell in self.grid:
            # Calculate solar shadow casting and enclosure index based on building heights
            cell.solar_exposure = calculate_solar_exposure(cell.coords, building_heights)
            
            # Measure programmatic deficits (e.g., high hotel density = high demand for public/food space)
            cell.programmatic_demand = evaluate_asset_pressure(cell.coords, hotel_proximity, transit_nodes)
            
            # Map physical proximity to the underground Metro connection
            cell.metro_proximity = calculate_distance(cell.coords, transit_nodes['Metro_Station'])
            
            # Register current surface conditions (e.g., hardscape concrete vs planters)
            cell.surface_condition = get_surface_material(cell.coords)

    def ingest_memory_archive(self, archival_data):
        """
        Phase 2: Layer qualitative historical narrative onto the physical grid.
        """
        for memory in archival_data:
            # Map narrative events to specific spatial coordinates in the park
            target_cell = self.grid.find_nearest_cell(memory.historical_location)
            # Assign intensity weight based on narrative emotional/historical significance
            target_cell.memory_volatility += memory.intensity_weight

    def evaluate_volumetric_interference(self):
        """
        Phase 3: Cross-reference memory data with urban pressures to find high-intensity zones.
        """
        for cell in self.grid:
            # Combine qualitative memory weights with quantitative programmatic deficits
            cell.intervention_score = (cell.memory_volatility * 0.4) + (cell.programmatic_demand * 0.6)

    def run_excavation_solver(self, threshold_limit):
        """
        Phase 4: Determine exactly where, how deep, and how wide to dig through the surface.
        """
        puncture_zones = []

        for cell in self.grid:
            if cell.intervention_score > threshold_limit:
                # Safety check: Can this specific structural grid zone handle a puncture?
                # (e.g., check proximity to primary garage column lines or heavy shear walls)
                if self.structural_limits.can_be_perforated(cell.coords):
                    
                    # Calculate excavation geometry based on proximity to the underground Metro connection
                    if cell.metro_proximity < 50: # Close to transit
                        puncture_type = "Transit_Daylight_Canyon"
                        depth = "Full_Subterranean_Penetration" # Digs all the way to platform level
                    else:
                        puncture_type = "Infrastructural_Light_Scoop"
                        depth = "Parking_Deck_Intervention"    # Blurs surface with garage levels
                        
                    puncture_zones.append({
                        "coordinates": cell.coords,
                        "type": puncture_type,
                        "depth": depth,
                        "area": calculate_puncture_boundary(cell.intervention_score)
                    })
        return puncture_zones

    def deploy_vertical_cassettes(self, puncture_zones):
        """
        Phase 5: Turn the modular cassette system vertically, anchoring surface to subsurface.
        """
        architectural_outputs = []

        for zone in puncture_zones:
            # Generate a custom 3D vertical casing/liner based on the puncture type
            cassette_geometry = generate_vertical_profile(zone["coordinates"], zone["area"], zone["depth"])
            
            # Program the cassette according to the local deficit (e.g., micro-food kiosks, sunken theater, garden)
            cassette_program = assign_program(zone["type"])
            
            architectural_outputs.append({
                "geometry": cassette_geometry,
                "program": cassette_program,
                "structural_tie_in": "Anchor_to_1951_Garage_Floor"
            })
        return architectural_outputs

# EXECUTION PIPELINE EXAMPLE
# engine = MemoryMachineEngine(pershing_square_grid, garage_structural_blueprint)
# engine.ingest_urban_context(heights_data, hotel_data, metro_data, traffic_data)
# engine.ingest_memory_archive(pershing_historical_logs)
# engine.evaluate_volumetric_interference()
# excavations = engine.run_excavation_solver(threshold_limit=0.75)
# midterm_design_proposal = engine.deploy_vertical_cassettes(excavations)