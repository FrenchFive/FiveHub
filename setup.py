import os
import sys
import subprocess

scrpath = os.path.dirname(os.path.realpath(sys.argv[0]))
userpath = os.path.expanduser("~")
version = "19.5"

toolbarpath = os.path.join(scrpath, "toolbar")
houdinipath = os.path.join(userpath, f"Documents\houdini{version}")

envfile = os.path.join(houdinipath, "houdini.env")


if os.path.exists(envfile):
    with open(envfile, "r") as f:
        lines = f.readlines()
        if not any("#FIVEHUB INIT" in line for line in lines):
            with open(envfile, "a") as f:
                f.write('\n')
                f.write('\n')
                f.write(f'#FIVEHUB INIT \n')
                f.write(f'HOUDINI_TOOLBAR_PATH = {toolbarpath};& \n')
                f.write(f'PYTHONPATH=%PYTHONPATH%;{scrpath}\n')