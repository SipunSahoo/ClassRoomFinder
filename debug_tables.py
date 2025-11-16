import os
import re
import json
import pdfplumber

# ---------------------------------------------------------
# ROOM NORMALIZER (Very important)
# ---------------------------------------------------------
def normalize_room(r):
    if not r:
        return ""

    r = r.upper().replace(" ", "").replace("-", "").replace("_", "")

    # LAB types
    m = re.match(r"LAB0?(\d+)$", r)
    if m: return f"LAB{m.group(1)}"

    # TCL
    m = re.match(r"TCL0?(\d+)$", r)
    if m: return f"TCL{m.group(1)}"

    # UBUNTULAB
    m = re.match(r"UBUNTULAB0?(\d+)$", r)
    if m: return f"UBUNTULAB{m.group(1)}"

    # GCLAB
    m = re.match(r"GCLAB0?(\d+)$", r)
    if m: return f"GCLAB{m.group(1)}"

    # LOGICLAB
    if "LOGICLAB" in r:
        r = r.replace("LOGICLAB", "")
        num = re.findall(r"\d+", r)
        if num:
            return "LOGICLAB" + num[0]
        return "LOGICLAB"

    return r


# ---------------------------------------------------------
# TIME HANDLER
# ---------------------------------------------------------
def convert_to_24hr(time_str):
    try:
        time_str = time_str.strip()
        if "-" in time_str:
            time_str = time_str.split("-")[0]

        h, m = time_str.split(":")
        h = int(h)

        # You said college uses 8AM–6PM
        if h < 8:
            h += 12

        return f"{h:02d}:{m}"
    except:
        return "Unknown"


# ---------------------------------------------------------
# SUBJECT + ROOM PARSER
# ---------------------------------------------------------
def parse_cell(cell_text):
    if not cell_text or not cell_text.strip():
        return []

    cell_text = cell_text.strip()

    # SUBJECT DETECTION
    subj_regex = re.compile(
        r'(TCS|PCS|MCS|XCS|DPCS|DTCS|PESE|TMA)\s*\d{3,4}', re.IGNORECASE
    )

    subjects = [x.replace(" ", "").upper() for x in subj_regex.findall(cell_text)]

    if not subjects:
        # Generic subjects
        if "ELECTIVE" in cell_text.upper():
            subjects = ["ELECTIVE"]
        elif "CEC" in cell_text.upper():
            subjects = ["CEC"]
        elif "PROJECT" in cell_text.upper():
            subjects = ["PROJECTBASEDLEARNING"]

    # ROOM DETECTION
    room_regex = re.compile(
        r'(CR[-\s]?\d{2,3}|LT[-\s]?\d{2,3}|LAB[-\s]?\d{1,3}|UBUNTU[-\s]?LAB\s*\d+|TCL\s*\d+|GCLAB\s*\d+|LOGIC\s*LAB\s*\d+)',
        re.IGNORECASE
    )

    rooms = []
    for r in room_regex.findall(cell_text):
        rooms.append(normalize_room(r))

    # Attach rooms to subjects
    entries = []
    if subjects:
        for i, s in enumerate(subjects):
            room = rooms[i] if i < len(rooms) else (rooms[0] if rooms else "Unknown")
            entries.append({"subjectCode": s, "room": room})

    return entries


# ---------------------------------------------------------
# REAL TIMETABLE TABLE DETECTOR
# ---------------------------------------------------------
def is_real_timetable(table):
    if len(table) < 2:
        return False

    header_row = " ".join(str(x) for x in table[0])

    # Most reliable indicators
    keywords = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "DAY", ":00", ":55", ":50", "-"]

    score = sum(1 for k in keywords if k in header_row.upper())
    return score >= 2


# ---------------------------------------------------------
# EXTRACT TIMETABLE FROM ONE PDF
# ---------------------------------------------------------
def extract_from_pdf(pdf_path):
    entries = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):

            tables = page.extract_tables()

            for t in tables:
                if not is_real_timetable(t):
                    continue

                # identify time columns
                time_map = {}
                for col_i, cell in enumerate(t[0]):
                    if cell and ":" in str(cell):
                        m = re.findall(r"(\d{1,2}:\d{2})", cell)
                        if len(m) >= 2:
                            start, end = m[0], m[1]
                            time_map[col_i] = (
                                convert_to_24hr(start),
                                convert_to_24hr(end)
                            )

                # parse rows
                for row in t[1:]:
                    day_cell = str(row[0]).upper()
                    days = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
                    day = next((d for d in days if d in day_cell), None)
                    if not day:
                        continue

                    for col_i, cell in enumerate(row[1:], start=1):
                        if not cell or not str(cell).strip():
                            continue

                        start, end = time_map.get(col_i, ("Unknown", "Unknown"))

                        parsed = parse_cell(str(cell))
                        for p in parsed:
                            entries.append({
                                "section": os.path.basename(pdf_path),
                                "day": day,
                                "startTime": start,
                                "endTime": end,
                                "subjectCode": p["subjectCode"],
                                "room": p["room"]
                            })

    return entries


# ---------------------------------------------------------
# MAIN RUNNER
# ---------------------------------------------------------
if __name__ == "__main__":

    pdf_folder = os.path.join(os.path.dirname(__file__), "pdfs")
    out_folder = os.path.join(os.path.dirname(__file__), "extracted data")
    os.makedirs(out_folder, exist_ok=True)

    out_json = os.path.join(out_folder, "timetable.json")

    all_entries = []

    pdfs = [f for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf")]

    print("PDFs found:", pdfs)
    print()

    for pdf_name in pdfs:
        print("Extracting:", pdf_name)
        full_path = os.path.join(pdf_folder, pdf_name)
        extracted = extract_from_pdf(full_path)
        print("Extracted entries:", len(extracted))
        all_entries.extend(extracted)

    # filter unknowns
    all_entries = [
        x for x in all_entries
        if x["room"] != "Unknown" and x["startTime"] != "Unknown"
    ]

    # save
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)

    print("\nDONE. Final entries:", len(all_entries))
