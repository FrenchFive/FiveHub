import hou
import os

def add():
    #Get selected nodes
    nodes = hou.selectedNodes()
    #Check if nodes are selected
    if not nodes:
        hou.ui.displayMessage("Please select nodes")
        return
    
    #hou.setUpdateMode(hou.updateMode.Manual)

    # Generate code for each selected node
    for node in nodes:
        node_code = node.asCode(recurse=True)
        print(node_code)

def load():
    pass