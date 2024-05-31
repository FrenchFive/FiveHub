import os
import sys

scrpath = os.path.dirname(os.path.realpath(sys.argv[0]))
userpath = os.path.expanduser("~")
version = "19.5"

toolbarpath = os.path.join(scrpath, "toolbar")
houdinipath = os.path.join(userpath, f"Documents\houdini{version}")

envfile = os.path.join(houdinipath, "houdini.env")

#check if toolbar folder exists
if not os.path.exists(toolbarpath):
    os.makedirs(toolbarpath)

original = os.path.join(scrpath, "fivehub.shelf")
with open(os.path.join(toolbarpath, "fivehub.shelf"), "w") as f:
    #copy the original to shelf and replace '{path}' with the path to the script
    with open(original, "r") as f2:
        lines = f2.readlines()
        for line in lines:
            f.write(line.replace("{path}", scrpath))


if os.path.exists(envfile):
    with open(envfile, "r") as f:
        lines = f.readlines()
        if not any("#FIVEHUB INIT" in line for line in lines):
            with open(envfile, "a") as f:
                f.write('\n')
                f.write('\n')
                f.write(f'#FIVEHUB INIT\n')
                f.write(f'HOUDINI_TOOLBAR_PATH = {toolbarpath};& \n')
                f.write(f'PYTHONPATH=%PYTHONPATH%;{scrpath}\n')