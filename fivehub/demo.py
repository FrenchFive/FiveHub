"""Demo project, so the app and the pipeline can be exercised without Houdini.

``run_demo`` builds a project with assets, a shot and tasks, then publishes:
a clean USD crate (PASS), a dark variant of it (PASS), a deliberately broken
tree (FAIL — unwelded, no materials) and a bgeo cache on the shot's fx task —
one of every state the UI shows.
"""

import os

from . import config
from .geometry import MaterialData, MeshData, PublishRequest, SourceInfo
from .project import create_project, get_project
from .publish import FilePublishRequest, publish_files, publish_usd
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
    source = SourceInfo(dcc="demo", scene="fivehub.demo", user="demo")

    try:
        project = get_project("DemoProject", root)
    except ValueError:
        project = create_project("DemoProject", hub_root=root)

    for kind, entity, tasks in (
        ("asset", "DemoCrate", ("modeling", "lookdev")),
        ("asset", "DemoTree", ("modeling",)),
        ("shot", "SH010", ("layout", "fx")),
    ):
        if project.db.get_entity(kind, entity) is None:
            project.create_entity(kind, entity)
        for task in tasks:
            entity_id = project.db.get_entity(kind, entity)["id"]
            if project.db.get_task(entity_id, task) is None:
                project.create_task(kind, entity, task)

    results = []
    wood = {"M_DemoWood": MaterialData("M_DemoWood", base_color=(0.55, 0.4, 0.25), roughness=0.7)}
    results.append(
        publish_usd(
            project, "asset", "DemoCrate", "modeling",
            PublishRequest(
                asset_name="DemoCrate",
                comment="Demo publish from fivehub.demo",
                meshes=[cube_mesh()],
                materials=wood,
                thumbnail=_thumbnail(root, "DemoCrate"),
                source=source,
            ),
        )
    )

    dark = {"M_DemoDark": MaterialData("M_DemoDark", base_color=(0.1, 0.1, 0.1), roughness=0.4)}
    results.append(
        publish_usd(
            project, "asset", "DemoCrate", "modeling",
            PublishRequest(
                asset_name="DemoCrate",
                variant="dark",
                comment="Dark variant",
                meshes=[cube_mesh(material="M_DemoDark")],
                materials=dark,
                thumbnail=_thumbnail(root, "DemoCrateDark"),
                source=source,
            ),
        )
    )

    # Broken on purpose: unwelded points, no materials.
    broken = cube_mesh(name="tree", welded=False)
    broken.face_materials = None
    results.append(
        publish_usd(
            project, "asset", "DemoTree", "modeling",
            PublishRequest(
                asset_name="DemoTree",
                comment="This one is supposed to fail validation",
                meshes=[broken],
                source=source,
            ),
        )
    )

    # A file-format publish on the shot's fx task.
    cache = os.path.join(config.exchange_path(root), "demo_smoke.vdb")
    with open(cache, "wb") as handle:
        handle.write(b"FIVEHUB DEMO VDB PLACEHOLDER")
    results.append(
        publish_files(
            project, "shot", "SH010", "fx",
            FilePublishRequest(
                asset_name="SH010",
                format="vdb",
                files=[cache],
                comment="Demo smoke cache",
                thumbnail=_thumbnail(root, "SH010"),
                source=source,
            ),
        )
    )

    return [result.to_dict() for result in results]
