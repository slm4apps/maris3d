# SPDX-License-Identifier: Apache-2.0
"""Locked Blender prompt set v0 (Blender 5.2). Each item: id, level (1 primitive .. 4 composite),
prompt, check (see checks.py) and ref (a reference script that must pass its own check)."""
P = []
def add(level, prompt, check, ref):
    P.append({"id": f"b{len(P)+1:03d}", "level": level, "prompt": prompt, "check": check, "ref": ref.strip()})

# ---- level 1: single primitives
add(1, "Add a cube to the scene.", {"meshes": (1, 1)}, "import bpy\nbpy.ops.mesh.primitive_cube_add()")
add(1, "Add a UV sphere with radius 2 at the origin.", {"meshes": (1, 1), "bbox_x": (3.9, 4.1)}, "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add(radius=2)")
add(1, "Add a cylinder with radius 1 and depth 4.", {"meshes": (1, 1), "bbox_z": (1.9, 2.1)}, "import bpy\nbpy.ops.mesh.primitive_cylinder_add(radius=1, depth=4)")
add(1, "Add a cone at location (3, 0, 0).", {"meshes": (1, 1), "loc_near": (3, 0, 0)}, "import bpy\nbpy.ops.mesh.primitive_cone_add(location=(3,0,0))")
add(1, "Add a torus.", {"meshes": (1, 1)}, "import bpy\nbpy.ops.mesh.primitive_torus_add()")
add(1, "Add a plane scaled to 10 by 10 units.", {"meshes": (1, 1), "bbox_x": (9.9, 10.1)}, "import bpy\nbpy.ops.mesh.primitive_plane_add(size=10)")
add(1, "Add an ico sphere with 3 subdivisions.", {"meshes": (1, 1), "verts_min": 100}, "import bpy\nbpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3)")
add(1, "Add a monkey (Suzanne) mesh.", {"meshes": (1, 1), "verts_min": 400}, "import bpy\nbpy.ops.mesh.primitive_monkey_add()")
add(1, "Add a camera at (0, -10, 5).", {"camera": 1, "loc_near": (0, -10, 5)}, "import bpy\nbpy.ops.object.camera_add(location=(0,-10,5))")
add(1, "Add a sun light.", {"light": "SUN"}, "import bpy\nbpy.ops.object.light_add(type='SUN')")
add(1, "Add a point light at (4, 4, 6).", {"light": "POINT", "loc_near": (4, 4, 6)}, "import bpy\nbpy.ops.object.light_add(type='POINT', location=(4,4,6))")
add(1, "Add a Bezier curve.", {"curve": 1}, "import bpy\nbpy.ops.curve.primitive_bezier_curve_add()")

# ---- level 2: transform / modifiers / materials
add(2, "Add a cube, rotate it 45 degrees around Z and move it to (2, 3, 1).", {"meshes": (1, 1), "loc_near": (2, 3, 1)},
    "import bpy, math\nbpy.ops.mesh.primitive_cube_add(location=(2,3,1), rotation=(0,0,math.radians(45)))")
