"""
actions/model_generator_3d.py — Procedural 3D Model Generation Engine

Builds multi-part 3D models in binary GLTF (.glb) format on-demand.
Each model is constructed as a hierarchy of distinct named mesh components,
which enables the Barehands holographic workspace to natively support
smooth exploded-view expansion (via voice commands or touchless pinch-scrubbing).
"""

import math
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

try:
    import trimesh
    import numpy as np
    HAS_TRIMESH = True
except ImportError:
    HAS_TRIMESH = False

logger = logging.getLogger("ModelGenerator3D")

_HERE = Path(__file__).resolve().parent
_MEDIA_ROOTS = [
    _HERE.parent.parent / "barehands-main" / "media",
    _HERE.parent / "barehands-main" / "media",
    Path("C:/Users/Asus/Desktop/Brahma-Echo-main/barehands-main/media"),
]


def get_default_media_dir(mode: str = "holo") -> Path:
    """Finds or creates target media directory for 3D GLB models."""
    for root in _MEDIA_ROOTS:
        if root.parent.exists():
            target = root / ("holo" if mode == "holo" else "")
            target.mkdir(parents=True, exist_ok=True)
            return target
    fallback = _HERE.parent.parent / "barehands-main" / "media" / ("holo" if mode == "holo" else "")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# ==============================================================================
# Procedural Multi-Part 3D Builders (Engineered for Exploded Views)
# ==============================================================================

def _make_arc_reactor() -> Tuple[Any, str]:
    """Generates an explodable Iron Man style Arc Reactor model."""
    scene = trimesh.Scene()

    # 1. Central Core Glow Iris
    core = trimesh.creation.cylinder(radius=0.42, height=0.35, sections=32)
    core.visual.vertex_colors = [0, 240, 255, 230]
    scene.add_geometry(core, node_name="core_iris")

    # 2. Outer Protective Casing
    outer_ring = trimesh.creation.annulus(r_min=1.1, r_max=1.35, height=0.28, sections=40)
    outer_ring.visual.vertex_colors = [120, 130, 140, 255]
    scene.add_geometry(outer_ring, node_name="chassis_ring")

    # 3. Inner Magnetic Field Ring
    inner_ring = trimesh.creation.annulus(r_min=0.6, r_max=0.8, height=0.22, sections=36)
    inner_ring.visual.vertex_colors = [20, 180, 220, 255]
    scene.add_geometry(inner_ring, node_name="magnetic_ring")

    # 4. 10 Radial Copper Induction Coils
    num_coils = 10
    for i in range(num_coils):
        angle = i * (2.0 * math.pi / num_coils)
        coil = trimesh.creation.box(extents=[0.16, 0.28, 0.32])
        coil.visual.vertex_colors = [235, 145, 40, 255]

        rot_z = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
        trans = trimesh.transformations.translation_matrix([
            math.cos(angle) * 0.95,
            math.sin(angle) * 0.95,
            0.0
        ])
        coil.apply_transform(trans @ rot_z)
        scene.add_geometry(coil, node_name=f"induction_coil_{i+1}")

    # 5. Mounting Struts (Top and Bottom caps)
    for z_off, label in [(0.2, "top_bracket"), (-0.2, "base_plate")]:
        bracket = trimesh.creation.cylinder(radius=1.25, height=0.06, sections=32)
        trans = trimesh.transformations.translation_matrix([0, 0, z_off])
        bracket.apply_transform(trans)
        bracket.visual.vertex_colors = [80, 95, 110, 255]
        scene.add_geometry(bracket, node_name=label)

    return scene, "Mark-VI Arc Reactor"


