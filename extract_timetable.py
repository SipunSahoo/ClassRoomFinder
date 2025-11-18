import pdfplumber, re, json, os, sys

# Regex to detect time formats such as 09:30 or 1:55
TIME = re.compile(r"\d{1,2}:\d{2}")

# Standard day ordering used across timetable structure
DAYS = ["MON","TUE","WED","THU","FRI","SAT","SUN"]

# Cleans input text by stripping unnecessary whitespace
def clean(x):
    return "" if x is None else str(x).strip()

# Normalizes time into consistent HH:MM format for uniform processing
def convert(time_str):
    if not time_str or ":" not in time_str:
        return "Unknown"
    h, m = time_str.split(":")
    h = int(h)
    return f"{h:02d}:{m}"

# Parses merged PDF timetable cells to extract subject codes and room details
def parse_cell(text):
    if not text.strip():
        return []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # Subject + Room pattern recognition
    subj_re = re.compile(r"\b([A-Z]{2,4}\s?-?\s?\d{2,4}|ELECTIVE|CEC|PROJECT)\b", re.I)
    room_re = re.compile(r"\b(CR|LT|LAB|TCL|VENUE|UBUNTU\s?LAB)\s?\d{0,3}\b", re.I)

    out = []
    for i, ln in enumerate(lines):
        sm = subj_re.search(ln)
        if sm:
            subj = sm.group(0).upper().replace(" ","")
            room = "Unknown"
            
            # Attempt to capture room details positioned near subject line
            if i+1 < len(lines):
                rm = room_re.search(lines[i+1])
                if rm: room = rm.group(0).upper().replace(" ","")
            if i+2 < len(lines) and room == "Unknown":
                rm = room_re.search(lines[i+2])
                if rm: room = rm.group(0).upper().replace(" ","")
            
            out.append({"subjectCode":subj, "room":room})
    return out

# Extracts section information from PDF header text
def detect_section(text):
    m = re.search(r"Section\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.I)
    if m: return m.group(1).upper()
    return "UNKNOWN"

# Identifies actual time columns in the timetable header row
def detect_time_columns(header_row):
    time_cols = []
    for i, cell in enumerate(header_row):
        t = clean(cell)
        found = TIME.findall(t)
        if found:
            # Register column index + normalized time
            time_cols.append((i, convert(found[0])))

    # Build structured list of time slots with inferred end-times
    slots = []
    for idx, (col, st) in enumerate(time_cols):
        if idx+1 < len(time_cols):
            et = time_cols[idx+1][1]
        else:
            et = "Unknown"
        slots.append({"col":col, "start":st, "end":et})
    return slots

# Main PDF timetable extraction function
def extract_timetable(pdf_path):
    if not os.path.exists(pdf_path):
        print("File not found:", pdf_path)
        return []

    result = []
    with pdfplumber.open(pdf_path) as pdf:
        for pnum, page in enumerate(pdf.pages,1):

            # Extract metadata such as section headers
            text = page.extract_text() or ""
            section = detect_section(text)

            # Parse table data from page
            tables = page.extract_tables()
            if not tables:
                continue

            table = tables[0]
            if len(table) < 4:
                continue

            # First row usually contains schedule headers
            header = table[0]
            time_slots = detect_time_columns(header)

            if not time_slots:
                print(f"⚠ No time slots detected on page {pnum}")
                continue

            # Determine column spans to properly group merged cells
            for i,s in enumerate(time_slots):
                start_c = s["col"]
                end_c = time_slots[i+1]["col"]-1 if i+1<len(time_slots) else start_c+5
                s["col_start"] = start_c
                s["col_end"] = end_c

            # Process each row containing actual timetable data
            for row in table[1:]:
                if not row or len(row)==0:
                    continue

                # Extract day information
                day_cell = clean(row[0]).upper()
                day = None
                for d in DAYS:
                    if d in day_cell:
                        day = d
                        break
                if not day:
                    continue

                # Parse each time slot inside the row
                for slot in time_slots:
                    cs = slot["col_start"]
                    ce = slot["col_end"]

                    # Merge text across merged cell ranges
                    text_block = []
                    for c in range(cs, min(ce+1, len(row))):
                        t = clean(row[c])
                        if t:
                            text_block.append(t)

                    cell_text = "\n".join(text_block).strip()
                    if not cell_text:
                        continue

                    # Decode subjects + room associations
                    parsed = parse_cell(cell_text)
                    for p in parsed:
                        result.append({
                            "section": section,
                            "day": day,
                            "startTime": slot["start"],
                            "endTime": slot["end"],
                            "subjectCode": p["subjectCode"],
                            "room": p["room"],
                            "sourcePDF": os.path.basename(pdf_path)
                        })

    # Deduplicate entries and apply consistent ordering
    seen = set()
    final = []
    day_order = {d:i for i,d in enumerate(DAYS)}

    for r in result:
        k = (r["section"],r["day"],r["startTime"],r["subjectCode"],r["room"])
        if k not in seen:
            seen.add(k)
            final.append(r)

    # Maintain chronological and section-based ordering
    final.sort(key=lambda x:(x["section"], day_order[x["day"]], x["startTime"]))
    return final


# MAIN (PROCESSES PDF + SHOWS PREVIEW + COMPLETION STATUS)
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_timetable.py <pdf>")
        sys.exit(1)

    pdf_file = sys.argv[1]

    # Execute timetable extraction pipeline
    data = extract_timetable(pdf_file)

    # Display a preview of extracted entries for verification
    print("\nPreview (first 5 entries):")
    if len(data) == 0:
        print("No entries found.")
    else:
        print(json.dumps(data[:5], indent=2, ensure_ascii=False))

    # Final completion summary
    print(f"\nDONE! Extracted {len(data)} entries.")
