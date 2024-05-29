selected_nodes = hou.selectedNodes()
file_path = "/path/to/your/output/file.hip"
hou.hipFile.saveChildrenToFile(selected_nodes, file_path)

edited_file_path = "/path/to/your/edited/file.hip"
loaded_nodes = hou.hipFile.loadChildrenFromFile(edited_file_path)