def _make_drone() -> Tuple[Any, str]:
    """Generates an explodable Tactical Quadcopter Drone."""
    scene = trimesh.Scene()

    # 1. Main Central Avionics Fuselage
    body = trimesh.creation.box(extents=[0.7, 0.7, 0.25])
    body.visual.vertex_colors = [45, 52, 60, 255]
    scene.add_geometry(body, node_name="fuselage_core")

    # 2. Top Sensor Dome / GPS Puck
    puck = trimesh.creation.cylinder(radius=0.22, height=0.12, sections=24)
    puck.apply_transform(trimesh.transformations.translation_matrix([0, 0, 0.18]))
    puck.visual.vertex_colors = [0, 229, 255, 255]
    scene.add_geometry(puck, node_name="sensor_puck")

    # 3. 4 Rotor Arms and Motor Pods
    angles = [math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4]
    for idx, ang in enumerate(angles):
        dist = 0.9
        ax, ay = math.cos(ang) * dist, math.sin(ang) * dist

        arm = trimesh.creation.box(extents=[0.6, 0.08, 0.08])
        rot = trimesh.transformations.rotation_matrix(ang, [0, 0, 1])
        trans_arm = trimesh.transformations.translation_matrix([ax * 0.5, ay * 0.5, 0])
        arm.apply_transform(trans_arm @ rot)
        arm.visual.vertex_colors = [70, 80, 90, 255]
        scene.add_geometry(arm, node_name=f"rotor_arm_{idx+1}")

        motor = trimesh.creation.cylinder(radius=0.14, height=0.18, sections=18)
        motor.apply_transform(trimesh.transformations.translation_matrix([ax, ay, 0.08]))
        motor.visual.vertex_colors = [200, 40, 40, 255]
        scene.add_geometry(motor, node_name=f"motor_pod_{idx+1}")

        prop = trimesh.creation.box(extents=[0.65, 0.07, 0.02])
        prop.apply_transform(trimesh.transformations.translation_matrix([ax, ay, 0.20]))
        prop.visual.vertex_colors = [220, 230, 240, 220]
        scene.add_geometry(prop, node_name=f"propeller_blade_{idx+1}")

    # 4. Camera Gimbal Payload (Underside)
    gimbal = trimesh.creation.icosphere(subdivisions=2, radius=0.18)
    gimbal.apply_transform(trimesh.transformations.translation_matrix([0.25, 0, -0.22]))
    gimbal.visual.vertex_colors = [10, 200, 180, 255]
    scene.add_geometry(gimbal, node_name="optical_gimbal")

    return scene, "Tactical Recon Drone"


def _make_jet_engine() -> Tuple[Any, str]:
    """Generates an explodable Turbofan Jet Engine."""
    scene = trimesh.Scene()

    # 1. Outer Bypass Nacelle Cowling
    nacelle = trimesh.creation.annulus(r_min=1.05, r_max=1.22, height=1.6, sections=36)
    nacelle.visual.vertex_colors = [130, 140, 155, 240]
    scene.add_geometry(nacelle, node_name="bypass_nacelle")

    # 2. Central Drive Shaft & Core Spindle
    spindle = trimesh.creation.cylinder(radius=0.28, height=1.8, sections=24)
    spindle.visual.vertex_colors = [60, 65, 75, 255]
    scene.add_geometry(spindle, node_name="central_shaft")

    # 3. Compressor Nose Spinner Cone
    spinner = trimesh.creation.cone(radius=0.35, height=0.45, sections=24)
    trans_sp = trimesh.transformations.translation_matrix([0, 0, 0.95])
    spinner.apply_transform(trans_sp)
    spinner.visual.vertex_colors = [240, 70, 50, 255]
    scene.add_geometry(spinner, node_name="intake_spinner")

    # 4. Fan Blades Array (12 blades)
    num_blades = 12
    for b in range(num_blades):
        bang = b * (2.0 * math.pi / num_blades)
        blade = trimesh.creation.box(extents=[0.10, 0.65, 0.04])
        blade.visual.vertex_colors = [190, 205, 220, 255]

        rot_z = trimesh.transformations.rotation_matrix(bang, [0, 0, 1])
        rot_pitch = trimesh.transformations.rotation_matrix(math.radians(25), [1, 0, 0])
        trans = trimesh.transformations.translation_matrix([
            math.cos(bang) * 0.62,
            math.sin(bang) * 0.62,
            0.6
        ])
        blade.apply_transform(trans @ rot_z @ rot_pitch)
        scene.add_geometry(blade, node_name=f"fan_blade_{b+1}")

    # 5. Combustion Chamber & Turbine Stator Ring
    stator = trimesh.creation.annulus(r_min=0.32, r_max=0.85, height=0.5, sections=30)
    stator.apply_transform(trimesh.transformations.translation_matrix([0, 0, -0.1]))
    stator.visual.vertex_colors = [255, 140, 20, 255]
    scene.add_geometry(stator, node_name="combustion_stator")

    # 6. Exhaust Nozzle
    nozzle = trimesh.creation.cone(radius=0.95, height=0.5, sections=28)
    rot_flip = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    trans_noz = trimesh.transformations.translation_matrix([0, 0, -1.0])
    nozzle.apply_transform(trans_noz @ rot_flip)
    nozzle.visual.vertex_colors = [85, 90, 100, 255]
    scene.add_geometry(nozzle, node_name="exhaust_nozzle")

    return scene, "High-Bypass Turbofan"


