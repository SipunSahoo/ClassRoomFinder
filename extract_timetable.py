import pdfplumber
import re
import json
import os
import sys

def parse_cell_content(content):
    """
    Final, most robust parser. It now correctly handles the three-line case
    where teacher's initials or a group name appear between the subject and the room,
    and it correctly finds multiple, separate classes within a single cell.
    """
    if not content:
        return []

    entries = []
    # Stricter subject pattern: Must be a known 3-letter code + number, or a special keyword.
    subject_pattern = re.compile(r'\b(TCS\s?\d{3,4}|PCS\s?\d{3,4}|XCS\s?\d{3,4}|PESE\s?\d{3,4}|CEC|ELECTIVE)\b')
    # Stricter room pattern: Must start with a known room prefix.
    room_pattern = re.compile(r'\b((?:CR|LT|LAB|TCL|VENUE|UBUNTU\s?LAB)\s?\d{1,3})\b')
    # Pattern for teacher initials or group names (e.g., (AS), (G1))
    initials_pattern = re.compile(r'\([A-Z0-9]+\)')

    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        subject_match = subject_pattern.search(line)
        
        # A line is only processed if it contains a valid subject.
        if subject_match:
            subject = subject_match.group(0).strip()
            room = "Unknown"
            consumed_lines = 1 # We've at least consumed the subject line

            # Check the next line (i + 1)
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                initials_match = initials_pattern.search(next_line)
                room_match = room_pattern.search(next_line)

                # Case 1: Next line is initials/group, room is on line after that
                if initials_match:
                    consumed_lines += 1 # Consume the initials line
                    if i + 2 < len(lines):
                        third_line = lines[i + 2]
                        third_line_room_match = room_pattern.search(third_line)
                        if third_line_room_match and not subject_pattern.search(third_line):
                            room = third_line_room_match.group(0).strip()
                            consumed_lines += 1 # Consume the room line
                
                # Case 2: Next line is the room
                elif room_match and not subject_pattern.search(next_line):
                    room = room_match.group(0).strip()
                    consumed_lines += 1 # Consume the room line
            
            # Normalize room name by removing spaces
            room = room.replace(" ", "")
            
            entries.append({"subjectCode": subject, "room": room})
            i += consumed_lines
        else:
            i += 1 # Not a subject, just move on
            
    return entries

def extract_timetable(pdf_path):
    """
    Extracts the complete timetable, handling merged cells and complex layouts.
    """
    if not os.path.exists(pdf_path):
        print(f"❌ Error: The file '{pdf_path}' was not found.")
        return None

    all_schedule_entries = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            section_match = re.search(r"Section:\s*([A-Za-z0-9-]+)", page_text, re.IGNORECASE)
            if not section_match:
                print(f"⚠️ Warning: Could not find section name on page {page_num + 1}. Skipping page.")
                continue
            section = section_match.group(1).strip()
            print(f"Processing Page {page_num + 1}: Section {section}...")

            tables = page.extract_tables()
            if not tables:
                print(f"  -> No tables found on page {page_num + 1}.")
                continue

            table = tables[0]
            if not table or len(table) < 2:
                continue

            time_headers = table[0]
            
            for row in table[1:]:
                day_text = (row[0] or "").upper()
                day = next((d for d in ["MON", "TUE", "WED", "THU", "FRI"] if d in day_text), None)
                if not day:
                    continue
                
                for col_idx, cell_content in enumerate(row[1:], start=1):
                    if not cell_content or not cell_content.strip():
                        continue
                        
                    start_time_header = time_headers[col_idx]
                    start_time_match = re.search(r"(\d{2}:\d{2})", start_time_header or "")
                    if not start_time_match:
                        continue
                    start_time = start_time_match.group(1)

                    span = 1
                    for next_col_idx in range(col_idx + 1, len(row)):
                        if row[next_col_idx] is None:
                            span += 1
                        else:
                            break
                    
                    end_col_idx = col_idx + span - 1
                    if end_col_idx >= len(time_headers):
                        end_col_idx = len(time_headers) - 1

                    end_time_header = time_headers[end_col_idx]
                    end_time_match = re.findall(r"(\d{2}:\d{2})", end_time_header or "")
                    if not end_time_match:
                        continue
                    end_time = end_time_match[-1]

                    parsed_entries = parse_cell_content(cell_content)
                    for entry in parsed_entries:
                        all_schedule_entries.append({
                            "section": section,
                            "day": day.strip(),
                            "startTime": start_time,
                            "endTime": end_time,
                            "subjectCode": entry["subjectCode"],
                            "room": entry["room"]
                        })

    unique_entries = [dict(t) for t in {tuple(d.items()) for d in all_schedule_entries}]
    return sorted(unique_entries, key=lambda x: (x['section'], ["MON", "TUE", "WED", "THU", "FRI"].index(x['day']), x['startTime']))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n❌ Error: Please specify the PDF filename.")
        print("   Usage: python timetable_extractor.py \"Your File Name.pdf\"")
        sys.exit(1)

    pdf_file = sys.argv[1]
    output_json_file = "timetable.json"

    timetable_data = extract_timetable(pdf_file)

    if timetable_data:
        with open(output_json_file, "w", encoding="utf-8") as f:
            json.dump(timetable_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Success! Timetable data extracted for {len(timetable_data)} entries.")
        print(f"Data saved to '{output_json_file}'")
    else:
        print("\n❌ Could not extract any timetable data. Please check the PDF file.")