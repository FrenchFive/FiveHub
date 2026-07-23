"""Demo publishes, so the app and the pipeline can be exercised without a DCC.

``run_demo`` publishes a clean crate (PASS), a second variant of it, and then
attempts a deliberately broken asset (unwelded, unassigned faces, bad name)
whose failed report lands in the publish log — one of each state the UI shows.
"""

import os

from . import config
from .geometry import MaterialData, MeshData, PublishRequest, SourceInfo
from .publish import publish
from .thumbs import write_placeholder_png


def cube_mesh(name="crate", size=1.0, material="M_DemoWood", welded=True):
    half = size * 0.5
    points = [
        (-half, 0.0, -half), (half, 0.0, -half), (half, 0.0, half), (-half, 0.0, half),
        (-half, size, -half), (half, size, -half), (half, size, half), (-half, size, half),
    ]
    faces = [
        (1, 0, 3, 2),  # bottom
        (4, 5, 6, 7),  # top
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    if welded:
        counts = [4] * len(faces)
        indices = [i for face in faces for i in face]
    else:
        # Every face gets its own copy of its points — classic unwelded export.
        counts, indices, split = [], [], []
        for face in faces:
            counts.append(4)
            for i in face:
                indices.append(len(split))
                split.append(points[i])
        points = split
    return MeshData(
        name=name,
        points=points,
        face_vertex_counts=counts,
        face_vertex_indices=indices,
        face_materials=[material] * len(counts),
        display_color=(0.85, 0.85, 0.85),
    )


def _thumbnail(root, name):
    path = os.path.join(config.exchange_path(root), "%s_thumb.png" % name)
    return write_placeholder_png(path)


def run_demo(hub_root=None):
    root = config.ensure_hub(hub_root)
    results = []

    wood = {"M_DemoWood": MaterialData("M_DemoWood", base_color=(0.55, 0.4, 0.25), roughness=0.7)}
    source = SourceInfo(dcc="demo", scene="fivehub.demo", nodes=["crate"])

    results.append(
        publish(
            PublishRequest(
                asset_name="DemoCrate",
                project="Demo",
                comment="Demo publish from fivehub.demo",
                meshes=[cube_mesh()],
                materials=wood,
                thumbnail=_thumbnail(root, "DemoCrate"),
                source=source,
            ),
            hub_root=root,
        )
    )

    dark = {"M_DemoDark": MaterialData("M_DemoDark", base_color=(0.1, 0.1, 0.1), roughness=0.4)}
    results.append(
        publish(
            PublishRequest(
                asset_name="DemoCrate",
                project="Demo",
                variant="dark",
                comment="Dark variant",
                meshes=[cube_mesh(material="M_DemoDark")],
                materials=dark,
                thumbnail=_thumbnail(root, "DemoCrateDark"),
                source=source,
            ),
            hub_root=root,
        )
    )

    # Broken on purpose: unwelded points, no materials, styleless name.
    broken = cube_mesh(name="mesh1", welded=False)
    broken.face_materials = None
    results.append(
        publish(
            PublishRequest(
                asset_name="broken_asset",
                project="Demo",
                comment="This one is supposed to fail validation",
                meshes=[broken],
                source=source,
            ),
            hub_root=root,
        )
    )

    return results
