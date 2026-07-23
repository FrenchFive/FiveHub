# FIVE HUB — pipeline HDA library

Drop `.hda` files in this folder and they load in **every** Houdini session
automatically — no install step. This works because the FiveHub package
puts `$FIVEHUB/houdini` on `HOUDINI_PATH`, and Houdini's default HDA scan
path includes every `<HOUDINI_PATH>/otls` directory.

Use it for the tools you build as the pipeline grows: a custom FileCache,
loaders, exporters, QC gadgets. Commit the `.hda`, everyone has it on next
launch (git mode: after their next pull).

Rules of thumb:
- One operator per file, named like `fivehub_filecache.hda`, so git diffs
  and versioning stay per-tool.
- Save HDAs with *Save Operator Type* onto files here — embedded ("Embedded"
  library) definitions can't be shared.
- Show-specific HDAs don't belong here — publish those into their project
  (format `hda`); FiveHub installs a project's published HDAs automatically
  when you open one of its scenes.