def _make_satellite() -> Tuple[Any, str]:
    """Generates an explodable Deep Space Satellite."""
    scene = trimesh.Scene()

    # 1. Main Service Bus
    bus = trimesh.creation.box(extents=[0.9, 0.9, 1.2])
    bus.visual.vertex_colors = [220, 190, 80, 255]
    scene.add_geometry(bus, node_name="satellite_bus")

    # 2. Left & Right Solar Arrays
    for side, sign in [("port", 1), ("starboard", -1)]:
        wing = trimesh.creation.box(extents=[1.5, 0.65, 0.04])
        wing.apply_transform(trimesh.transformations.translation_matrix([sign * 1.4, 0, 0]))
        wing.visual.vertex_colors = [25, 60, 130, 255]
        scene.add_geometry(wing, node_name=f"{side}_solar_array")

        strut = trimesh.creation.cylinder(radius=0.04, height=0.45)
        rot_y = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
        trans = trimesh.transformations.translation_matrix([sign * 0.65, 0, 0])
        strut.apply_transform(trans @ rot_y)
        strut.visual.vertex_colors = [180, 180, 180, 255]
        scene.add_geometry(strut, node_name=f"{side}_boom_strut")

    # 3. High-Gain Communications Dish
    dish = trimesh.creation.cone(radius=0.55, height=0.25, sections=28)
    trans_dish = trimesh.transformations.translation_matrix([0, 0, 0.85])
    dish.apply_transform(trans_dish)
    dish.visual.vertex_colors = [240, 240, 245, 255]
    scene.add_geometry(dish, node_name="high_gain_dish")

    # 4. Omni Antenna Feed
    feed = trimesh.creation.cylinder(radius=0.03, height=0.5)
    feed.apply_transform(trimesh.transformations.translation_matrix([0, 0, 1.15]))
    feed.visual.vertex_colors = [0, 230, 255, 255]
    scene.add_geometry(feed, node_name="antenna_feed")

    return scene, "Orbital Communications Satellite"


def _make_gear_train() -> Tuple[Any, str]:
    """Generates an explodable Planetary Gear Assembly."""
    scene = trimesh.Scene()

    # 1. Base Mounting Carrier Plate
    plate = trimesh.creation.cylinder(radius=1.45, height=0.1, sections=36)
    plate.apply_transform(trimesh.transformations.translation_matrix([0, 0, -0.2]))
    plate.visual.vertex_colors = [70, 75, 85, 255]
    scene.add_geometry(plate, node_name="carrier_plate")

    # 2. Central Sun Gear
    sun = trimesh.creation.cylinder(radius=0.45, height=0.3, sections=24)
    sun.visual.vertex_colors = [240, 160, 40, 255]
    scene.add_geometry(sun, node_name="sun_gear")

    # 3. 4 Planetary Gears
    for g in range(4):
        gang = g * (math.pi / 2)
        planet = trimesh.creation.cylinder(radius=0.32, height=0.28, sections=20)
        gx, gy = math.cos(gang) * 0.85, math.sin(gang) * 0.85
        planet.apply_transform(trimesh.transformations.translation_matrix([gx, gy, 0]))
        planet.visual.vertex_colors = [0, 200, 220, 255]
        scene.add_geometry(planet, node_name=f"planet_gear_{g+1}")

    # 4. Outer Ring Gear Housing
    ring = trimesh.creation.annulus(r_min=1.2, r_max=1.4, height=0.32, sections=36)
    ring.visual.vertex_colors = [140, 150, 160, 255]
    scene.add_geometry(ring, node_name="outer_ring_gear")

    return scene, "Planetary Gear Transmission"


