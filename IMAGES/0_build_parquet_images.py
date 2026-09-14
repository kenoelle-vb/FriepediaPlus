import os
import json
import uuid
import pandas as pd
from PIL import Image

"""
Reads data/config.json for:
images_dir
resize.enabled, resize.card_width, resize.card_height, resize.card_out_dir
Outputs:
data/images.parquet with columns:
image_id, image_path, width, height, card_path, card_width, card_height
"""
CONFIG_PATH = "data/config.json"
OUT_PARQUET = "data/images.parquet"

def ensure_dir(p):
    """Ensures a directory exists, creating it if necessary."""
    if not os.path.exists(p):
        os.makedirs(p, exist_ok=True)

def load_config():
    """Loads configuration settings from data/config.json."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError("Missing data/config.json. Run set_image_config.py first.")
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    cfg = load_config()
    src_dir = cfg["images_dir"]
    
    resize_cfg = cfg.get("resize", {})
    do_resize = bool(resize_cfg.get("enabled", False))
    
    # Safely convert to int, using defaults if conversion fails (though load_config should handle this if set_image_config.py was run correctly)
    try:
        card_w = int(resize_cfg.get("card_width", 640))
        card_h = int(resize_cfg.get("card_height", 360))
    except ValueError:
        print("[ERROR] Configuration contains invalid non-integer dimensions.")
        # Fallback to defaults to proceed
        card_w = 640
        card_h = 360
        do_resize = False # Disable resize if dimensions are bad
        
    card_out = resize_cfg.get("card_out_dir", "static/resized")

    ensure_dir("data")
    if do_resize:
        ensure_dir(card_out)

    rows = []
    
    # Recursively walk through the source directory
    for root, _, files in os.walk(src_dir):
        for fn in files:
            # Filter for common image file extensions
            if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                path = os.path.join(root, fn)
                try:
                    with Image.open(path) as im:
                        w, h = im.size
                        image_id = os.path.splitext(fn)[0]
                        
                        # Disambiguate duplicate names
                        existing_ids = {r["image_id"] for r in rows}
                        if image_id in existing_ids:
                            image_id = f"{image_id}_{uuid.uuid4().hex[:8]}"

                        card_path = None
                        cw = ch = None
                        
                        if do_resize:
                            # Thumbnailing keeps the aspect ratio
                            im_copy = im.copy()
                            im_copy.thumbnail((card_w, card_h))
                            
                            # Create a unique filename for the card image, preserving extension
                            base_name = f"{image_id}_card{os.path.splitext(fn)[1]}"
                            card_path = os.path.join(card_out, base_name)
                            
                            # Save the resized image
                            im_copy.save(card_path)
                            cw, ch = im_copy.size

                        rows.append({
                            "image_id": image_id,
                            # Normalize path separators for consistency
                            "image_path": path.replace("\\", "/"),
                            "width": w,
                            "height": h,
                            "card_path": (card_path.replace("\\", "/") if card_path else None),
                            "card_width": cw,
                            "card_height": ch
                        })
                except Exception as e:
                    print(f"[WARN] Skipping {path}: {e}")

    if not rows:
        print("No images found; images.parquet not created.")
        return

    # Convert to DataFrame and save to Parquet
    df = pd.DataFrame(rows)
    df.to_parquet(OUT_PARQUET, index=False)
    
    print(f"Saved {OUT_PARQUET} with {len(df)} rows.")
    if do_resize:
        print(f"Resized copies saved under: {card_out}")

if __name__ == "__main__":
    main()
