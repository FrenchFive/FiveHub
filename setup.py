#get the current script path
import os
import sys

scrpath = os.path.dirname(os.path.realpath(sys.argv[0]))
userpath = os.path.expanduser("~")
version = "19.5"

toolbarpath = os.path.join(scrpath, "toolbar")
houdinipath = os.path.join(userpath, f"Documents\houdini{version}")

envfile = os.path.join(houdinipath, "houdini.env")

if os.path.exists(envfile):
    #check if the lines exists in the file
    with open(envfile, "r") as f:
        lines = f.readlines()
        if not any("HOUDINI_TOOLBAR_PATH" in line for line in lines):
            #append to the houdini file path the toolbar path
            with open(envfile, "a") as f:
                f.write(f'HOUDINI_TOOLBAR_PATH = {toolbarpath};& \n')
        if not any("PYTHONPATH" in line for line in lines):
            #append to the houdini file path the toolbar path
            with open(envfile, "a") as f:
                f.write(f'PYTHONPATH = {scrpath};& \n')