def _make_tesseract() -> Tuple[Any, str]:
    """Generates an explodable Sci-Fi Holographic Tesseract / Cube Matrix."""
    scene = trimesh.Scene()

    # 1. Outer Geometric Frame
    outer = trimesh.creation.box(extents=[1.4, 1.4, 1.4])
    outer.visual.vertex_colors = [0, 229, 255, 180]
    scene.add_geometry(outer, node_name="outer_matrix_cage")

    # 2. Inner Hyper-Cube Core
    inner = trimesh.creation.box(extents=[0.7, 0.7, 0.7])
    rot = trimesh.transformations.rotation_matrix(math.pi / 4, [1, 1, 0])
    inner.apply_transform(rot)
    inner.visual.vertex_colors = [255, 60, 120, 255]
    scene.add_geometry(inner, node_name="hypercube_core")

    # 3. 8 Geometric Corner Nodes
    for idx, (x, y, z) in enumerate([
        (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
        (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)
    ]):
        node = trimesh.creation.icosphere(subdivisions=1, radius=0.12)
        trans = trimesh.transformations.translation_matrix([x * 0.7, y * 0.7, z * 0.7])
        node.apply_transform(trans)
        node.visual.vertex_colors = [0, 255, 200, 255]
        scene.add_geometry(node, node_name=f"quantum_node_{idx+1}")

    return scene, "Holographic Tesseract Matrix"


def _make_generic_parametric(prompt: str) -> Tuple[Any, str]:
    """Dynamic fallback parser that combines geometric primitives into a structured multi-part scene."""
    scene = trimesh.Scene()
    p = prompt.lower()

    if "rocket" in p or "missile" in p:
        body = trimesh.creation.cylinder(radius=0.35, height=1.6, sections=24)
        body.visual.vertex_colors = [230, 235, 240, 255]
        scene.add_geometry(body, node_name="fuselage")

        nose = trimesh.creation.cone(radius=0.35, height=0.6, sections=24)
        nose.apply_transform(trimesh.transformations.translation_matrix([0, 0, 1.1]))
        nose.visual.vertex_colors = [230, 40, 40, 255]
        scene.add_geometry(nose, node_name="payload_cone")

        for i in range(4):
            ang = i * (math.pi / 2)
            fin = trimesh.creation.box(extents=[0.05, 0.45, 0.4])
            rot = trimesh.transformations.rotation_matrix(ang, [0, 0, 1])
            trans = trimesh.transformations.translation_matrix([math.cos(ang) * 0.45, math.sin(ang) * 0.45, -0.6])
            fin.apply_transform(trans @ rot)
            fin.visual.vertex_colors = [60, 60, 70, 255]
            scene.add_geometry(fin, node_name=f"stabilizer_fin_{i+1}")
        return scene, "Ballistic Rocket"

    if "sword" in p or "blade" in p:
        blade = trimesh.creation.box(extents=[0.14, 0.04, 1.6])
        blade.apply_transform(trimesh.transformations.translation_matrix([0, 0, 0.8]))
        blade.visual.vertex_colors = [0, 220, 255, 240]
        scene.add_geometry(blade, node_name="energy_blade")

        guard = trimesh.creation.box(extents=[0.6, 0.1, 0.08])
        guard.visual.vertex_colors = [220, 170, 40, 255]
        scene.add_geometry(guard, node_name="crossguard")

        hilt = trimesh.creation.cylinder(radius=0.06, height=0.45, sections=16)
        hilt.apply_transform(trimesh.transformations.translation_matrix([0, 0, -0.26]))
        hilt.visual.vertex_colors = [40, 40, 45, 255]
        scene.add_geometry(hilt, node_name="hilt_grip")

        pommel = trimesh.creation.icosphere(subdivisions=1, radius=0.1)
        pommel.apply_transform(trimesh.transformations.translation_matrix([0, 0, -0.52]))
        pommel.visual.vertex_colors = [220, 170, 40, 255]
        scene.add_geometry(pommel, node_name="counter_pommel")
        return scene, "Energy Blade"

    # Default multi-part high-tech core assembly
    core = trimesh.creation.icosphere(subdivisions=2, radius=0.45)
    core.visual.vertex_colors = [0, 229, 255, 255]
    scene.add_geometry(core, node_name="focal_core")

    ring_a = trimesh.creation.annulus(r_min=0.8, r_max=0.95, height=0.15, sections=32)
    ring_a.visual.vertex_colors = [120, 140, 160, 255]
    scene.add_geometry(ring_a, node_name="primary_ring")

    ring_b = trimesh.creation.annulus(r_min=1.1, r_max=1.22, height=0.12, sections=32)
    rot_b = trimesh.transformations.rotation_matrix(math.pi / 3, [1, 0, 0])
    ring_b.apply_transform(rot_b)
    ring_b.visual.vertex_colors = [255, 165, 0, 255]
    scene.add_geometry(ring_b, node_name="secondary_gimbal")

    for idx, (dx, dy) in enumerate([(0.9, 0.9), (-0.9, 0.9), (0.9, -0.9), (-0.9, -0.9)]):
        pylon = trimesh.creation.cylinder(radius=0.08, height=0.6, sections=12)
        pylon.apply_transform(trimesh.transformations.translation_matrix([dx * 0.7, dy * 0.7, 0]))
        pylon.visual.vertex_colors = [0, 255, 180, 255]
        scene.add_geometry(pylon, node_name=f"stabilizer_{idx+1}")

    return scene, f"Holographic {prompt.title()}"


def _make_cat() -> Tuple[Any, str]:
    """Generates an explodable Cybernetic Feline / Cat model."""
    scene = trimesh.Scene()

    # 1. Main Torso
    torso = trimesh.creation.box(extents=[0.55, 1.0, 0.45])
    torso.apply_transform(trimesh.transformations.translation_matrix([0, 0, 0.1]))
    torso.visual.vertex_colors = [50, 60, 75, 255]
    scene.add_geometry(torso, node_name="cat_torso")

    # 2. Chest & Tactical Collar
    collar = trimesh.creation.annulus(r_min=0.25, r_max=0.38, height=0.12, sections=24)
    rot_c = trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0])
    trans_c = trimesh.transformations.translation_matrix([0, 0.55, 0.3])
    collar.apply_transform(trans_c @ rot_c)
    collar.visual.vertex_colors = [0, 240, 255, 255]
    scene.add_geometry(collar, node_name="tactical_collar")

    # 3. Head
    head = trimesh.creation.box(extents=[0.48, 0.42, 0.38])
    head.apply_transform(trimesh.transformations.translation_matrix([0, 0.72, 0.42]))
    head.visual.vertex_colors = [70, 85, 105, 255]
    scene.add_geometry(head, node_name="cat_head")

    # 4. Pointed Ears (Left & Right)
    for sign, label in [(-1, "ear_left"), (1, "ear_right")]:
        ear = trimesh.creation.cone(radius=0.12, height=0.32, sections=12)
        trans_e = trimesh.transformations.translation_matrix([sign * 0.18, 0.72, 0.72])
        rot_e = trimesh.transformations.rotation_matrix(sign * 0.15, [0, 1, 0])
        ear.apply_transform(trans_e @ rot_e)
        ear.visual.vertex_colors = [0, 229, 255, 255]
        scene.add_geometry(ear, node_name=label)

    # 5. Cybernetic Eyes
    for sign, label in [(-1, "eye_left"), (1, "eye_right")]:
        eye = trimesh.creation.icosphere(subdivisions=1, radius=0.065)
        eye.apply_transform(trimesh.transformations.translation_matrix([sign * 0.14, 0.94, 0.46]))
        eye.visual.vertex_colors = [0, 255, 200, 255]
        scene.add_geometry(eye, node_name=label)

    # 6. Four Articulated Legs and Paws
    legs_info = [
        (-0.24, 0.35, "leg_front_left"),
        (0.24, 0.35, "leg_front_right"),
        (-0.24, -0.35, "leg_back_left"),
        (0.24, -0.35, "leg_back_right"),
    ]
    for lx, ly, label in legs_info:
        leg = trimesh.creation.cylinder(radius=0.08, height=0.5, sections=16)
        leg.apply_transform(trimesh.transformations.translation_matrix([lx, ly, -0.28]))
        leg.visual.vertex_colors = [90, 100, 115, 255]
        scene.add_geometry(leg, node_name=label)

        foot = trimesh.creation.box(extents=[0.14, 0.18, 0.08])
        foot.apply_transform(trimesh.transformations.translation_matrix([lx, ly + 0.04, -0.52]))
        foot.visual.vertex_colors = [0, 229, 255, 240]
        scene.add_geometry(foot, node_name=f"{label}_paw")

    # 7. Articulated Tail
    tail1 = trimesh.creation.cylinder(radius=0.05, height=0.45, sections=12)
    rot_t1 = trimesh.transformations.rotation_matrix(-math.pi / 4, [1, 0, 0])
    trans_t1 = trimesh.transformations.translation_matrix([0, -0.65, 0.25])
    tail1.apply_transform(trans_t1 @ rot_t1)
    tail1.visual.vertex_colors = [60, 70, 85, 255]
    scene.add_geometry(tail1, node_name="tail_base")

    tail2 = trimesh.creation.cylinder(radius=0.04, height=0.35, sections=12)
    rot_t2 = trimesh.transformations.rotation_matrix(math.pi / 6, [1, 0, 0])
    trans_t2 = trimesh.transformations.translation_matrix([0, -0.85, 0.52])
    tail2.apply_transform(trans_t2 @ rot_t2)
    tail2.visual.vertex_colors = [0, 229, 255, 255]
    scene.add_geometry(tail2, node_name="tail_tip")

    return scene, "Cybernetic Feline (Cat)"


