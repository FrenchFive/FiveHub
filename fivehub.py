import hou
import os
import re
import shutil

import fivedb
import fiveinterface

import uuid

def reload():
    import fivehub
    import fivedb
    import fiveinterface
    import importlib
    importlib.reload(fivehub)
    importlib.reload(fivedb)
    importlib.reload(fiveinterface)

def add():
    # Get selected nodes
    nodes = hou.selectedNodes()
    
    # Check if nodes are selected
    if not nodes:
        hou.ui.displayMessage("PLEASE SELECT A NODE")
        return
    
    #check if the selected node is a geo node
    for node in nodes:
        if not node.type().name() == "geo":
            hou.ui.displayMessage("PLEASE SELECT A GEO NODE")
            return
    
    #INTERFACE
    name, project = fiveinterface.addwindow()

    if name == None and project == None:
        return

    #change node name to asset name
    for i in range(len(nodes)):
        if len(nodes) == 1:
            node.setName(f"FH_{name}")
        else:
            node.setName(f"FH_{name}_{i}")
    
    #Hide all other nodes except the selected nodes
    for node in hou.node("/obj").children():
        if node not in nodes:
            # set node display flag to false
            node.setDisplayFlag(False)

    #RESETTING VIEWPORT
    scene_viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    viewport = scene_viewer.curViewport()
    viewport.home()
    viewport.frameSelected()

    #SET VIEWPORT TO SMOOTH SHADED
    settings = viewport.settings()
    scnset = settings.displaySet(hou.displaySetType.SceneObject)
    scnset.setShadingModeLocked(False)
    scnset.setShadedMode(hou.glShadingType.Smooth)

    #SET VIEWPORT LIGHT TO HEADLIGHT
    settings.setLighting(hou.viewportLighting.Headlight)


    #DATABASE
    id = fivedb.add_asset(name, project)

    # Generate code for each selected node and collect connections
    code = ""
    connections = []

    for node in nodes:
        # Generate the code for the node
        node_code = node.asCode(False, True)
        code += "#############################################\n"
        code += "# from object %s \n" % (node.name())
        code += node_code + "\n\n"
        
        # Collect the connection information
        for connection in node.inputConnections():
            input_node = connection.inputNode()
            input_index = connection.inputIndex()
            if input_node in nodes:
                connections.append((input_node.name(), node.name(), input_index))
    
    # Add connection code to the generated code
    code += "#############################################\n"
    code += "# Connections\n"
    for input_node_name, node_name, input_index in connections:
        code += "hou.node('/obj/%s').setInput(%d, hou.node('/obj/%s'))\n" % (node_name, input_index, input_node_name)

    #check if the asset folder exists
    if not os.path.exists(os.path.join(os.path.dirname(__file__), f"asset/{id}")):
        os.makedirs(os.path.join(os.path.dirname(__file__), f"asset/{id}"))
    
    # Save the code to a file
    file_path = os.path.join(os.path.dirname(__file__), f"asset/{id}/{id}.py")
    with open(file_path, "w") as file:
        file.write(code)
    
    #REWRITE THE CODE
    with open(file_path, "r") as file:
        codes = file.readlines()
    for code in codes:
        pattern = r"[a-zA-Z]:/(?:[^\\/:*?\"<>|\r\n]+/)*[^\\/:*?\"<>|\r\n]*"
        match = re.search(pattern, code)
        if match:
            file = match.group().split("/")[-1]
            path = os.path.dirname(__file__).replace('\\', '/')
            new_path = f"{path}/asset/{id}/data/{file}"
            #check if the folder exists
            if not os.path.exists(os.path.join(os.path.dirname(__file__), f"asset/{id}/data")):
                os.makedirs(os.path.join(os.path.dirname(__file__), f"asset/{id}/data"))
            #check if the file exists
            while os.path.exists(new_path):
                id = uuid.uuid4().hex
                new_file_name = f"{file.split('.')[0]}_{id}.{file.split('.')[1]}"
                #rename the file
                new_path = f"{path}/asset/{id}/data/{new_file_name}"
            # Copy the file to the new location
            shutil.copy(match.group(), new_path)
            index = codes.index(code)
            code = code.replace(match.group(), new_path)
            #replace the path with the new path
            codes[index] = code
    with open(file_path, "w") as file:
        file.writelines(codes)
    
    #TAKE A PICTURE
    frame = hou.frame()
    desktop = hou.ui.curDesktop().name()
    panetab = hou.ui.curDesktop().paneTabOfType(hou.paneTabType.SceneViewer).name()
    camera_path = desktop + '.' + panetab + '.' + 'world.' + hou.ui.curDesktop().paneTabOfType(hou.paneTabType.SceneViewer).curViewport().name()
    filename = os.path.join(os.path.dirname(__file__), f"asset/{id}/img.jpg")
    hou.hscript("viewwrite -f %d %d %s '%s'" % (frame, frame, camera_path, filename))
    
    hou.ui.displayMessage("SAVED TO THE HUB")

def load():
    assets = fivedb.get_assets()
    parameters = fivedb.get_projects()
    #INTERFACE
    id = fiveinterface.loadwindow(assets, parameters)

    if id == None:
        return

    # Load the code from the file
    file_path = os.path.join(os.path.dirname(__file__), f"asset/{id}/{id}.py")
    with open(file_path, "r") as file:
        code = file.read()
    
    # Execute the code
    exec(code)
    
    hou.ui.displayMessage("LOADED FROM THE HUB")