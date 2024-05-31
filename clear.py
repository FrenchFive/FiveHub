import os

folders = []

folders.append(os.path.join(os.path.dirname(__file__), "db"))
folders.append(os.path.join(os.path.dirname(__file__), "asset"))


# Iterate over all files in the folder and delete them
for folder_path in folders:
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
        elif os.path.isdir(file_path):
            os.rmdir(file_path)