def _make_car() -> Tuple[Any, str]:
    """Generates an explodable Cybernetic Sports Car / Vehicle model."""
    scene = trimesh.Scene()

    # 1. Main Chassis
    chassis = trimesh.creation.box(extents=[0.9, 1.8, 0.28])
    chassis.apply_transform(trimesh.transformations.translation_matrix([0, 0, 0]))
    chassis.visual.vertex_colors = [35, 40, 50, 255]
    scene.add_geometry(chassis, node_name="main_chassis")

    # 2. Cockpit Canopy / Cabin
    cabin = trimesh.creation.box(extents=[0.75, 0.9, 0.32])
    cabin.apply_transform(trimesh.transformations.translation_matrix([0, -0.1, 0.28]))
    cabin.visual.vertex_colors = [0, 229, 255, 180]
    scene.add_geometry(cabin, node_name="canopy_cockpit")

    # 3. 4 Wheels
    for wx, wy, label in [
        (-0.52, 0.55, "wheel_front_left"),
        (0.52, 0.55, "wheel_front_right"),
        (-0.52, -0.55, "wheel_rear_left"),
        (0.52, -0.55, "wheel_rear_right"),
    ]:
        wheel = trimesh.creation.cylinder(radius=0.25, height=0.18, sections=24)
        rot_w = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
        trans_w = trimesh.transformations.translation_matrix([wx, wy, -0.05])
        wheel.apply_transform(trans_w @ rot_w)
        wheel.visual.vertex_colors = [25, 25, 30, 255]
        scene.add_geometry(wheel, node_name=label)

    # 4. Front Aero Bumper
    bumper = trimesh.creation.box(extents=[0.85, 0.25, 0.16])
    bumper.apply_transform(trimesh.transformations.translation_matrix([0, 0.95, -0.04]))
    bumper.visual.vertex_colors = [0, 240, 255, 255]
    scene.add_geometry(bumper, node_name="aero_splitter")

    # 5. Rear Spoiler Wing
    wing = trimesh.creation.box(extents=[0.95, 0.18, 0.05])
    wing.apply_transform(trimesh.transformations.translation_matrix([0, -0.9, 0.38]))
    wing.visual.vertex_colors = [255, 60, 60, 255]
    scene.add_geometry(wing, node_name="rear_spoiler")

    return scene, "Cybernetic Sport Vehicle"


