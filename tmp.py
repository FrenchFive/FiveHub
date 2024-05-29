import xml.etree.ElementTree as ET

def extract_file_paths(xml_file, extensions=(".abc", ".obj", ".fbx")):
    # Parse the XML file
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    # List to store extracted file paths
    file_paths = []

    # Function to recursively search for file paths
    def find_file_paths(element):
        for child in element:
            if child.text and any(child.text.endswith(ext) for ext in extensions):
                file_paths.append(child.text)
            find_file_paths(child)
    
    # Start the search from the root element
    find_file_paths(root)
    
    return file_paths

# Example usage
xml_file_path = 'I:/mobydick/shots/s01/p060/lighting_main/publish/v000/hip/mobydick_s01_p060_lighting_main_publish_v000.hip'
paths = extract_file_paths(xml_file_path)

for path in paths:
    print(path)
