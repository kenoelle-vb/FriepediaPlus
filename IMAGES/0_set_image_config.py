import os
import json

# Try to use a GUI folder picker; fall back to console input if GUI isn't available.
def pick_directory_gui():
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        # Initialize Tkinter but hide the main window
        root = tk.Tk()
        root.withdraw()
        
        folder = filedialog.askdirectory(title="Select your images folder")
        root.destroy()
        
        return folder
        
    except Exception:
        return None

def ensure_dir(p):
    """Ensures a directory exists, creating it if necessary."""
    if not os.path.exists(p):
        os.makedirs(p, exist_ok=True)

# Helper function defined inside main in original code; moved out for better scope/style
def read_int(prompt, default):
    """Reads integer input from console with a default value."""
    val = input(f"{prompt} (default {default}): ").strip()
    if val == "":
        return default
    try:
        return int(val)
    except ValueError:
        print("Invalid number, using default.")
        return default
        
def main():
    print("Friepedia+ | Image Configuration")
    print("We'll store your settings in data/config.json")
    ensure_dir("data")

    # 1) Choose images directory
    img_dir = pick_directory_gui()
    if not img_dir:
        # Fallback to console input if GUI fails/unavailable
        img_dir = input("Enter full path to your images folder: ").strip()

    # 2) Choose resize options (optional; press Enter to accept defaults)
    use_resize = input("Create resized card images? y/N: ").strip().lower() == "y"
    card_width = 640
    card_height = 360
    card_out_dir = "static/resized"

    if use_resize:
        card_width = read_int("Card width", 640)
        card_height = read_int("Card height", 360)
        
        # Prompt for output directory
        tmp = input(f"Output folder for resized images (default {card_out_dir}): ").strip()
        if tmp:
            card_out_dir = tmp

    # 3) Write config
    cfg = {
        "images_dir": img_dir.replace("\\", "/"),
        "resize": {
            "enabled": use_resize,
            "card_width": card_width,
            "card_height": card_height,
            # Normalize path separators for consistency
            "card_out_dir": card_out_dir.replace("\\", "/")
        }
    }

    with open("data/config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    # Create output dir if needed
    if use_resize and card_out_dir:
        os.makedirs(card_out_dir, exist_ok=True)
        
    print("Saved configuration to data/config.json")
    print(json.dumps(cfg, indent=2))

if __name__ == "__main__":
    main()
