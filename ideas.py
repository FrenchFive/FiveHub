import hou

# Step 1: Save Selected Nodes to a HIP File
selected_nodes = hou.selectedNodes()
file_path = "/path/to/your/output/file.hip"
hou.hipFile.saveChildrenToFile(selected_nodes, file_path)

# (Manual or automated editing of the HIP file happens here)

# Step 3: Load Edited Nodes into an Existing Scene
edited_file_path = "/path/to/your/edited/file.hip"
loaded_nodes = hou.hipFile.loadChildrenFromFile(edited_file_path)


# CHECK FOR FILES
import hou

def extract_file_paths_from_hip(file_path, extensions=(".abc", ".obj", ".fbx")):

    # Set Houdini to manual update mode
    hou.setUpdateMode(hou.updateMode.Manual)
    
    # Load the HIP file
    hou.hipFile.load(file_path)
    
    # List to store extracted file paths
    file_paths = []

    # Traverse all nodes in the scene
    for node in hou.node("/").allSubChildren():
        # Check each parameter in the node
        for parm in node.parms():
            # Check if the parameter is a file path
            if parm.parmTemplate().type() == hou.parmTemplateType.String:
                value = parm.eval()
                if isinstance(value, str) and any(value.endswith(ext) for ext in extensions):
                    file_paths.append(value)
                    hou.session.getenv("HIP")
    
    # Set Houdini back to the normal update mode
    hou.setUpdateMode(hou.updateMode.AutoUpdate)

    return file_paths

# Example usage
hip_file_path = '/path/to/your/file.hip'
paths = extract_file_paths_from_hip(hip_file_path)

for path in paths:
    print(path)