def _make_credit_card(color: str = "red") -> Tuple[Any, str]:
    """Generates an explodable Holographic Chip Card / Credit Card model."""
    scene = trimesh.Scene()
    card = trimesh.creation.box(extents=[1.5, 0.95, 0.04])
    c_rgb = [220, 30, 40, 255] if "red" in color else [30, 120, 220, 255]
    card.visual.vertex_colors = c_rgb
    scene.add_geometry(card, node_name="card_substrate")

    chip = trimesh.creation.box(extents=[0.24, 0.2, 0.06])
    chip.apply_transform(trimesh.transformations.translation_matrix([-0.42, 0.05, 0.02]))
    chip.visual.vertex_colors = [240, 200, 50, 255]
    scene.add_geometry(chip, node_name="emv_smart_chip")

    stripe = trimesh.creation.box(extents=[1.5, 0.18, 0.05])
    stripe.apply_transform(trimesh.transformations.translation_matrix([0, 0.25, -0.02]))
    stripe.visual.vertex_colors = [20, 20, 25, 255]
    scene.add_geometry(stripe, node_name="magnetic_stripe")

    foil = trimesh.creation.box(extents=[0.22, 0.18, 0.06])
    foil.apply_transform(trimesh.transformations.translation_matrix([0.48, -0.15, 0.02]))
    foil.visual.vertex_colors = [0, 240, 255, 255]
    scene.add_geometry(foil, node_name="security_hologram")

    return scene, f"Holographic {'Red ' if 'red' in color else ''}Credit Card"


