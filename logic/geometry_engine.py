import math

MATERIAL_COLORS = {
    "concrete": "#6b6460", "water": "#1a5f7a", "steel": "#8a8a9a",
    "glass": "#a8d8ea",    "wood": "#7a5535",  "vegetation": "#3a6535",
    "stone": "#7a7060",    "weathered_steel": "#7a5a45",
}

def build_geometries(spatial_params):
    """Translate AI spatial parameters into a list of Three.js geometry descriptors."""
    if not spatial_params:
        return []

    geo_type = spatial_params.get("geometry_type", "")
    footprint = spatial_params.get("footprint_m", {})
    width     = float(footprint.get("width", 10) if isinstance(footprint, dict) else 10)
    depth     = float(footprint.get("depth", 10) if isinstance(footprint, dict) else 10)
    height    = float(spatial_params.get("height_m", 5))

    # Normalise to preview scale — cap at 12 units radius so nothing dominates the scene
    MAX_RADIUS = 12.0
    raw_radius = width / 2.0
    scale      = min(1.0, MAX_RADIUS / raw_radius) if raw_radius > 0 else 1.0
    radius     = raw_radius * scale
    height     = height * scale
    depth      = depth  * scale

    materials = spatial_params.get("materials", [])
    primary   = next((MATERIAL_COLORS[m] for m in materials if m in MATERIAL_COLORS), "#666666")
    water_col = MATERIAL_COLORS["water"]
    green_col = MATERIAL_COLORS["vegetation"]

    geos = []

    def cyl(r, h, px=0, py=None, pz=0, color=None):
        geos.append({
            "type": "cylinder",
            "args": [r, r, h],
            "position": [px, (h / 2) if py is None else py, pz],
            "color": color or primary,
        })

    def box(w, h, d, px=0, py=None, pz=0, color=None):
        geos.append({
            "type": "box",
            "args": [w, h, d],
            "position": [px, (h / 2) if py is None else py, pz],
            "color": color or primary,
        })

    def sphere(r, px=0, py=0, pz=0, color=None):
        geos.append({
            "type": "sphere",
            "args": [r],
            "position": [px, py, pz],
            "color": color or green_col,
        })

    if geo_type == "pavilion_with_water":
        col_count = int(spatial_params.get("column_count", 8))
        col_h     = float(spatial_params.get("column_height_m", height * 0.75))
        col_r     = max(0.2, radius * 0.06)
        pool_r    = float(spatial_params.get("pool_width_m", radius * 1.1)) / 2
        pool_d    = float(spatial_params.get("pool_depth_m", 0.3))
        cyl(pool_r, pool_d, color=water_col)
        cyl(radius * 1.05, height * 0.05, color="#454540")
        for i in range(col_count):
            a = i * (2 * math.pi / col_count)
            cyl(col_r, col_h, radius * 0.8 * math.sin(a), None, radius * 0.8 * math.cos(a), color=primary)
        cyl(radius * 1.2, height * 0.1, py=col_h + height * 0.05, color="#363630")

    elif geo_type == "shade_canopy":
        col_count = int(spatial_params.get("column_count", 6))
        col_h     = float(spatial_params.get("column_height_m", height * 0.9))
        col_r     = max(0.15, radius * 0.05)
        for i in range(col_count):
            a = i * (2 * math.pi / col_count)
            cyl(col_r, col_h, radius * 0.85 * math.sin(a), None, radius * 0.85 * math.cos(a))
        cyl(radius * 1.1, height * 0.06, py=col_h + height * 0.03, color="#303030")

    elif geo_type == "water_garden":
        cyl(radius, height * 0.05, color="#454540")
        cyl(radius * 0.85, height * 0.07, color=water_col)
        mound_r = radius * 0.35
        sphere(mound_r, py=height * 0.07 + mound_r * 0.6)   # sits on top of pool rim
        cyl(radius * 0.1, height * 0.28, py=height * 0.14, color=primary)

    elif geo_type == "acoustic_screen":
        screen_h = float(spatial_params.get("screen_height_m", height))
        screen_l = float(spatial_params.get("screen_length_m", width))
        fin_count = max(3, int(screen_l / 2))
        fin_w = screen_l / (fin_count * 1.5)
        fin_d = max(0.2, fin_w * 0.35)
        for i in range(fin_count):
            fx = -screen_l / 2 + i * (screen_l / fin_count) + fin_w / 2
            box(fin_w, screen_h, fin_d, px=fx)

    elif geo_type == "memory_tower":
        cyl(radius,        height * 0.08,  color="#404040")
        cyl(radius * 0.35, height * 0.75,  py=height * 0.08 + height * 0.375, color=primary)
        cyl(radius * 0.55, height * 0.10,  py=height * 0.83 + height * 0.05,  color="#606060")
        cyl(radius * 0.06, height * 0.28,  py=height * 0.93 + height * 0.14,  color="#888888")

    elif geo_type == "landscape_mound":
        # Stacked flat discs — low earthwork mound, not a tower
        layers = 6
        for i in range(layers):
            frac    = 1.0 - i * (0.75 / layers)
            disc_h  = max(0.3, height * 0.18)
            cyl(radius * frac, disc_h, py=i * disc_h * 0.7, color=green_col)

    elif geo_type == "amphitheater":
        # Stepped concentric tiers — auditorium / bowl seating form
        tiers    = min(int(spatial_params.get("tiers", 6)), 10)
        tier_h   = max(0.4, height / tiers)
        stage_r  = radius * 0.25
        # Stage floor at centre
        cyl(stage_r, tier_h * 0.4, color="#303028")
        # Seating tiers radiating outward and upward
        for i in range(tiers):
            inner_r = stage_r + i * ((radius - stage_r) / tiers)
            outer_r = stage_r + (i + 1) * ((radius - stage_r) / tiers)
            seat_w  = outer_r - inner_r
            mid_r   = (inner_r + outer_r) / 2
            # Use a box ring approximated by 12 short arc-segments
            seg     = 12
            for s in range(seg):
                a0 = s * (2 * math.pi / seg)
                px = mid_r * math.sin(a0)
                pz = mid_r * math.cos(a0)
                box(seat_w * 0.92, tier_h, seat_w * 0.92,
                    px=px, py=i * tier_h + tier_h / 2, pz=pz, color=primary)

    elif geo_type == "supertree":
        # Gardens by the Bay supertree: tapering trunk + crown disc + hanging fronds
        trunk_r_base = max(0.4, radius * 0.25)
        trunk_r_top  = max(0.15, radius * 0.08)
        trunk_h      = height * 0.80
        crown_r      = radius
        crown_h      = height * 0.12

        # Trunk — tapered as stacked cylinders
        taper_steps = 6
        for i in range(taper_steps):
            frac   = i / taper_steps
            seg_r  = trunk_r_base + frac * (trunk_r_top - trunk_r_base)
            seg_h  = trunk_h / taper_steps
            cyl(seg_r, seg_h, py=i * seg_h + seg_h / 2, color=primary)

        # Crown disc (living canopy)
        cyl(crown_r, crown_h, py=trunk_h + crown_h / 2, color=green_col)

        # Radial frond spokes hanging from crown edge
        spoke_count = 10
        frond_l = crown_r * 0.55
        frond_r = max(0.05, crown_r * 0.04)
        for i in range(spoke_count):
            a   = i * (2 * math.pi / spoke_count)
            sx  = (crown_r * 0.72) * math.sin(a)
            sz  = (crown_r * 0.72) * math.cos(a)
            cyl(frond_r, frond_l,
                px=sx, py=trunk_h - frond_l * 0.5, pz=sz, color=green_col)

        # Skybridge walkway at crown level (flat horizontal ring approximated by 16 boxes)
        bridge_r = crown_r * 0.6
        bridge_w = crown_r * 0.08
        seg = 16
        for i in range(seg):
            a  = i * (2 * math.pi / seg)
            bx = bridge_r * math.sin(a)
            bz = bridge_r * math.cos(a)
            box(bridge_w, bridge_w * 0.5, bridge_w,
                px=bx, py=trunk_h, pz=bz, color="#404038")

    elif geo_type == "kinetic_mast":
        # Schouwburgplein hydraulic lighting mast: tall pole + rotating boom + lamp head
        mast_r      = max(0.12, radius * 0.10)
        mast_h      = height
        boom_l      = radius * 1.4
        boom_r      = max(0.06, mast_r * 0.5)
        lamp_r      = max(0.18, radius * 0.22)
        lamp_h      = height * 0.10
        base_r      = radius * 0.35
        base_h      = height * 0.04
        pivot_h     = mast_h * 0.92   # where the boom pivots

        # Ground base plate
        cyl(base_r, base_h, color="#303030")

        # Vertical mast
        cyl(mast_r, mast_h, py=base_h + mast_h / 2, color=primary)

        # Counter-weight box below pivot
        cw_l = boom_l * 0.28
        box(cw_l * 0.4, cw_l * 0.4, cw_l * 0.4,
            px=-boom_l * 0.14, py=pivot_h - cw_l * 0.2, pz=0, color="#505050")

        # Horizontal boom arm extending from mast pivot
        box(boom_l, boom_r * 2, boom_r * 2,
            px=boom_l / 2, py=pivot_h, pz=0, color=primary)

        # Lamp head at tip of boom
        cyl(lamp_r, lamp_h,
            px=boom_l, py=pivot_h - lamp_h / 2, pz=0, color="#d0b840")

        # Second mast offset for cluster effect (halved size)
        if radius > 1.5:
            cyl(mast_r * 0.7, mast_h * 0.85,
                px=radius * 0.55, py=base_h + mast_h * 0.425, pz=radius * 0.3,
                color=primary)

    else:
        box(width, height, depth)

    # After generating the base shapes, apply the master position offset.
    # The AI is instructed to provide this based on the host site DNA.
    position_offset = spatial_params.get("position", {"x": 0, "y": 0, "z": 0})
    offset_x = position_offset.get("x", 0)
    offset_y = position_offset.get("y", 0) # This is the vertical offset in Three.js
    offset_z = position_offset.get("z", 0)

    # Apply the main position offset to all generated geometries
    for g in geos:
        g["position"][0] += offset_x
        g["position"][1] += offset_y
        g["position"][2] += offset_z

    return geos