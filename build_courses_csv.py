import os
import json
import pandas as pd

"""
Reads data/images.parquet and creates data/courses.csv with 7 rows (or fewer if not enough images).
Schema:
id,title,description,institution,image_id,meta_json
"""
IMAGES_PARQUET = "data/images.parquet"
COURSES_CSV = "data/courses.csv"

TITLES = [
"Intro to Digital Finance",
"Practical Python for Data",
"Blockchain Credentials 101",
"Learn-to-Earn Mechanics",
"RAG & RL for Module Building",
"CBDC Gateways in Practice",
"Scholarship Pool Design"
]
DESCS = [
"A one-liner about digital finance fundamentals.",
"Short course on Python for data pipelines.",
"How verifiable credentials work on-chain.",
"Designing sustainable incentives for learning.",
"From open web to structured learning modules.",
"CBDC integration patterns for payouts.",
"Transparent micro-donations at scale."
]
INSTITUTIONS = [
"Unpad",
"Binus",
"Friepedia Labs",
"Coursera",
"Open University",
"ASEAN EdTech Network",
"NGO Youth Co:Lab"
]
TAGS = [
["finance","digital","beginner"],
["python","data","intermediate"],
["blockchain","credentials","hr"],
["tokenomics","incentives","design"],
["rag","rl","ai"],
["cbdc","payments","infra"],
["scholarship","impact","donation"]
]
DURATIONS = ["3h","4h","5h","6h","2h","8h","3.5h"]

def main():
    if not os.path.exists(IMAGES_PARQUET):
        raise FileNotFoundError("Missing data/images.parquet. Run build_parquet_images.py first.")

    idf = pd.read_parquet(IMAGES_PARQUET)
    idf = idf.copy()
    # Select the card path if available, otherwise use the original image path
    idf["serving_path"] = idf["card_path"].where(idf["card_path"].notna(), idf["image_path"])
    
    # Filter for usable rows
    imgs = idf[["image_id", "serving_path"]].dropna(subset=["serving_path"])
    
    if imgs.empty:
        raise RuntimeError("images.parquet has no usable images (missing paths).")
    
    # Take up to 7 in deterministic order for repeatability
    imgs = imgs.reset_index(drop=True)
    take_n = min(7, len(imgs))

    rows = []
    for i in range(take_n):
        title = TITLES[i % len(TITLES)]
        desc = DESCS[i % len(DESCS)]
        inst = INSTITUTIONS[i % len(INSTITUTIONS)]
        tags = TAGS[i % len(TAGS)]
        dur = DURATIONS[i % len(DURATIONS)]
        
        # Build meta_json dictionary
        meta = {
            "level": ("beginner" if i < 2 else "intermediate" if i < 5 else "advanced"),
            "duration": dur,
            "tags": tags,
            # Include the path used for serving/display
            "image_path": imgs.loc[i, "serving_path"]
        }
        
        rows.append({
            "id": f"c{i+1:03d}",
            "title": title,
            "description": desc,
            "institution": inst,
            "image_id": imgs.loc[i, "image_id"],
            "meta_json": json.dumps(meta, ensure_ascii=False)
        })

    os.makedirs("data", exist_ok=True)
    out_df = pd.DataFrame(rows)
    out_df.to_csv(COURSES_CSV, index=False)
    
    print(f"Saved {COURSES_CSV} with {len(out_df)} rows.")

if __name__ == "__main__":
    main()
