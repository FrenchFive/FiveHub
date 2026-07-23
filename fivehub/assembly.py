"""Shot assembly: publish one USD layer that references everything a task
imported from the hub.

Imports made through FiveHub are tracked as dependencies (with or without a
version pin). ``publish_assembly`` turns a task's tracked USD dependencies
into a published assembly layer — unpinned dependencies reference the
source's root interface (they follow the latest), pinned ones reference the
exact version entry. Loading the assembly in Solaris brings in the whole
shot.
"""

import os
import shutil

from . import config
from .naming import make_identifier
from .report import RuleResult, Status, ValidationReport
from .usdlayers import write_assembly_layer
from .user import get_user


def _source_layer(project, dependency):
    """Absolute path of the layer a dependency should reference."""
    context = project.db.task_context(dependency["src_task_id"])
    if context is None:
        return None
    publish_root = project.publish_dir(
        context["kind"], context["entity"], context["task"], "usd"
    )
    if dependency["src_version"]:
        row = project.db.get_publish(
            dependency["src_task_id"], "usd", dependency["src_version"]
        )
        if row and row.get("path"):
            return project.absolute(row["path"])
        return None
    root_layer = os.path.join(publish_root, "%s.usda" % dependency["src_name"])
    return root_layer if os.path.isfile(root_layer) else None


def publish_assembly(project, entity, task, kind="shot", comment="", user=""):
    """Publish the assembly layer for a task from its tracked dependencies."""
    task_record = project._task_record(kind, entity, task)
    dependencies = [
        dep for dep in project.db.dependencies_of(task_record["id"])
        if dep["src_format"] == "usd"
    ]
    if not dependencies:
        raise ValueError(
            "no tracked USD dependencies on %s/%s — import published assets "
            "into this task first (imports through FIVE HUB are tracked)"
            % (entity, task)
        )

    user = user or get_user()
    name = "%s_assembly" % entity
    version = project.claim_publish(kind, entity, task, name, "usd", "default", user)
    label = config.version_label(version)
    version_dir = os.path.join(project.publish_dir(kind, entity, task, "usd"), label)

    try:
        os.makedirs(version_dir)
        references = []
        used_names = set()
        resolved = 0
        for dependency in dependencies:
            layer = _source_layer(project, dependency)
            if layer is None:
                continue
            resolved += 1
            child = make_identifier(
                "%s_%s" % (dependency["src_entity"], dependency["src_name"])
            )
            while child in used_names:
                child += "_1"
            used_names.add(child)
            relative = os.path.relpath(layer, version_dir).replace(os.sep, "/")
            references.append((child, relative))
        if not references:
            raise ValueError(
                "none of the tracked dependencies resolve to a published layer"
            )

        layer_path = write_assembly_layer(
            os.path.join(version_dir, "%s.usda" % name),
            entity,
            references,
            custom={
                "comment": comment or "",
                "publishedBy": user,
                "context": "%s / %s %s / %s" % (project.name, kind, entity, task),
            },
        )

        report = ValidationReport(asset_name=name, project=project.name, user=user)
        report.results.append(
            RuleResult(
                "assembly.references",
                "Tracked dependencies resolve to published layers",
                "error",
                Status.PASS,
                ["%d of %d dependencies referenced" % (len(references), len(dependencies))],
            )
        )
        report_path = report.save(os.path.join(version_dir, config.REPORT_FILE))
    except Exception:
        project.release_publish(kind, entity, task, "usd", version)
        shutil.rmtree(version_dir, ignore_errors=True)
        raise

    project.complete_publish(
        kind, entity, task, "usd", version, report,
        path=layer_path, report_path=report_path,
        comment=comment or "assembly of %d reference(s)" % len(references),
        user=user,
    )
    return {
        "name": name,
        "version": version,
        "version_label": label,
        "layer": layer_path,
        "references": len(references),
        "report_path": report_path,
    }
