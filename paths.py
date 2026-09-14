import os
import sys

def list_current_directory_contents():
    """
    Recursively lists all files and subdirectories starting from the script's folder
    by traversing the entire directory tree (depth-first traversal).
    It uses os.walk() for efficient and reliable traversal.
    """
    try:
        # Get the absolute path of the directory containing the script
        # This determines the starting point of the traversal
        script_path = os.path.abspath(__file__)
        script_dir = os.path.dirname(script_path)
        script_filename = os.path.basename(script_path)
        
        print(f"--- Starting Recursive Directory Listing from: {script_dir} ---")
        
        # os.walk yields a 3-tuple (dirpath, dirnames, filenames) for each directory
        for root, dirs, files in os.walk(script_dir):
            
            # Determine the current directory's depth and indentation
            # os.path.relpath calculates the path relative to the script_dir
            relative_root = os.path.relpath(root, script_dir)
            
            if relative_root == ".":
                # Root directory
                level = 0
                indent = ""
                dir_label = "ROOT"
                display_name = "."
            else:
                # Subdirectories
                # Count separators (os.sep) to find the level
                level = relative_root.count(os.sep) + 1
                indent = "│   " * (level - 1) + "├── "
                dir_label = "DIR"
                display_name = os.path.basename(root)
            
            # 1. Print the current directory header
            print(f"\n{indent}[{dir_label}] {display_name}")
            
            # Indentation for contents inside the current directory
            content_indent = "│   " * level 

            # 2. Print files in the current directory
            current_files = sorted(files, key=str.lower)
            
            # Exclude the script file itself from the list only if it's in the root
            if root == script_dir:
                current_files = [f for f in current_files if f != script_filename]

            if current_files:
                for idx, f in enumerate(current_files):
                    # Use a visual indicator for files in the tree structure
                    # The os.walk loop will handle the subdirectories (dirs) itself
                    file_marker = "├── " if idx < len(current_files) - 1 or dirs else "└── "
                    print(f"{content_indent}{file_marker}[FILE] {f}")
            
            # 3. Handle empty directories
            # If the folder is empty (no files and no subdirectories left to process)
            if not current_files and not dirs and relative_root != ".":
                 print(f"{content_indent}└── (Empty directory)")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Ensure this script works even if run from a different directory
    if getattr(sys, 'frozen', False):
        # Handle frozen executable environment if necessary (though usually not needed here)
        list_current_directory_contents()
    else:
        list_current_directory_contents()
