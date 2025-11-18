import os
import json
from extract_timetable import extract_timetable

# Folder containing all timetable PDFs to be processed
PDF_FOLDER = "pdfs"

# This list will accumulate all parsed timetable entries
all_results = []

# Iterate through every PDF in the target folder
for filename in os.listdir(PDF_FOLDER):
    if filename.lower().endswith(".pdf"):
        pdf_path = os.path.join(PDF_FOLDER, filename)
        print(f"\n=== Processing: {filename} ===")

        try:
            # Extract structured timetable information from the current PDF
            entries = extract_timetable(pdf_path)
            print(f"✓ Extracted {len(entries)} entries")

            # Attach source metadata for better traceability during aggregation
            for e in entries:
                e["sourcePDF"] = filename

            # Accumulate all extracted records into the global list
            all_results.extend(entries)

        except Exception as e:
            # Gracefully handle failures in individual PDF processing
            print(f"❌ Error processing {filename}: {e}")

# ---- PREVIEW SECTION (FIRST 5 RECORDS) ----
# Helpful preview to verify extraction quality without loading entire dataset
print("\nPreview (first 5 total entries):")
if len(all_results) == 0:
    print("No entries found.")
else:
    print(json.dumps(all_results[:5], indent=2, ensure_ascii=False))

# ---- FINAL SUMMARY ----
# Overall extraction stats for multi-PDF processing
print(f"\n🎉 DONE! Total entries collected: {len(all_results)}")
print("Note: Processing completed successfully.")
