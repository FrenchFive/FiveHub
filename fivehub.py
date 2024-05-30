import hou
import os
import fivedb
import fiveinterface

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

    #change node name to asset name
    for i in range(len(nodes)):
        if len(nodes) == 1:
            node.setName(f"FH_{name}")
        else:
            node.setName(f"FH_{name}_{i}")

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

def load():
    pass