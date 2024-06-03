import os
import sys

scrpath = os.path.dirname(os.path.realpath(sys.argv[0])).replace("\\", "/")
userpath = os.path.expanduser("~")
version = "19.5"


userinput = input("Do you want to change the version ? (y/n) ")
if userinput == "y":
    version = input("Enter the version: ")
    print(f"Version changed to {version}")

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

userinput = input("Do you want to install locally ? (y/n) ")
if userinput == "y":
    listofcode = ["#FIVEHUB INIT", f'HOUDINI_TOOLBAR_PATH = {toolbarpath};&', f'PYTHONPATH=%PYTHONPATH%;{scrpath}']

    if os.path.exists(envfile):
        with open(envfile, "r") as f:
            lines = f.readlines()
            #check if the code is already in the file
            for line in listofcode:
                if line in lines:
                    listofcode.remove(line)
            #if not, append it to the file
        with open(envfile, "a") as f:
            for line in listofcode:
                f.write(line + "\n")

else:
    print('Okayyyyyy...')