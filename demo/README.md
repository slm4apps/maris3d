# Demo

What version 0.1 built, as files you can open: the Blender scene itself, the same scene as `.glb`
and `.fbx` for other programs, and the text that was typed to make it.

| folder | what | made by |
|---|---|---|
| [christmas-street/](christmas-street/README.md) | the street of the demo videos: 31 things, 1,132 objects | 204 one-shape prompts to the model plus 714 rows run by the recording driver, all listed |

Each folder's README says plainly which part the model did and which part code did.

## Tools

```sh
# write scene.blend, scene.glb, scene.fbx, objects/<Name>.glb/.fbx and objects.json for a scene
blender -b <scene.blend> --python demo/tools/export_scene.py -- <out folder>
# open every exported file once and count what is in it
blender -b --factory-startup --python demo/tools/check_files.py -- <out folder>
```

The exporter saves the scene again from a neutral folder first, because a `.blend` and an FBX
otherwise carry the folder and user name of the machine they were made on.