add(2, "Add a cube and add a Subdivision Surface modifier with 2 levels.", {"meshes": (1, 1), "modifier": "SUBSURF"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nm = bpy.context.object.modifiers.new('Subsurf','SUBSURF')\nm.levels = 2")
add(2, "Add a cube with a Bevel modifier, width 0.1, 3 segments.", {"meshes": (1, 1), "modifier": "BEVEL"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nm = bpy.context.object.modifiers.new('Bevel','BEVEL')\nm.width = 0.1\nm.segments = 3")
add(2, "Add a plane and a Solidify modifier with thickness 0.2.", {"meshes": (1, 1), "modifier": "SOLIDIFY"},
    "import bpy\nbpy.ops.mesh.primitive_plane_add()\nm = bpy.context.object.modifiers.new('Solidify','SOLIDIFY')\nm.thickness = 0.2")
add(2, "Add a cube and an Array modifier with count 5 and a relative offset of 1.2 on X.", {"meshes": (1, 1), "modifier": "ARRAY"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nm = bpy.context.object.modifiers.new('Array','ARRAY')\nm.count = 5\nm.relative_offset_displace[0] = 1.2")
add(2, "Add a cube and a Mirror modifier on the X axis.", {"meshes": (1, 1), "modifier": "MIRROR"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.modifiers.new('Mirror','MIRROR')")
add(2, "Add a sphere and give it a red material named RedMat.", {"meshes": (1, 1), "material": 1},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nmat = bpy.data.materials.new('RedMat')\nmat.diffuse_color = (1,0,0,1)\nbpy.context.object.data.materials.append(mat)")
add(2, "Add a cube and apply smooth shading to it.", {"meshes": (1, 1)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.object.shade_smooth()")
add(2, "Add a cube and scale it to 2 by 1 by 0.5.", {"meshes": (1, 1), "scale_near": (2, 1, .5)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.scale = (2, 1, 0.5)")
add(2, "Add a cube named Crate and put it in a new collection named Props.", {"meshes": (1, 1), "name": "Crate", "collection": "Props"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.name = 'Crate'\nc = bpy.data.collections.new('Props')\nbpy.context.scene.collection.children.link(c)\nfor u in o.users_collection: u.objects.unlink(o)\nc.objects.link(o)")
add(2, "Add a cube and unwrap it with Smart UV Project.", {"meshes": (1, 1), "uv": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.object.mode_set(mode='EDIT')\nbpy.ops.mesh.select_all(action='SELECT')\nbpy.ops.uv.smart_project()\nbpy.ops.object.mode_set(mode='OBJECT')")
add(2, "Add a plane and a Subdivision Surface modifier, then apply the modifier.", {"meshes": (1, 1), "verts_min": 9},
    "import bpy\nbpy.ops.mesh.primitive_plane_add()\no = bpy.context.object\nm = o.modifiers.new('S','SUBSURF')\nm.levels = 2\nbpy.ops.object.modifier_apply(modifier=m.name)")
add(2, "Add a cube and join it with a sphere into one mesh object.", {"meshes": (1, 1), "verts_min": 300},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.mesh.primitive_uv_sphere_add(location=(0,0,2))\nfor o in bpy.data.objects: o.select_set(True)\nbpy.context.view_layer.objects.active = bpy.data.objects[0]\nbpy.ops.object.join()")

# ---- level 3: animation, parenting, scene setup
add(3, "Add a cube and animate it moving from x=0 at frame 1 to x=10 at frame 60.", {"meshes": (1, 1), "animated": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.location.x = 0\no.keyframe_insert('location', frame=1)\no.location.x = 10\no.keyframe_insert('location', frame=60)")
add(3, "Set the animation length to 120 frames and add a cube that rotates a full turn around Z over that time.", {"meshes": (1, 1), "animated": 1, "frame_end": 120},
    "import bpy, math\nbpy.context.scene.frame_start = 1\nbpy.context.scene.frame_end = 120\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.rotation_euler.z = 0\no.keyframe_insert('rotation_euler', frame=1)\no.rotation_euler.z = math.radians(360)\no.keyframe_insert('rotation_euler', frame=120)")
add(3, "Add an empty named Rig and parent a cube to it.", {"meshes": (1, 1), "parented": 1, "name": "Rig"},
    "import bpy\nbpy.ops.object.empty_add()\ne = bpy.context.object\ne.name = 'Rig'\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.parent = e")
add(3, "Create a basic studio setup: a plane as floor, a sun light and a camera.", {"meshes": (1, 1), "light": "SUN", "camera": 1},
    "import bpy\nbpy.ops.mesh.primitive_plane_add(size=20)\nbpy.ops.object.light_add(type='SUN', location=(5,5,10))\nbpy.ops.object.camera_add(location=(0,-12,6), rotation=(1.1,0,0))\nbpy.context.scene.camera = bpy.context.object")
add(3, "Add 5 cubes in a row along the X axis, spaced 3 units apart.", {"meshes": (5, 5), "bbox_x": (1.9, 2.1)},
    "import bpy\nfor i in range(5):\n    bpy.ops.mesh.primitive_cube_add(location=(i*3,0,0))")
add(3, "Create a 4 by 4 grid of spheres spaced 2.5 units apart.", {"meshes": (16, 16)},
    "import bpy\nfor x in range(4):\n    for y in range(4):\n        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(x*2.5,y*2.5,0))")
add(3, "Add a circle of 8 cylinders with radius 5 around the origin.", {"meshes": (8, 8)},
    "import bpy, math\nfor i in range(8):\n    a = i*2*math.pi/8\n    bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=2, location=(5*math.cos(a),5*math.sin(a),1))")
add(3, "Add a sphere and a point light, and make the sphere use a metallic material with metallic 1.0 and roughness 0.2.", {"meshes": (1, 1), "light": "POINT", "material": 1},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nmat = bpy.data.materials.new('Metal')\nmat.metallic = 1.0\nmat.roughness = 0.2\nbpy.context.object.data.materials.append(mat)\nbpy.ops.object.light_add(type='POINT', location=(3,3,4))")

# ---- level 4: composite models
add(4, "Model a simple table: a flat top 2 by 1 and 0.1 thick, with four legs. Use only cubes.", {"meshes": (5, 5), "bbox_z": (0.5, 1.5)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(location=(0,0,0.8))\nt = bpy.context.object\nt.scale = (1,0.5,0.05)\nfor x in (-0.9,0.9):\n    for y in (-0.4,0.4):\n        bpy.ops.mesh.primitive_cube_add(location=(x,y,0.4))\n        bpy.context.object.scale = (0.05,0.05,0.4)")
add(4, "Make a low-poly chair with a seat, a back and four legs, all from cubes, and give it a wood-brown material.", {"meshes": (6, 8), "material": 6, "bbox_z": (0.8, 2.5)},
    "import bpy\nmat = bpy.data.materials.new('Wood')\nmat.diffuse_color = (0.4,0.25,0.1,1)\ndef box(loc, sc):\n    bpy.ops.mesh.primitive_cube_add(location=loc)\n    o = bpy.context.object\n    o.scale = sc\n    o.data.materials.append(mat)\nbox((0,0,0.5),(0.5,0.5,0.05))\nbox((0,-0.45,1.0),(0.5,0.05,0.5))\nfor x in (-0.45,0.45):\n    for y in (-0.45,0.45):\n        box((x,y,0.225),(0.05,0.05,0.225))")
add(4, "Build a snowman from three stacked spheres of decreasing size, with two small spheres as eyes and a cone as the nose.", {"meshes": (6, 6)},
    "import bpy\nfor r,z in ((1,1),(0.7,2.4),(0.5,3.4)):\n    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(0,0,z))\nfor x in (-0.2,0.2):\n    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.06, location=(x,-0.45,3.55))\nbpy.ops.mesh.primitive_cone_add(radius1=0.07, depth=0.4, location=(0,-0.6,3.4), rotation=(1.5708,0,0))")
add(4, "Create a staircase with 8 steps, each step a cube 2 wide, 0.4 high and 0.6 deep, rising as it goes.", {"meshes": (8, 8), "bbox_z": (3.0, 3.6)},
    "import bpy\nfor i in range(8):\n    bpy.ops.mesh.primitive_cube_add(location=(0,i*0.6,0.2+i*0.4))\n    bpy.context.object.scale = (1,0.3,0.2)")
add(4, "Create a simple house: a cube body, a cone roof on top, and a door as a thin box on the front.", {"meshes": (3, 3)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(location=(0,0,1))\nbpy.ops.mesh.primitive_cone_add(radius1=1.8, depth=1.5, location=(0,0,2.75), vertices=4)\nbpy.ops.mesh.primitive_cube_add(location=(0,-1.0,0.6))\nbpy.context.object.scale = (0.3,0.05,0.6)")
add(4, "Make a dumbbell: two spheres joined by a cylinder along the X axis.", {"meshes": (3, 3)},
    "import bpy, math\nbpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=3, rotation=(0,math.radians(90),0))\nfor x in (-1.5,1.5):\n    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.6, location=(x,0,0))")
add(4, "Create a ring (torus) with a small sphere gem on top, both with a gold material named Gold.", {"meshes": (2, 2), "material": 2},
    "import bpy\nmat = bpy.data.materials.new('Gold')\nmat.diffuse_color = (1,0.8,0.2,1)\nbpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=0.15)\nbpy.context.object.data.materials.append(mat)\nbpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, location=(0,0,1.1))\nbpy.context.object.data.materials.append(mat)")
add(4, "Make a lamp: a cylinder base, a thin pole, a cone shade, and a point light inside the shade.", {"meshes": (3, 3), "light": "POINT"},
    "import bpy\nbpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=0.1, location=(0,0,0.05))\nbpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=2, location=(0,0,1.1))\nbpy.ops.mesh.primitive_cone_add(radius1=0.6, radius2=0.2, depth=0.6, location=(0,0,2.3))\nbpy.ops.object.light_add(type='POINT', location=(0,0,2.2))")

# =====================================================================================
# b042+ : extension to ~200 prompts . The 41 above are never edited or reordered.
# =====================================================================================

# ---- level 1 (b042+): primitives, lights, cameras, curves, text, empties
add(1, "Create a cube whose edges are 4 units long.", {"meshes": (1, 1), "bbox_x": (3.9, 4.1)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(size=4)")
add(1, "I need a cylinder with 6 sides, 1.5 tall.", {"meshes": (1, 1), "dim": (2, 1.4, 1.6), "faces": (8, 8)},
    "import bpy\nbpy.ops.mesh.primitive_cylinder_add(vertices=6, depth=1.5)")
add(1, "Place a UV sphere at (0, 5, 2) built from 16 segments and 8 rings.", {"meshes": (1, 1), "loc_near": (0, 5, 2), "verts_max": 120},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, location=(0,5,2))")
add(1, "Add a cone that is 3 units tall with a base radius of 1.", {"meshes": (1, 1), "dim": (2, 2.9, 3.1), "bbox_x": (1.9, 2.1)},
    "import bpy\nbpy.ops.mesh.primitive_cone_add(radius1=1, depth=3)")
add(1, "Make a torus with a major radius of 2 and a minor radius of 0.5.", {"meshes": (1, 1), "bbox_x": (4.9, 5.1)},
    "import bpy\nbpy.ops.mesh.primitive_torus_add(major_radius=2, minor_radius=0.5)")
add(1, "Create a flat circle mesh with 32 vertices and radius 3.", {"meshes": (1, 1), "bbox_x": (5.9, 6.1)},
    "import bpy\nbpy.ops.mesh.primitive_circle_add(vertices=32, radius=3)")
add(1, "Add a grid mesh with 10 subdivisions along each axis, 5 units wide.", {"meshes": (1, 1), "verts_min": 100, "verts_max": 144, "bbox_x": (4.9, 5.1)},
    "import bpy\nbpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10, size=5)")
add(1, "Add an ico sphere with radius 1.5 located at (-2, -2, 0).", {"meshes": (1, 1), "loc_near": (-2, -2, 0), "bbox_x": (2.7, 3.1)},
    "import bpy\nbpy.ops.mesh.primitive_ico_sphere_add(radius=1.5, location=(-2,-2,0))")
add(1, "Add a spot light at (0, 0, 8).", {"light": "SPOT", "loc_near": (0, 0, 8)},
    "import bpy\nbpy.ops.object.light_add(type='SPOT', location=(0,0,8))")
add(1, "Create an area light.", {"light": "AREA"},
    "import bpy\nbpy.ops.object.light_add(type='AREA')")
add(1, "Add a sun light and set its strength to 5.", {"light": "SUN", "data_prop": ("LIGHT", "energy", 5.0)},
    "import bpy\nbpy.ops.object.light_add(type='SUN')\nbpy.context.object.data.energy = 5")
add(1, "Add a point light with 1000 watts of power.", {"light": "POINT", "data_prop": ("LIGHT", "energy", 1000.0)},
    "import bpy\nbpy.ops.object.light_add(type='POINT')\nbpy.context.object.data.energy = 1000")
add(1, "Create a camera with a 85mm focal length.", {"camera": 1, "data_prop": ("CAMERA", "lens", 85.0)},
    "import bpy\nbpy.ops.object.camera_add()\nbpy.context.object.data.lens = 85")
add(1, "Add an orthographic camera.", {"camera": 1, "data_prop": ("CAMERA", "type", "ORTHO")},
    "import bpy\nbpy.ops.object.camera_add()\nbpy.context.object.data.type = 'ORTHO'")
add(1, "Add a camera and make it the active scene camera.", {"camera": 1},
    "import bpy\nbpy.ops.object.camera_add()\nbpy.context.scene.camera = bpy.context.object")
add(1, "Add an empty of plain axes type at (1, 2, 3).", {"type_count": {"EMPTY": (1, 1)}, "loc_near": (1, 2, 3)},
    "import bpy\nbpy.ops.object.empty_add(type='PLAIN_AXES', location=(1,2,3))")
add(1, "Add a sphere-shaped empty.", {"type_count": {"EMPTY": (1, 1)}},
    "import bpy\nbpy.ops.object.empty_add(type='SPHERE')")
add(1, "Add a text object that reads Hello.", {"text": "Hello"},
    "import bpy\nbpy.ops.object.text_add()\nbpy.context.object.data.body = 'Hello'")
add(1, "Create a 3D text saying BLENDER at (0, 0, 1).", {"text": "BLENDER", "loc_near": (0, 0, 1)},
    "import bpy\nbpy.ops.object.text_add(location=(0,0,1))\nbpy.context.object.data.body = 'BLENDER'")
add(1, "Add a Bezier circle with radius 3.", {"curve": 1},
    "import bpy\nbpy.ops.curve.primitive_bezier_circle_add(radius=3)")
add(1, "Add a NURBS path curve.", {"curve": 1},
    "import bpy\nbpy.ops.curve.primitive_nurbs_path_add()")
add(1, "Add a plane with the name Ground.", {"meshes": (1, 1), "name": "Ground"},
    "import bpy\nbpy.ops.mesh.primitive_plane_add()\nbpy.context.object.name = 'Ground'")
add(1, "Add a cube and rename it to Box_01.", {"meshes": (1, 1), "name": "Box_01"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.name = 'Box_01'")
add(1, "Add a cube rotated 90 degrees about the X axis.", {"meshes": (1, 1), "rot_near": (1.5708, 0, 0)},
    "import bpy, math\nbpy.ops.mesh.primitive_cube_add(rotation=(math.radians(90),0,0))")
add(1, "Add a cube, then double its size on every axis by changing its scale.", {"meshes": (1, 1), "scale_near": (2, 2, 2)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.scale = (2,2,2)")
add(1, "Add a cube at (0, 0, 5) and lower it so its location is the origin.", {"meshes": (1, 1), "loc_near": (0, 0, 0)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(location=(0,0,5))\nbpy.context.object.location = (0,0,0)")
add(1, "Add two spheres, one at (-3, 0, 0) and one at (3, 0, 0).", {"meshes": (2, 2), "loc_near": (3, 0, 0)},
    "import bpy\nfor x in (-3,3):\n    bpy.ops.mesh.primitive_uv_sphere_add(location=(x,0,0))")
add(1, "Create a cylinder lying on its side along the Y axis.", {"meshes": (1, 1), "rot_near": (1.5708, 0, 0)},
    "import bpy, math\nbpy.ops.mesh.primitive_cylinder_add(rotation=(math.radians(90),0,0))")
add(1, "Add a cone pointing downward (flipped upside down).", {"meshes": (1, 1), "rot_near": (3.1416, 0, 0)},
    "import bpy, math\nbpy.ops.mesh.primitive_cone_add(rotation=(math.pi,0,0))")
add(1, "Create a plane at height z=2 sized 6 by 6.", {"meshes": (1, 1), "bbox_x": (5.9, 6.1), "loc_near": (0, 0, 2)},
    "import bpy\nbpy.ops.mesh.primitive_plane_add(size=6, location=(0,0,2))")
add(1, "Make a very flat box: a cube that is 4 wide, 4 deep and 0.2 tall.", {"meshes": (1, 1), "dim": (2, 0.15, 0.25), "bbox_x": (3.9, 4.1)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.scale = (2,2,0.1)")
add(1, "Add a monkey head at (0, 0, 2) scaled to 1.5 times its normal size.", {"meshes": (1, 1), "verts_min": 400, "loc_near": (0, 0, 2), "scale_near": (1.5, 1.5, 1.5)},
    "import bpy\nbpy.ops.mesh.primitive_monkey_add(location=(0,0,2))\nbpy.context.object.scale = (1.5,1.5,1.5)")
add(1, "Add a Bezier curve and move it up to z=3.", {"curve": 1, "loc_near": (0, 0, 3)},
    "import bpy\nbpy.ops.curve.primitive_bezier_curve_add(location=(0,0,3))")
add(1, "Create a cube with 8 vertices and nothing else in the scene.", {"meshes": (1, 1), "objects_min": 1, "verts_min": 8, "verts_max": 8},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()")
add(1, "Add a camera looking straight down from 10 units above the origin.", {"camera": 1, "loc_near": (0, 0, 10), "rot_near": (0, 0, 0)},
    "import bpy\nbpy.ops.object.camera_add(location=(0,0,10), rotation=(0,0,0))")
add(1, "Add a UV sphere and set the scene's world to exist with a background color of dark gray.", {"meshes": (1, 1), "world": 1},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nw = bpy.data.worlds.new('World')\nw.color = (0.05,0.05,0.05)\nbpy.context.scene.world = w")

# ---- level 2 (b078+): transforms, modifiers, materials, shading, UV, mesh ops
add(2, "Add a cube and put a Subdivision Surface modifier on it with viewport level 3.", {"meshes": (1, 1), "mod_prop": ("SUBSURF", "levels", 3)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nm = bpy.context.object.modifiers.new('Subsurf','SUBSURF')\nm.levels = 3")
add(2, "Give a plane a Wireframe modifier with a thickness of 0.05.", {"meshes": (1, 1), "mod_prop": ("WIREFRAME", "thickness", 0.05)},
    "import bpy\nbpy.ops.mesh.primitive_plane_add()\nm = bpy.context.object.modifiers.new('Wire','WIREFRAME')\nm.thickness = 0.05")
add(2, "Create a cylinder and attach a Decimate modifier that keeps 30 percent of the faces.", {"meshes": (1, 1), "mod_prop": ("DECIMATE", "ratio", 0.3)},
    "import bpy\nbpy.ops.mesh.primitive_cylinder_add(vertices=64)\nm = bpy.context.object.modifiers.new('Decimate','DECIMATE')\nm.ratio = 0.3")
add(2, "Add a sphere with a Displace modifier at strength 0.5.", {"meshes": (1, 1), "mod_prop": ("DISPLACE", "strength", 0.5)},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nm = bpy.context.object.modifiers.new('Displace','DISPLACE')\nm.strength = 0.5")
add(2, "Make a cube with a Mirror modifier on Y only (not X).", {"meshes": (1, 1), "modifier": "MIRROR"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nm = bpy.context.object.modifiers.new('Mirror','MIRROR')\nm.use_axis = (False, True, False)")
add(2, "Make a cube and then bevel it with a Bevel modifier whose amount is 0.25 using 2 segments.", {"meshes": (1, 1), "mod_prop": ("BEVEL", "segments", 2)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nm = bpy.context.object.modifiers.new('Bevel','BEVEL')\nm.width = 0.25\nm.segments = 2")
add(2, "Add a cube with an Array modifier of 4 copies and a constant offset of 3 units on Y.", {"meshes": (1, 1), "mod_prop": ("ARRAY", "count", 4)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nm = bpy.context.object.modifiers.new('Array','ARRAY')\nm.count = 4\nm.use_relative_offset = False\nm.use_constant_offset = True\nm.constant_offset_displace = (0,3,0)")
add(2, "Add a plane with a Solidify modifier, thickness 0.5, then apply it so the mesh has real thickness.", {"meshes": (1, 1), "verts_min": 8, "dim": (2, 0.45, 0.55)},
    "import bpy\nbpy.ops.mesh.primitive_plane_add()\no = bpy.context.object\nm = o.modifiers.new('Solidify','SOLIDIFY')\nm.thickness = 0.5\nbpy.ops.object.modifier_apply(modifier=m.name)")
add(2, "Add a cube and use a Bevel modifier and a Subdivision Surface modifier on it, in that order.", {"meshes": (1, 1), "modifier": "BEVEL", "mod_count": ("SUBSURF", 1)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.modifiers.new('Bevel','BEVEL')\no.modifiers.new('Subsurf','SUBSURF')")
add(2, "Add a Simple Deform modifier that twists a tall box by 90 degrees.", {"meshes": (1, 1), "modifier": "SIMPLE_DEFORM"},
    "import bpy, math\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.scale = (0.5,0.5,2)\nbpy.ops.object.transform_apply(scale=True)\nm = o.modifiers.new('Twist','SIMPLE_DEFORM')\nm.deform_method = 'TWIST'\nm.angle = math.radians(90)")
add(2, "Create a plane and subdivide it by adding a Subdivision Surface modifier set to Simple, level 2.", {"meshes": (1, 1), "mod_prop": ("SUBSURF", "levels", 2)},
    "import bpy\nbpy.ops.mesh.primitive_plane_add()\nm = bpy.context.object.modifiers.new('Subsurf','SUBSURF')\nm.subdivision_type = 'SIMPLE'\nm.levels = 2")
add(2, "Add a Triangulate modifier to a cube.", {"meshes": (1, 1), "modifier": "TRIANGULATE"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.modifiers.new('Tri','TRIANGULATE')")
add(2, "Add a cube and a Weld modifier.", {"meshes": (1, 1), "modifier": "WELD"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.context.object.modifiers.new('Weld','WELD')")
add(2, "Add a sphere and give it a Smooth modifier (Smooth by Angle is not needed).", {"meshes": (1, 1), "modifier": "SMOOTH"},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nbpy.context.object.modifiers.new('Smooth','SMOOTH')")
add(2, "Add a cube with a Remesh modifier in voxel mode with a voxel size of 0.1.", {"meshes": (1, 1), "modifier": "REMESH"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nm = bpy.context.object.modifiers.new('Remesh','REMESH')\nm.mode = 'VOXEL'\nm.voxel_size = 0.1")
add(2, "Make a blue material called BlueMat and assign it to a new cube.", {"meshes": (1, 1), "mat_name": "BlueMat", "mat_color": (0, 0, 1), "material": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nmat = bpy.data.materials.new('BlueMat')\nmat.diffuse_color = (0,0,1,1)\nbpy.context.object.data.materials.append(mat)")
add(2, "Create a cylinder with a green material.", {"meshes": (1, 1), "mat_color": (0, 1, 0), "material": 1},
    "import bpy\nbpy.ops.mesh.primitive_cylinder_add()\nmat = bpy.data.materials.new('Green')\nmat.diffuse_color = (0,1,0,1)\nbpy.context.object.data.materials.append(mat)")
add(2, "Add a torus and make it shiny: material with roughness 0.1.", {"meshes": (1, 1), "material": 1, "mat_prop": ("roughness", 0.1)},
    "import bpy\nbpy.ops.mesh.primitive_torus_add()\nmat = bpy.data.materials.new('Shiny')\nmat.roughness = 0.1\nbpy.context.object.data.materials.append(mat)")
add(2, "Add a sphere with a fully metallic material (metallic 1).", {"meshes": (1, 1), "material": 1, "mat_prop": ("metallic", 1.0)},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nmat = bpy.data.materials.new('Chrome')\nmat.metallic = 1.0\nbpy.context.object.data.materials.append(mat)")
add(2, "Add two cubes next to each other, the left one red and the right one white, with separate materials.", {"meshes": (2, 2), "material": 2, "mat_color": (1, 0, 0)},
    "import bpy\nfor x, c in ((-2,(1,0,0,1)),(2,(1,1,1,1))):\n    bpy.ops.mesh.primitive_cube_add(location=(x,0,0))\n    m = bpy.data.materials.new('M%d' % x)\n    m.diffuse_color = c\n    bpy.context.object.data.materials.append(m)")
add(2, "Create a plane and give it a gray material using the node-based shader: set the Principled BSDF base color to (0.5, 0.5, 0.5, 1).", {"meshes": (1, 1), "material": 1},
    "import bpy\nbpy.ops.mesh.primitive_plane_add()\nmat = bpy.data.materials.new('Gray')\nbsdf = mat.node_tree.nodes['Principled BSDF']\nbsdf.inputs['Base Color'].default_value = (0.5,0.5,0.5,1)\nmat.diffuse_color = (0.5,0.5,0.5,1)\nbpy.context.object.data.materials.append(mat)")
add(2, "Add a cube with an emissive material: use the Emission input of the Principled BSDF with strength 5.", {"meshes": (1, 1), "material": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nmat = bpy.data.materials.new('Glow')\nb = mat.node_tree.nodes['Principled BSDF']\nb.inputs['Emission Color'].default_value = (1,0.6,0.1,1)\nb.inputs['Emission Strength'].default_value = 5\nbpy.context.object.data.materials.append(mat)")
add(2, "Give a sphere a semi-transparent glass look with alpha 0.3 on a material named Glass.", {"meshes": (1, 1), "material": 1, "mat_name": "Glass"},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nmat = bpy.data.materials.new('Glass')\nmat.diffuse_color = (0.8,0.9,1,0.3)\nmat.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.3\nbpy.context.object.data.materials.append(mat)")
add(2, "Add a UV sphere and shade it smooth.", {"meshes": (1, 1), "smooth": 1},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nbpy.ops.object.shade_smooth()")
add(2, "Add a cylinder and shade it flat.", {"meshes": (1, 1)},
    "import bpy\nbpy.ops.mesh.primitive_cylinder_add()\nbpy.ops.object.shade_flat()")
add(2, "Add a monkey and shade it smooth with Subdivision Surface level 1.", {"meshes": (1, 1), "smooth": 1, "modifier": "SUBSURF"},
    "import bpy\nbpy.ops.mesh.primitive_monkey_add()\nbpy.ops.object.shade_smooth()\nm = bpy.context.object.modifiers.new('Subsurf','SUBSURF')\nm.levels = 1")
add(2, "Add a cube and then use cube projection UV mapping on it.", {"meshes": (1, 1), "uv": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.object.mode_set(mode='EDIT')\nbpy.ops.mesh.select_all(action='SELECT')\nbpy.ops.uv.cube_project()\nbpy.ops.object.mode_set(mode='OBJECT')")
add(2, "Unwrap a cylinder using the standard Unwrap operator after selecting all of its faces.", {"meshes": (1, 1), "uv": 1},
    "import bpy\nbpy.ops.mesh.primitive_cylinder_add()\nbpy.ops.object.mode_set(mode='EDIT')\nbpy.ops.mesh.select_all(action='SELECT')\nbpy.ops.uv.unwrap()\nbpy.ops.object.mode_set(mode='OBJECT')")
add(2, "Add a sphere and create a second UV map named Lightmap on its mesh.", {"meshes": (1, 1), "uv": 1},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nme = bpy.context.object.data\nif not me.uv_layers:\n    me.uv_layers.new(name='UVMap')\nme.uv_layers.new(name='Lightmap')")
add(2, "Add a cube, enter edit mode, and extrude the top face up by 2 units.", {"meshes": (1, 1), "verts_min": 12, "dim": (2, 3.9, 4.1)},
    "import bpy, bmesh\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\nbm = bmesh.new()\nbm.from_mesh(o.data)\ntop = max(bm.faces, key=lambda f: f.calc_center_median().z)\nr = bmesh.ops.extrude_face_region(bm, geom=[top])\nverts = [v for v in r['geom'] if isinstance(v, bmesh.types.BMVert)]\nbmesh.ops.translate(bm, vec=(0,0,2), verts=verts)\nbm.to_mesh(o.data)\nbm.free()")
add(2, "Add a plane and subdivide it twice using the Subdivide operator in edit mode.", {"meshes": (1, 1), "verts_min": 25},
    "import bpy\nbpy.ops.mesh.primitive_plane_add()\nbpy.ops.object.mode_set(mode='EDIT')\nbpy.ops.mesh.select_all(action='SELECT')\nbpy.ops.mesh.subdivide(number_cuts=3)\nbpy.ops.object.mode_set(mode='OBJECT')")
add(2, "Create a cube and bevel all its edges in edit mode with an offset of 0.1.", {"meshes": (1, 1), "verts_min": 24},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.object.mode_set(mode='EDIT')\nbpy.ops.mesh.select_all(action='SELECT')\nbpy.ops.mesh.bevel(offset=0.1)\nbpy.ops.object.mode_set(mode='OBJECT')")
add(2, "Add a cube, then inset each of its faces individually by 0.2 in edit mode.", {"meshes": (1, 1), "verts_min": 24},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.object.mode_set(mode='EDIT')\nbpy.ops.mesh.select_all(action='SELECT')\nbpy.ops.mesh.inset(thickness=0.2, use_individual=True)\nbpy.ops.object.mode_set(mode='OBJECT')")
add(2, "Add a cube and apply its scale after setting it to (3, 3, 3), so its scale reads 1 but it stays 6 units wide.", {"meshes": (1, 1), "bbox_x": (5.9, 6.1), "scale_near": (1, 1, 1)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.scale = (3,3,3)\nbpy.ops.object.transform_apply(scale=True)")
add(2, "Add a cube and set its origin to the geometry center after moving it to (5, 5, 5).", {"meshes": (1, 1), "loc_near": (5, 5, 5)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.location = (5,5,5)\nbpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')")
add(2, "Add a cube and duplicate it, moving the copy 3 units up the Z axis.", {"meshes": (2, 2), "loc_near": (0, 0, 3)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.object.duplicate()\nbpy.context.object.location.z = 3")
add(2, "Make two linked duplicates of a sphere, so all three share one mesh.", {"meshes": (3, 3)},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\nsrc = bpy.context.object\nfor i in (1, 2):\n    o = src.copy()\n    o.location.x = i*3\n    bpy.context.collection.objects.link(o)")
add(2, "Create two cubes and join them so there's a single mesh object, with a total of 16 vertices.", {"meshes": (1, 1), "verts_min": 16, "verts_max": 16},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(location=(-2,0,0))\nbpy.ops.mesh.primitive_cube_add(location=(2,0,0))\nfor o in bpy.data.objects: o.select_set(True)\nbpy.context.view_layer.objects.active = bpy.data.objects[0]\nbpy.ops.object.join()")
add(2, "Mirror a cube across the X axis by giving it a negative X scale and then applying the scale.", {"meshes": (1, 1)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(location=(2,0,0))\no = bpy.context.object\no.scale.x = -1\nbpy.ops.object.transform_apply(scale=True)")
add(2, "Add a cube and add an Empty at the same place, then give the cube a Child Of constraint targeting the empty.", {"meshes": (1, 1), "type_count": {"EMPTY": (1, 1)}, "constraint": "CHILD_OF"},
    "import bpy\nbpy.ops.object.empty_add(location=(0,0,0))\ne = bpy.context.object\nbpy.ops.mesh.primitive_cube_add()\nc = bpy.context.object.constraints.new('CHILD_OF')\nc.target = e")
add(2, "Add a cube with a Track To constraint that points at an empty at (0, 10, 0).", {"meshes": (1, 1), "type_count": {"EMPTY": (1, 1)}, "constraint": "TRACK_TO"},
    "import bpy\nbpy.ops.object.empty_add(location=(0,10,0))\ne = bpy.context.object\nbpy.ops.mesh.primitive_cube_add()\nc = bpy.context.object.constraints.new('TRACK_TO')\nc.target = e")
add(2, "Add a cube and limit its location so it can't go above z=4, using a constraint.", {"meshes": (1, 1), "constraint": "LIMIT_LOCATION"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nc = bpy.context.object.constraints.new('LIMIT_LOCATION')\nc.use_max_z = True\nc.max_z = 4")
add(2, "Add a sphere with two shape keys: the basis and one called Squash.", {"meshes": (1, 1), "shape_keys": 2},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\no = bpy.context.object\no.shape_key_add(name='Basis')\nk = o.shape_key_add(name='Squash')\nfor v in k.data:\n    v.co.z *= 0.5")
add(2, "Add a cube and make it a Boolean cutter: add a sphere, and give the cube a Boolean modifier with the difference operation against it.", {"meshes": (2, 2), "mod_prop": ("BOOLEAN", "operation", "DIFFERENCE")},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nc = bpy.context.object\nbpy.ops.mesh.primitive_uv_sphere_add(radius=0.8, location=(0.5,0.5,0.5))\ns = bpy.context.object\nm = c.modifiers.new('Bool','BOOLEAN')\nm.operation = 'DIFFERENCE'\nm.object = s\ns.hide_render = True")
add(2, "Add a cube, set its display type to wire, and hide it from rendering.", {"meshes": (1, 1), "hide_render": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.display_type = 'WIRE'\no.hide_render = True")

# ---- level 3 (b123+): animation, parenting, collections, scene setup, arrays of objects
add(3, "Animate a sphere bouncing: z=0 at frame 1, z=3 at frame 15 and back to z=0 at frame 30.", {"meshes": (1, 1), "animated": 1, "keyed": [1, 15, 30]},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\no = bpy.context.object\nfor f, z in ((1,0),(15,3),(30,0)):\n    o.location.z = z\n    o.keyframe_insert('location', index=2, frame=f)")
add(3, "Make a cube grow from scale 1 at frame 1 to scale 3 at frame 48.", {"meshes": (1, 1), "animated": 1, "keyed": [1, 48]},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.scale = (1,1,1)\no.keyframe_insert('scale', frame=1)\no.scale = (3,3,3)\no.keyframe_insert('scale', frame=48)")
add(3, "Set the timeline to run from frame 10 to frame 90, at 30 frames per second.", {"frame_start": 10, "frame_end": 90, "fps": 30},
    "import bpy\ns = bpy.context.scene\ns.frame_start = 10\ns.frame_end = 90\ns.render.fps = 30")
add(3, "Set the render resolution to 1280 by 720.", {"res": (1280, 720)},
    "import bpy\ns = bpy.context.scene\ns.render.resolution_x = 1280\ns.render.resolution_y = 720")
add(3, "Make a cone spin on the Z axis: rotation 0 degrees at frame 1 and 180 degrees at frame 24.", {"meshes": (1, 1), "animated": 1, "keyed": [1, 24]},
    "import bpy, math\nbpy.ops.mesh.primitive_cone_add()\no = bpy.context.object\no.rotation_euler.z = 0\no.keyframe_insert('rotation_euler', index=2, frame=1)\no.rotation_euler.z = math.radians(180)\no.keyframe_insert('rotation_euler', index=2, frame=24)")
add(3, "Add a camera that flies from (0, -10, 3) at frame 1 to (10, 0, 3) at frame 100.", {"camera": 1, "animated": 1, "keyed": [1, 100]},
    "import bpy\nbpy.ops.object.camera_add(location=(0,-10,3))\no = bpy.context.object\no.keyframe_insert('location', frame=1)\no.location = (10,0,3)\no.keyframe_insert('location', frame=100)\nbpy.context.scene.camera = o")
add(3, "Animate a point light's power from 0 at frame 1 to 500 at frame 30.", {"light": "POINT", "data_animated": 1},
    "import bpy\nbpy.ops.object.light_add(type='POINT')\nl = bpy.context.object.data\nl.energy = 0\nl.keyframe_insert('energy', frame=1)\nl.energy = 500\nl.keyframe_insert('energy', frame=30)")
add(3, "Animate a cube's X location with keyframes at frames 1, 25 and 50 with values 0, 5 and 0.", {"meshes": (1, 1), "animated": 1, "keyed": [1, 25, 50]},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\nfor f, x in ((1,0),(25,5),(50,0)):\n    o.location.x = x\n    o.keyframe_insert('location', index=0, frame=f)")
add(3, "Make an object orbit the origin: an empty named Pivot with a sphere parented to it, and rotate the empty from 0 to 360 degrees on Z across frames 1 to 120.", {"meshes": (1, 1), "parent_of": ("", "Pivot"), "animated": 1, "keyed": [1, 120]},
    "import bpy, math\nbpy.ops.object.empty_add()\np = bpy.context.object\np.name = 'Pivot'\nbpy.ops.mesh.primitive_uv_sphere_add(location=(4,0,0))\nbpy.context.object.parent = p\np.rotation_euler.z = 0\np.keyframe_insert('rotation_euler', index=2, frame=1)\np.rotation_euler.z = math.radians(360)\np.keyframe_insert('rotation_euler', index=2, frame=120)")
add(3, "Add a cube and a sphere; make the sphere a child of the cube.", {"meshes": (2, 2), "parented": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nc = bpy.context.object\nbpy.ops.mesh.primitive_uv_sphere_add(location=(0,0,2))\nbpy.context.object.parent = c")
add(3, "Create three cubes parented to a single empty called Group_A.", {"meshes": (3, 3), "parent_of": ("cube", "Group_A")},
    "import bpy\nbpy.ops.object.empty_add()\ne = bpy.context.object\ne.name = 'Group_A'\nfor i in range(3):\n    bpy.ops.mesh.primitive_cube_add(location=(i*3,0,0))\n    bpy.context.object.parent = e")
add(3, "Make a new collection named Lights and put a sun and a point light into it.", {"light": "SUN", "collection": "Lights", "type_count": {"LIGHT": (2, 2)}},
    "import bpy\nc = bpy.data.collections.new('Lights')\nbpy.context.scene.collection.children.link(c)\nfor t in ('SUN','POINT'):\n    bpy.ops.object.light_add(type=t)\n    o = bpy.context.object\n    for u in o.users_collection: u.objects.unlink(o)\n    c.objects.link(o)")
add(3, "Create two collections, Walls and Floor, each with one cube inside.", {"meshes": (2, 2), "collection": "Walls", "collections_min": 2},
    "import bpy\nfor n in ('Walls','Floor'):\n    c = bpy.data.collections.new(n)\n    bpy.context.scene.collection.children.link(c)\n    bpy.ops.mesh.primitive_cube_add()\n    o = bpy.context.object\n    for u in o.users_collection: u.objects.unlink(o)\n    c.objects.link(o)")
add(3, "Put a camera in a collection called Cameras and make that camera the active one.", {"camera": 1, "collection": "Cameras"},
    "import bpy\nc = bpy.data.collections.new('Cameras')\nbpy.context.scene.collection.children.link(c)\nbpy.ops.object.camera_add(location=(0,-8,3))\no = bpy.context.object\nfor u in o.users_collection: u.objects.unlink(o)\nc.objects.link(o)\nbpy.context.scene.camera = o")
add(3, "Build a three-point lighting setup: one sun light (key), one area light (fill) and one point light (rim).", {"light": "SUN", "type_count": {"LIGHT": (3, 3)}},
    "import bpy\nbpy.ops.object.light_add(type='SUN', location=(5,-5,6))\nbpy.ops.object.light_add(type='AREA', location=(-5,-4,3))\nbpy.ops.object.light_add(type='POINT', location=(0,6,4))")
add(3, "Set up a product shot: a sphere on a plane, a camera aimed at it and an area light above.", {"meshes": (2, 2), "camera": 1, "light": "AREA"},
    "import bpy\nbpy.ops.mesh.primitive_plane_add(size=10)\nbpy.ops.mesh.primitive_uv_sphere_add(location=(0,0,1))\nbpy.ops.object.light_add(type='AREA', location=(0,0,6))\nbpy.ops.object.camera_add(location=(0,-8,3), rotation=(1.3,0,0))\nbpy.context.scene.camera = bpy.context.object")
add(3, "Create a wall of bricks: 5 columns by 3 rows of cubes scaled to 2 by 1 by 1, all on the XZ plane.", {"meshes": (15, 15)},
    "import bpy\nfor r in range(3):\n    for c in range(5):\n        bpy.ops.mesh.primitive_cube_add(location=(c*2,0,r))\n        bpy.context.object.scale = (1,0.5,0.5)")
add(3, "Place 10 spheres along a straight line from (0,0,0) to (9,9,0), one per unit step.", {"meshes": (10, 10)},
    "import bpy\nfor i in range(10):\n    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(i,i,0))")
add(3, "Lay out a ring of 12 small cubes of side 0.5 around a circle of radius 6 in the XY plane.", {"meshes": (12, 12)},
    "import bpy, math\nfor i in range(12):\n    a = 2*math.pi*i/12\n    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(6*math.cos(a), 6*math.sin(a), 0))")
add(3, "Make a spiral of 20 spheres: each rises 0.3 higher and moves around a circle of radius 3.", {"meshes": (20, 20)},
    "import bpy, math\nfor i in range(20):\n    a = i*0.5\n    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(3*math.cos(a), 3*math.sin(a), i*0.3))")
add(3, "Create a checkerboard: an 8 by 8 grid of flat boxes, alternating between two materials named Dark and Light.", {"meshes": (64, 64), "mat_name": "Dark", "material": 64},
    "import bpy\nmats = [bpy.data.materials.new('Dark'), bpy.data.materials.new('Light')]\nmats[0].diffuse_color = (0.05,0.05,0.05,1)\nmats[1].diffuse_color = (0.95,0.95,0.95,1)\nfor x in range(8):\n    for y in range(8):\n        bpy.ops.mesh.primitive_cube_add(location=(x,y,0))\n        o = bpy.context.object\n        o.scale = (0.5,0.5,0.05)\n        o.data.materials.append(mats[(x+y)%2])")
add(3, "Add a plane as ground, scale it to 20 by 20 and add a sphere resting on it at z=1.", {"meshes": (2, 2), "bbox_x": (19.9, 20.1), "obj_at": ("sphere", (0, 0, 1))},
    "import bpy\nbpy.ops.mesh.primitive_plane_add(size=20)\nbpy.ops.mesh.primitive_uv_sphere_add(location=(0,0,1))")
add(3, "Make a pendulum: an empty at (0,0,5) as pivot, a thin cylinder rod of length 4 hanging under it and a sphere bob at the end, both parented to the pivot.", {"meshes": (2, 2), "type_count": {"EMPTY": (1, 1)}, "parented": 1},
    "import bpy\nbpy.ops.object.empty_add(location=(0,0,5))\np = bpy.context.object\nbpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=4, location=(0,0,3))\nbpy.context.object.parent = p\nbpy.ops.mesh.primitive_uv_sphere_add(radius=0.4, location=(0,0,1))\nbpy.context.object.parent = p")
add(3, "Swing the pendulum: build an empty named Pivot with a cube parented to it, then keyframe the empty's X rotation to -30 degrees at frame 1, 30 degrees at frame 30 and -30 degrees at frame 60.", {"meshes": (1, 1), "parent_of": ("", "Pivot"), "animated": 1, "keyed": [1, 30, 60]},
    "import bpy, math\nbpy.ops.object.empty_add()\np = bpy.context.object\np.name = 'Pivot'\nbpy.ops.mesh.primitive_cube_add(location=(0,0,-2))\nbpy.context.object.parent = p\nfor f, d in ((1,-30),(30,30),(60,-30)):\n    p.rotation_euler.x = math.radians(d)\n    p.keyframe_insert('rotation_euler', index=0, frame=f)")
add(3, "Animate a cube to move along a Bezier curve using a Follow Path constraint.", {"meshes": (1, 1), "curve": 1, "constraint": "FOLLOW_PATH"},
    "import bpy\nbpy.ops.curve.primitive_bezier_curve_add()\ncurve = bpy.context.object\nbpy.ops.mesh.primitive_cube_add()\nc = bpy.context.object.constraints.new('FOLLOW_PATH')\nc.target = curve")
add(3, "Make a sphere follow a cube: give the sphere a Copy Location constraint targeting the cube.", {"meshes": (2, 2), "constraint": "COPY_LOCATION"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(location=(3,0,0))\ncube = bpy.context.object\nbpy.ops.mesh.primitive_uv_sphere_add()\nc = bpy.context.object.constraints.new('COPY_LOCATION')\nc.target = cube")
add(3, "Add a camera aimed at a cube with a Track To constraint.", {"meshes": (1, 1), "camera": 1, "constraint": "TRACK_TO"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\ncube = bpy.context.object\nbpy.ops.object.camera_add(location=(0,-10,5))\ncam = bpy.context.object\nc = cam.constraints.new('TRACK_TO')\nc.target = cube\nc.track_axis = 'TRACK_NEGATIVE_Z'\nc.up_axis = 'UP_Y'\nbpy.context.scene.camera = cam")
add(3, "Set the render engine to Cycles with 64 samples.", {"engine": "CYCLES", "samples": 64},
    "import bpy\ns = bpy.context.scene\ns.render.engine = 'CYCLES'\ns.cycles.samples = 64")
add(3, "Set the render output to PNG at 50 percent resolution scale.", {"file_format": "PNG", "res_percent": 50},
    "import bpy\ns = bpy.context.scene\ns.render.image_settings.file_format = 'PNG'\ns.render.resolution_percentage = 50")
add(3, "Add a timeline marker named Start at frame 1 and one named End at frame 100.", {"markers": [1, 100]},
    "import bpy\nm = bpy.context.scene.timeline_markers\nm.new('Start', frame=1)\nm.new('End', frame=100)")
add(3, "Make a sphere that appears to blink: hide it from rendering at frame 10 and show it again at frame 20, using keyframes on its render visibility.", {"meshes": (1, 1), "animated": 1, "keyed": [10, 20]},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add()\no = bpy.context.object\no.hide_render = False\no.keyframe_insert('hide_render', frame=1)\no.hide_render = True\no.keyframe_insert('hide_render', frame=10)\no.hide_render = False\no.keyframe_insert('hide_render', frame=20)")
add(3, "Animate a material colour: a cube whose material diffuse colour goes from red at frame 1 to blue at frame 40.", {"meshes": (1, 1), "material": 1, "data_animated": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\nmat = bpy.data.materials.new('Fade')\nbpy.context.object.data.materials.append(mat)\nmat.diffuse_color = (1,0,0,1)\nmat.keyframe_insert('diffuse_color', frame=1)\nmat.diffuse_color = (0,0,1,1)\nmat.keyframe_insert('diffuse_color', frame=40)")
add(3, "Make a cube that moves in a square path: (0,0,0) then (4,0,0) then (4,4,0) then (0,4,0) then back, at frames 1, 20, 40, 60 and 80.", {"meshes": (1, 1), "animated": 1, "keyed": [1, 20, 40, 60, 80]},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\nfor f, p in ((1,(0,0,0)),(20,(4,0,0)),(40,(4,4,0)),(60,(0,4,0)),(80,(0,0,0))):\n    o.location = p\n    o.keyframe_insert('location', frame=f)")
add(3, "Set linear interpolation on a cube's X location animation from 0 to 5 over frames 1 to 40.", {"meshes": (1, 1), "animated": 1, "keyed": [1, 40]},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.keyframe_insert('location', frame=1)\no.location.x = 5\no.keyframe_insert('location', frame=40)\nact = o.animation_data.action\nfcs = act.fcurves if hasattr(act, 'fcurves') else [f for l in act.layers for s in l.strips for cb in s.channelbags for f in cb.fcurves]\nfor f in fcs:\n    for k in f.keyframe_points:\n        k.interpolation = 'LINEAR'")
add(3, "Create a simple solar system: a big sphere at the origin as the sun, and three smaller spheres at x=4, x=7 and x=10.", {"meshes": (4, 4), "loc_near": (7, 0, 0), "dim": (0, 3.9, 4.1)},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add(radius=2)\nfor r, x in ((0.4,4),(0.6,7),(0.5,10)):\n    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(x,0,0))")
add(3, "Set a gray world background and a sun light pointing down at an angle of 45 degrees on X.", {"light": "SUN", "world": 1, "rot_near": (0.7854, 0, 0)},
    "import bpy, math\nw = bpy.data.worlds.new('Studio')\nw.color = (0.3,0.3,0.3)\nbpy.context.scene.world = w\nbpy.ops.object.light_add(type='SUN', rotation=(math.radians(45),0,0))")
add(3, "Create a text object reading Title, put it inside a new collection named Text, and give it a material.", {"text": "Title", "collection": "Text"},
    "import bpy\nc = bpy.data.collections.new('Text')\nbpy.context.scene.collection.children.link(c)\nbpy.ops.object.text_add()\no = bpy.context.object\no.data.body = 'Title'\nfor u in o.users_collection: u.objects.unlink(o)\nc.objects.link(o)\nm = bpy.data.materials.new('TextMat')\no.data.materials.append(m)")
add(3, "Make a row of 6 cubes, each one scaled 20 percent bigger than the previous, starting at scale 1, 4 units apart.", {"meshes": (6, 6)},
    "import bpy\nfor i in range(6):\n    bpy.ops.mesh.primitive_cube_add(location=(i*4,0,0))\n    s = 1.2**i\n    bpy.context.object.scale = (s,s,s)")
add(3, "Duplicate a cylinder 4 times in a pyramid arrangement: 3 on the bottom row, 2 above and 1 at the top.", {"meshes": (6, 6)},
    "import bpy\nfor row, n in enumerate((3,2,1)):\n    for i in range(n):\n        bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1, location=((i-(n-1)/2)*1.2, 0, 0.5+row*1.1))")
add(3, "Animate the sun light's rotation to simulate a day: X rotation 0 at frame 1 and 180 degrees at frame 240.", {"light": "SUN", "animated": 1, "keyed": [1, 240]},
    "import bpy, math\nbpy.ops.object.light_add(type='SUN')\no = bpy.context.object\no.rotation_euler.x = 0\no.keyframe_insert('rotation_euler', index=0, frame=1)\no.rotation_euler.x = math.radians(180)\no.keyframe_insert('rotation_euler', index=0, frame=240)")
add(3, "Make a door: a box and a hinge empty on its left edge, parent the door to the hinge and open it 90 degrees at frame 30.", {"meshes": (1, 1), "type_count": {"EMPTY": (1, 1)}, "parented": 1, "animated": 1, "keyed": [30]},
    "import bpy, math\nbpy.ops.object.empty_add(location=(-0.5,0,0))\nh = bpy.context.object\nbpy.ops.mesh.primitive_cube_add(location=(0,0,1))\nd = bpy.context.object\nd.scale = (0.5,0.05,1)\nd.parent = h\nh.rotation_euler.z = 0\nh.keyframe_insert('rotation_euler', index=2, frame=1)\nh.rotation_euler.z = math.radians(90)\nh.keyframe_insert('rotation_euler', index=2, frame=30)")
add(3, "Generate 25 randomly placed cubes within a 10 by 10 area using a seeded random generator.", {"meshes": (25, 25)},
    "import bpy, random\nrandom.seed(1)\nfor i in range(25):\n    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(random.uniform(-5,5), random.uniform(-5,5), 0))")
add(3, "Set up a turntable: a monkey at the origin with an empty named Turn, parent the camera to the empty, and rotate the empty a full 360 degrees around Z over frames 1 to 96.", {"meshes": (1, 1), "camera": 1, "parent_of": ("", "Turn"), "animated": 1, "keyed": [1, 96]},
    "import bpy, math\nbpy.ops.mesh.primitive_monkey_add()\nbpy.ops.object.empty_add()\ne = bpy.context.object\ne.name = 'Turn'\nbpy.ops.object.camera_add(location=(0,-8,2), rotation=(1.4,0,0))\nbpy.context.object.parent = e\ne.rotation_euler.z = 0\ne.keyframe_insert('rotation_euler', index=2, frame=1)\ne.rotation_euler.z = math.radians(360)\ne.keyframe_insert('rotation_euler', index=2, frame=96)")

# ---- level 4 (b166+): composite models, plus geometry nodes / curves / text / boolean / UV
GN = ("import bpy\\n"
      "def gn_group(name='GN'):\\n"
      "    g = bpy.data.node_groups.new(name, 'GeometryNodeTree')\\n"
      "    g.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')\\n"
      "    g.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')\\n"
      "    return g\\n")
GN = GN.replace("\\n", "\n")

add(4, "Model a bookshelf: two side panels, a back panel and four shelves, all boxes. It should be about 2 tall.", {"meshes": (7, 12), "bbox_z": (1.8, 2.3)},
    "import bpy\ndef box(loc, sc):\n    bpy.ops.mesh.primitive_cube_add(location=loc)\n    bpy.context.object.scale = sc\nbox((-0.5,0,1),(0.025,0.2,1))\nbox((0.5,0,1),(0.025,0.2,1))\nbox((0,0.19,1),(0.5,0.01,1))\nfor z in (0.05,0.7,1.35,1.98):\n    box((0,0,z),(0.5,0.2,0.025))")
add(4, "Build a simple bed: a mattress box, a frame underneath, a headboard and a pillow.", {"meshes": (4, 6)},
    "import bpy\ndef box(loc, sc):\n    bpy.ops.mesh.primitive_cube_add(location=loc)\n    bpy.context.object.scale = sc\nbox((0,0,0.3),(1,2,0.15))\nbox((0,0,0.6),(0.95,1.95,0.15))\nbox((0,-2.05,0.9),(1,0.05,0.6))\nbox((0,-1.5,0.85),(0.5,0.25,0.1))")
add(4, "Make a traffic cone: a square base slab and a cone on top, and give both an orange material.", {"meshes": (2, 2), "material": 2, "mat_color": (1, 0.4, 0)},
    "import bpy\nmat = bpy.data.materials.new('Orange')\nmat.diffuse_color = (1,0.4,0,1)\nbpy.ops.mesh.primitive_cube_add(location=(0,0,0.05))\nbpy.context.object.scale = (0.4,0.4,0.05)\nbpy.context.object.data.materials.append(mat)\nbpy.ops.mesh.primitive_cone_add(radius1=0.3, radius2=0.04, depth=1.2, location=(0,0,0.7))\nbpy.context.object.data.materials.append(mat)")
add(4, "Create a low-poly tree: a brown cylinder trunk and three green cones stacked as foliage.", {"meshes": (4, 4), "material": 4, "bbox_z": (3.0, 5.0)},
    "import bpy\nbrown = bpy.data.materials.new('Trunk'); brown.diffuse_color = (0.3,0.15,0.05,1)\ngreen = bpy.data.materials.new('Leaf'); green.diffuse_color = (0.05,0.5,0.1,1)\nbpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.2, depth=1.5, location=(0,0,0.75))\nbpy.context.object.data.materials.append(brown)\nfor i, r in enumerate((1.2,0.9,0.6)):\n    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=r, depth=1.2, location=(0,0,1.8+i*0.8))\n    bpy.context.object.data.materials.append(green)")
add(4, "Make a low-poly car: a long box body, a smaller cabin box on top and four cylinder wheels turned on their sides.", {"meshes": (6, 6), "bbox_z": (1.0, 2.0)},
    "import bpy, math\nbpy.ops.mesh.primitive_cube_add(location=(0,0,0.6))\nbpy.context.object.scale = (2,0.9,0.35)\nbpy.ops.mesh.primitive_cube_add(location=(-0.2,0,1.15))\nbpy.context.object.scale = (1,0.8,0.25)\nfor x in (-1.3,1.3):\n    for y in (-0.95,0.95):\n        bpy.ops.mesh.primitive_cylinder_add(radius=0.4, depth=0.25, location=(x,y,0.4), rotation=(math.radians(90),0,0))")
add(4, "Build a simple rocket: a tall cylinder, a cone nose, and three fins around the base.", {"meshes": (5, 5), "bbox_z": (3.0, 5.0)},
    "import bpy, math\nbpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=3, location=(0,0,1.5))\nbpy.ops.mesh.primitive_cone_add(radius1=0.5, depth=1, location=(0,0,3.5))\nfor i in range(3):\n    a = i*2*math.pi/3\n    bpy.ops.mesh.primitive_cube_add(location=(0.7*math.cos(a),0.7*math.sin(a),0.4), rotation=(0,0,a))\n    bpy.context.object.scale = (0.3,0.03,0.4)")
add(4, "Make a robot from boxes: a body, a head with two eye spheres, two arms and two legs.", {"meshes": (8, 8)},
    "import bpy\ndef box(loc, sc):\n    bpy.ops.mesh.primitive_cube_add(location=loc)\n    bpy.context.object.scale = sc\nbox((0,0,1.5),(0.5,0.3,0.7))\nbox((0,0,2.6),(0.35,0.3,0.35))\nfor x in (-0.15,0.15):\n    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.06, location=(x,-0.3,2.65))\nfor x in (-0.75,0.75):\n    box((x,0,1.5),(0.12,0.12,0.6))\nfor x in (-0.25,0.25):\n    box((x,0,0.4),(0.15,0.15,0.4))")
add(4, "Create a low-poly character with a sphere head, a capsule-like body from a cylinder plus two spheres, and stubby cylinder arms and legs.", {"meshes": (8, 12)},
    "import bpy, math\nbpy.ops.mesh.primitive_uv_sphere_add(radius=0.4, location=(0,0,2.2))\nbpy.ops.mesh.primitive_cylinder_add(radius=0.4, depth=1, location=(0,0,1.3))\nfor z in (0.8,1.8):\n    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.4, location=(0,0,z))\nfor x in (-0.65,0.65):\n    bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=0.8, location=(x,0,1.3))\nfor x in (-0.2,0.2):\n    bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=0.6, location=(x,0,0.3))")
add(4, "Model a windmill: a tapered tower from a cone, a small cylinder hub on the front and four thin boxes as blades.", {"meshes": (6, 6)},
    "import bpy, math\nbpy.ops.mesh.primitive_cone_add(radius1=1.2, radius2=0.6, depth=4, location=(0,0,2))\nbpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=0.4, location=(0,-0.7,4), rotation=(math.radians(90),0,0))\nfor i in range(4):\n    a = i*math.pi/2\n    bpy.ops.mesh.primitive_cube_add(location=(1.2*math.sin(a),-1,4+1.2*math.cos(a)), rotation=(0,-a,0))\n    bpy.context.object.scale = (0.1,0.02,1.2)")
add(4, "Make a goalpost with two upright cylinders and a crossbar cylinder between them, standing 2.4 high and 7.3 wide.", {"meshes": (3, 3), "obj_at": ("cylinder", (-3.65, 0, 1.2))},
    "import bpy, math\nfor x in (-3.65,3.65):\n    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=2.4, location=(x,0,1.2))\nbpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=7.3, location=(0,0,2.4), rotation=(0,math.radians(90),0))")
add(4, "Build a simple bridge: a long flat deck, two arches made from half tori, and railings as thin boxes along both sides.", {"meshes": (5, 12)},
    "import bpy, math\nbpy.ops.mesh.primitive_cube_add(location=(0,0,0))\nbpy.context.object.scale = (6,1,0.15)\nfor x in (-3,3):\n    bpy.ops.mesh.primitive_torus_add(major_radius=2, minor_radius=0.15, location=(x,0,0), rotation=(math.radians(90),0,0))\nfor y in (-0.95,0.95):\n    bpy.ops.mesh.primitive_cube_add(location=(0,y,0.5))\n    bpy.context.object.scale = (6,0.03,0.3)")
add(4, "Make a mug: a cylinder body, a torus for the handle on one side, and a ceramic white material on both.", {"meshes": (2, 2), "material": 2, "mat_color": (1, 1, 1)},
    "import bpy, math\nm = bpy.data.materials.new('Ceramic')\nm.diffuse_color = (1,1,1,1)\nbpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1, location=(0,0,0.5))\nbpy.context.object.data.materials.append(m)\nbpy.ops.mesh.primitive_torus_add(major_radius=0.3, minor_radius=0.07, location=(0.6,0,0.5), rotation=(math.radians(90),0,0))\nbpy.context.object.data.materials.append(m)")
add(4, "Create a hollow cup by using a Boolean difference between a cylinder and a smaller cylinder inside it, then apply the Boolean.", {"meshes": (1, 2), "verts_min": 40},
    "import bpy\nbpy.ops.mesh.primitive_cylinder_add(radius=1, depth=2, location=(0,0,1))\ncup = bpy.context.object\nbpy.ops.mesh.primitive_cylinder_add(radius=0.85, depth=2, location=(0,0,1.2))\ncut = bpy.context.object\nm = cup.modifiers.new('Cut','BOOLEAN')\nm.operation = 'DIFFERENCE'\nm.object = cut\nm.solver = 'EXACT'\nbpy.context.view_layer.objects.active = cup\nbpy.ops.object.modifier_apply(modifier=m.name)\nbpy.data.objects.remove(cut)")
add(4, "Make a cube with a round hole through its centre along Z using a Boolean modifier and a cylinder cutter, leaving the cutter in the scene hidden from render.", {"meshes": (2, 2), "mod_prop": ("BOOLEAN", "operation", "DIFFERENCE"), "hide_render": 1},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(size=2)\nc = bpy.context.object\nbpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=4)\nh = bpy.context.object\nh.hide_render = True\nh.display_type = 'WIRE'\nm = c.modifiers.new('Hole','BOOLEAN')\nm.operation = 'DIFFERENCE'\nm.object = h")
add(4, "Model a dice: a bevelled cube with a pip-sized sphere stuck into the top face, plus a white material.", {"meshes": (2, 2), "modifier": "BEVEL", "material": 1},
    "import bpy\nm = bpy.data.materials.new('White'); m.diffuse_color = (1,1,1,1)\nbpy.ops.mesh.primitive_cube_add(size=2)\nc = bpy.context.object\nc.modifiers.new('Bevel','BEVEL').width = 0.1\nc.data.materials.append(m)\nbpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(0,0,1))")
add(4, "Make a donut: a torus with a slightly squashed Z scale, a pink icing disk on top (a flattened torus), and Subdivision Surface on both.", {"meshes": (2, 2), "mod_count": ("SUBSURF", 2)},
    "import bpy\nbpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=0.45)\nd = bpy.context.object\nd.scale.z = 0.8\nd.modifiers.new('S','SUBSURF')\nbpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=0.4, location=(0,0,0.15))\ni = bpy.context.object\ni.scale.z = 0.5\ni.modifiers.new('S','SUBSURF')\nm = bpy.data.materials.new('Icing'); m.diffuse_color = (1,0.4,0.6,1)\ni.data.materials.append(m)")
add(4, "Build a pyramid out of 4 rows of cubes: 16 cubes on the bottom (4 by 4), then 9, 4 and 1 above.", {"meshes": (30, 30)},
    "import bpy\nfor level, n in enumerate((4,3,2,1)):\n    off = (n-1)/2\n    for x in range(n):\n        for y in range(n):\n            bpy.ops.mesh.primitive_cube_add(location=(x-off, y-off, level+0.5))")
add(4, "Create a castle tower: a tall cylinder with a cone roof and eight small boxes around the top as battlements.", {"meshes": (10, 10)},
    "import bpy, math\nbpy.ops.mesh.primitive_cylinder_add(radius=1.5, depth=6, location=(0,0,3))\nbpy.ops.mesh.primitive_cone_add(radius1=1.7, depth=2, location=(0,0,7))\nfor i in range(8):\n    a = i*math.pi/4\n    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(1.5*math.cos(a),1.5*math.sin(a),6.2))")
add(4, "Make a street lamp: a thin tall pole, a horizontal arm at the top, a lamp-head sphere at the arm's end, and a point light inside the sphere.", {"meshes": (3, 3), "light": "POINT"},
    "import bpy, math\nbpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=5, location=(0,0,2.5))\nbpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=1.2, location=(0.6,0,5), rotation=(0,math.radians(90),0))\nbpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, location=(1.2,0,4.95))\nbpy.ops.object.light_add(type='POINT', location=(1.2,0,4.95))")
add(4, "Build a simple boat: a flattened, elongated hull from a scaled sphere, a mast cylinder and a triangular sail from a cone squashed flat.", {"meshes": (3, 3)},
    "import bpy\nbpy.ops.mesh.primitive_uv_sphere_add(location=(0,0,0))\nbpy.context.object.scale = (2,0.8,0.4)\nbpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=3, location=(0,0,1.5))\nbpy.ops.mesh.primitive_cone_add(vertices=3, radius1=1, depth=0.02, location=(0.5,0,1.8))\nbpy.context.object.scale = (1,1,1)")
add(4, "Create a satellite: a cube body, two flat panel boxes on each side and a small dish made from a flattened cone on top.", {"meshes": (4, 4)},
    "import bpy\nbpy.ops.mesh.primitive_cube_add(location=(0,0,0))\nfor x in (-2.2,2.2):\n    bpy.ops.mesh.primitive_cube_add(location=(x,0,0))\n    bpy.context.object.scale = (1.2,0.8,0.03)\nbpy.ops.mesh.primitive_cone_add(radius1=0.7, depth=0.3, location=(0,0,1.2))")
add(4, "Make a cactus: one tall green capsule from a cylinder and two spheres, with two smaller arms made the same way.", {"meshes": (9, 9), "material": 9},
    "import bpy, math\nmat = bpy.data.materials.new('Cactus'); mat.diffuse_color = (0.1,0.5,0.1,1)\ndef cap(loc, r, h, rot=(0,0,0)):\n    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, rotation=rot)\n    bpy.context.object.data.materials.append(mat)\n    for s in (-1,1):\n        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(loc[0], loc[1], loc[2]+s*h/2))\n        bpy.context.object.data.materials.append(mat)\ncap((0,0,1.5),0.3,3)\ncap((0.7,0,1.8),0.15,1)\ncap((-0.7,0,1.4),0.15,1)")
add(4, "Create a wine glass: a thin cylinder stem, a wide flat disc base and a cone-shaped bowl on top, ending around 1.6 tall.", {"meshes": (3, 3), "bbox_z": (1.4, 1.9)},
    "import bpy\nbpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=0.05, location=(0,0,0.025))\nbpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.8, location=(0,0,0.45))\nbpy.ops.mesh.primitive_cone_add(radius1=0.1, radius2=0.45, depth=0.8, location=(0,0,1.25))")
add(4, "Using a Curve object, make a Bezier circle with a bevel depth of 0.1 so it becomes a pipe ring.", {"curve": 1, "data_prop": ("CURVE", "bevel_depth", 0.1)},
    "import bpy\nbpy.ops.curve.primitive_bezier_circle_add(radius=2)\nbpy.context.object.data.bevel_depth = 0.1")
add(4, "Create a Bezier curve and extrude it by 0.5 so it has a ribbon shape.", {"curve": 1, "data_prop": ("CURVE", "extrude", 0.5)},
    "import bpy\nbpy.ops.curve.primitive_bezier_curve_add()\nbpy.context.object.data.extrude = 0.5")
add(4, "Make a text object with the word WELCOME, extruded by 0.2 and beveled slightly.", {"text": "WELCOME", "data_prop": ("FONT", "extrude", 0.2)},
    "import bpy\nbpy.ops.object.text_add()\no = bpy.context.object\no.data.body = 'WELCOME'\no.data.extrude = 0.2\no.data.bevel_depth = 0.02")
add(4, "Create text reading OPEN, then convert it to a mesh.", {"meshes": (1, 1), "verts_min": 20},
    "import bpy\nbpy.ops.object.text_add()\nbpy.context.object.data.body = 'OPEN'\nbpy.ops.object.convert(target='MESH')")
add(4, "Make a spring: a helix curve built with a Python-generated poly spline of 60 points, with bevel depth 0.05 on the curve data.", {"curve": 1, "data_prop": ("CURVE", "bevel_depth", 0.05)},
    "import bpy, math\ncu = bpy.data.curves.new('Spring', 'CURVE')\ncu.dimensions = '3D'\nsp = cu.splines.new('POLY')\nsp.points.add(59)\nfor i, p in enumerate(sp.points):\n    a = i*0.5\n    p.co = (math.cos(a), math.sin(a), i*0.08, 1)\ncu.bevel_depth = 0.05\no = bpy.data.objects.new('Spring', cu)\nbpy.context.collection.objects.link(o)")
add(4, "Make a Geometry Nodes modifier on a plane that uses an empty node group (just group input and group output).", {"meshes": (1, 1), "modifier": "NODES", "node_groups": 1},
    GN + "bpy.ops.mesh.primitive_plane_add()\no = bpy.context.object\ng = gn_group()\ng.nodes.new('NodeGroupInput')\ng.nodes.new('NodeGroupOutput')\no.modifiers.new('GeometryNodes','NODES').node_group = g")
add(4, "Build a Geometry Nodes setup on a cube that subdivides the mesh with a Subdivide Mesh node, level 2.", {"meshes": (1, 1), "modifier": "NODES", "node_groups": 1},
    GN + "bpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\ng = gn_group()\nn_in = g.nodes.new('NodeGroupInput')\nn_out = g.nodes.new('NodeGroupOutput')\nsub = g.nodes.new('GeometryNodeSubdivideMesh')\nsub.inputs['Level'].default_value = 2\ng.links.new(n_in.outputs[0], sub.inputs['Mesh'])\ng.links.new(sub.outputs['Mesh'], n_out.inputs[0])\no.modifiers.new('GeometryNodes','NODES').node_group = g")
add(4, "Create a Geometry Nodes tree on a plane that scatters points on its surface using Distribute Points on Faces and instances small cubes there.", {"meshes": (1, 1), "modifier": "NODES", "node_groups": 1},
    GN + "bpy.ops.mesh.primitive_plane_add(size=10)\no = bpy.context.object\ng = gn_group()\nn_in = g.nodes.new('NodeGroupInput')\nn_out = g.nodes.new('NodeGroupOutput')\nd = g.nodes.new('GeometryNodeDistributePointsOnFaces')\ncube = g.nodes.new('GeometryNodeMeshCube')\ncube.inputs['Size'].default_value = (0.2,0.2,0.2)\ninst = g.nodes.new('GeometryNodeInstanceOnPoints')\ng.links.new(n_in.outputs[0], d.inputs['Mesh'])\ng.links.new(d.outputs['Points'], inst.inputs['Points'])\ng.links.new(cube.outputs['Mesh'], inst.inputs['Instance'])\ng.links.new(inst.outputs['Instances'], n_out.inputs[0])\no.modifiers.new('Scatter','NODES').node_group = g")
add(4, "Make a Geometry Nodes group that outputs a UV sphere of radius 2 (no input mesh needed), and attach it to an empty-mesh object.", {"modifier": "NODES", "node_groups": 1},
    GN + "me = bpy.data.meshes.new('Empty')\no = bpy.data.objects.new('Gen', me)\nbpy.context.collection.objects.link(o)\ng = gn_group()\nn_out = g.nodes.new('NodeGroupOutput')\ns = g.nodes.new('GeometryNodeMeshUVSphere')\ns.inputs['Radius'].default_value = 2\ng.links.new(s.outputs['Mesh'], n_out.inputs[0])\no.modifiers.new('GN','NODES').node_group = g")
add(4, "Add a plane, a Geometry Nodes modifier with a Set Position node that raises every vertex by 1 on Z.", {"meshes": (1, 1), "modifier": "NODES", "node_groups": 1},
    GN + "bpy.ops.mesh.primitive_plane_add()\no = bpy.context.object\ng = gn_group()\nn_in = g.nodes.new('NodeGroupInput')\nn_out = g.nodes.new('NodeGroupOutput')\nsp = g.nodes.new('GeometryNodeSetPosition')\nsp.inputs['Offset'].default_value = (0,0,1)\ng.links.new(n_in.outputs[0], sp.inputs['Geometry'])\ng.links.new(sp.outputs['Geometry'], n_out.inputs[0])\no.modifiers.new('Raise','NODES').node_group = g")
add(4, "Build a ladder with two long vertical cylinders and seven horizontal rungs between them, using a loop for the rungs.", {"meshes": (9, 9)},
    "import bpy, math\nfor x in (-0.4,0.4):\n    bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=3, location=(x,0,1.5))\nfor i in range(7):\n    bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.8, location=(0,0,0.3+i*0.4), rotation=(0,math.radians(90),0))")
add(4, "Make a fence: 8 vertical posts spaced 1 unit apart plus two long horizontal rails running through them.", {"meshes": (10, 10)},
    "import bpy\nfor i in range(8):\n    bpy.ops.mesh.primitive_cube_add(location=(i,0,0.6))\n    bpy.context.object.scale = (0.05,0.05,0.6)\nfor z in (0.4,0.9):\n    bpy.ops.mesh.primitive_cube_add(location=(3.5,0,z))\n    bpy.context.object.scale = (3.6,0.02,0.05)")
add(4, "Model a simple sofa: a base block, a backrest block, two armrest blocks and three seat cushions, in a grey fabric material.", {"meshes": (7, 8), "material": 7, "mat_color": (0.5, 0.5, 0.5)},
    "import bpy\nmat = bpy.data.materials.new('Fabric'); mat.diffuse_color = (0.5,0.5,0.5,1)\ndef box(loc, sc):\n    bpy.ops.mesh.primitive_cube_add(location=loc)\n    bpy.context.object.scale = sc\n    bpy.context.object.data.materials.append(mat)\nbox((0,0,0.25),(1.5,0.5,0.25))\nbox((0,0.45,0.8),(1.5,0.1,0.4))\nfor x in (-1.6,1.6):\n    box((x,0,0.5),(0.1,0.5,0.4))\nfor x in (-1,0,1):\n    box((x,-0.05,0.6),(0.45,0.4,0.1))")
add(4, "Create a clock: a thin cylinder face, a torus rim, and two thin boxes for hour and minute hands pointing different directions.", {"meshes": (4, 4)},
    "import bpy, math\nbpy.ops.mesh.primitive_cylinder_add(radius=1, depth=0.1, rotation=(math.radians(90),0,0))\nbpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=0.06, rotation=(math.radians(90),0,0))\nbpy.ops.mesh.primitive_cube_add(location=(0,-0.1,0.3))\nbpy.context.object.scale = (0.03,0.02,0.3)\nbpy.ops.mesh.primitive_cube_add(location=(0.3,-0.12,0), rotation=(0,math.radians(90),0))\nbpy.context.object.scale = (0.02,0.02,0.4)")
add(4, "Make a UV-mapped crate: a cube beveled with a small bevel modifier, unwrapped with Smart UV Project, and named Crate_UV.", {"meshes": (1, 1), "uv": 1, "modifier": "BEVEL", "name": "Crate_UV"},
    "import bpy\nbpy.ops.mesh.primitive_cube_add()\no = bpy.context.object\no.name = 'Crate_UV'\nbpy.ops.object.mode_set(mode='EDIT')\nbpy.ops.mesh.select_all(action='SELECT')\nbpy.ops.uv.smart_project()\nbpy.ops.object.mode_set(mode='OBJECT')\no.modifiers.new('Bevel','BEVEL').width = 0.05")
add(4, "Build a 5-step spiral staircase: each step a flat box, rotated 30 degrees more than the last and rising 0.3, around a central pole.", {"meshes": (6, 6)},
    "import bpy, math\nbpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=2, location=(0,0,1))\nfor i in range(5):\n    a = math.radians(30*i)\n    bpy.ops.mesh.primitive_cube_add(location=(0.7*math.cos(a), 0.7*math.sin(a), 0.2+i*0.3), rotation=(0,0,a))\n    bpy.context.object.scale = (0.7,0.3,0.05)")
add(4, "Make a snowflake-like star: 6 thin boxes radiating from the centre, each rotated 60 degrees apart around Z.", {"meshes": (6, 6)},
    "import bpy, math\nfor i in range(6):\n    bpy.ops.mesh.primitive_cube_add(rotation=(0,0,math.radians(60*i)))\n    bpy.context.object.scale = (1.5,0.05,0.05)")
add(4, "Create a Saturn model: a sphere for the planet and a flat wide torus as the rings tilted by 20 degrees.", {"meshes": (2, 2), "rot_near": (0.349, 0, 0)},
    "import bpy, math\nbpy.ops.mesh.primitive_uv_sphere_add(radius=1)\nbpy.ops.mesh.primitive_torus_add(major_radius=2, minor_radius=0.1, rotation=(math.radians(20),0,0))\nbpy.context.object.scale.z = 0.3")
