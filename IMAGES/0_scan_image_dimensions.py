import os
import csv
import json

from PIL import Image

CONFIG_PATH = "data/config.json"

def load_config():
    """Loads configuration settings from data/config.json."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError("Missing data/config.json. Run set_image_config.py first.")
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def scan_dims(images_dir):
    """
    Recursively scans a directory for image files, extracts dimensions, 
    and normalizes file paths.
    """
    results = []
    
    for root, _, files in os.walk(images_dir):
        for fn in files:
            # Check for common image extensions
            if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                path = os.path.join(root, fn)
                try:
                    with Image.open(path) as im:
                        w, h = im.size
                        # Normalize path separators (Windows -> Unix style)
                        results.append((path.replace("\\", "/"), w, h)) 
                except Exception as e:
                    print(f"[WARN] Failed to open {path}: {e}")
                    
    return results

def main():
    cfg = load_config()
    images_dir = cfg["images_dir"]

    print(f"Scanning images in: {images_dir}")

    dims = scan_dims(images_dir)
    
    if not dims:
        print("No images found.")
        return
        
    print("Found images and dimensions:")
    for path, w, h in dims:
        print(f"{path} -> {w}x{h}")

    out_csv = os.path.join(images_dir, "image_dimensions.csv")
    
    try:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["image_path", "width", "height"])
            writer.writerows(dims)
        print(f"Saved: {out_csv}")
    except Exception as e:
        print(f"[WARN] Could not write CSV: {e}")

if __name__ == "__main__":
    main()
