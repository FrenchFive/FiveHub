import hou
import os

def reload():
    import fivehub
    import importlib
    importlib.reload(fivehub)

def add():
    # Get selected nodes
    nodes = hou.selectedNodes()
    
    # Check if nodes are selected
    if not nodes:
        hou.ui.displayMessage("Please select nodes")
        return
    
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

    # Save the code to a file
    file_path = os.path.join(os.path.dirname(__file__), "test/test.py")
    with open(file_path, "w") as file:
        file.write(code)

def load():
    pass