# ==============================================================================
# Public API
# ==============================================================================

def generate_model(prompt: str, mode: str = "holo", output_dir: Optional[Path] = None) -> Tuple[Path, str, int]:
    """
    Constructs a 3D model scene from a descriptive prompt, exports it as .glb,
    and returns (file_path, display_title, parts_count).
    """
    if not HAS_TRIMESH:
        raise RuntimeError("trimesh is not installed in the python environment.")

    p_clean = prompt.lower().strip()

    if any(k in p_clean for k in ["cat", "feline", "kitten", "kitty"]):
        scene, title = _make_cat()
    elif any(k in p_clean for k in ["car", "vehicle", "automobile", "truck", "audi", "bmw", "tesla"]):
        scene, title = _make_car()
    elif any(k in p_clean for k in ["card", "credit card", "debit card", "atm card"]):
        scene, title = _make_credit_card(color="red" if "red" in p_clean else "blue")
    elif any(k in p_clean for k in ["reactor", "arc", "iron man", "tony stark"]):
        scene, title = _make_arc_reactor()
    elif any(k in p_clean for k in ["drone", "quadcopter", "uav"]):
        scene, title = _make_drone()
    elif any(k in p_clean for k in ["engine", "turbine", "jet", "turbofan"]):
        scene, title = _make_jet_engine()
    elif any(k in p_clean for k in ["satellite", "station", "solar array"]):
        scene, title = _make_satellite()
    elif any(k in p_clean for k in ["gear", "transmission", "planetary"]):
        scene, title = _make_gear_train()
    elif any(k in p_clean for k in ["cube", "tesseract", "matrix", "box"]):
        scene, title = _make_tesseract()
    else:
        scene, title = _make_generic_parametric(prompt)

    # Determine save path
    dest_dir = output_dir or get_default_media_dir(mode)
    dest_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() else "_" for c in title.lower()).strip("_")
    out_file = dest_dir / f"{safe_name}.glb"

    # Export binary GLTF
    glb_data = scene.export(file_type="glb")
    out_file.write_bytes(glb_data)
    parts_count = len(scene.geometry)

    logger.info(f"Generated 3D model '{title}' ({parts_count} parts, {len(glb_data)} bytes) -> {out_file}")
    return out_file, title, parts_count
