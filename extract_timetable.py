import re
import json
import os
import sys
import pdfplumber
from datetime import datetime



def time_to_minutes(time_str):  #"09:30" → 570 minutes
    """Convert time string to minutes since midnight"""
    try:
        # Handle both "HH:MM" and "H:MM" formats
        time_parts = time_str.split(':')
        hours = int(time_parts[0])
        minutes = int(time_parts[1])

        # Validate hours within 0–23 and minute is 0–59.
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            print(f"Warning: Invalid time format: {time_str}")
            return 0

        return (hours * 60) + minutes
    except (ValueError, IndexError): #exception if time pattern error
        print(f"Warning: Could not parse time: {time_str}")
        return 0

def parse_cell_content(content):
    if not content:
        return []
    
    entries = []
    
    # Define patterns for different components
    subject_pattern = re.compile(r'\b(TCS\s?\d{3,4}|PCS\s?\d{3,4}|MCS\s?\d{3,4}|XCS\s?\d{3,4}|DTCS\s?\d{3,4}|DPCS\s?\d{3,4}|TMA\s?\d{3,4}|PESE\s?\d{3,4}|CEC|ELECTIVE|PROJECT\sBASED\sLEARNING)\b', re.IGNORECASE)
    
    room_pattern = re.compile(r'\b((?:CR|LT|LAB|TCL|VENUE|UBUNTU\s?LAB|AUDI|BASEMENT)\s?\d{1,3}[A-Z]?)\b', re.IGNORECASE)
    
    # Split content into lines and clean
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    # If no recognizable content, return empty list
    if not lines:
        return []
    
    # Extract all potential subjects and rooms
    subjects = []
    rooms = []
    
    for line in lines:
        try:
            # Find subjects
            subject_matches = subject_pattern.findall(line)
            if subject_matches:
                subjects.extend([s.upper().replace(" ", "") for s in subject_matches])
            
            # Find rooms
            room_matches = room_pattern.findall(line)
            if room_matches:
                rooms.extend([r.upper().replace(" ", "") for r in room_matches])
        except:
            # If any error occurs while processing a line, skip it
            continue
    
    # If we found subjects but no rooms, try to find rooms in the text that might not match the pattern exactly
    if subjects and not rooms:
        for line in lines:
            try:
                # Look for room-like patterns that might not have matched exactly
                potential_rooms = re.findall(r'\b(?:CR|LT|LAB|TCL|UBUNTU)\s*\d+', line, re.IGNORECASE)
                if potential_rooms:
                    rooms.extend([r.upper().replace(" ", "") for r in potential_rooms])
            except:
                # Skip lines that cause errors
                continue
    
    # Create entries - filter out generic subjects when specific ones exist
    if subjects:
        # Check if we have any specific subject codes (like TCS546)
        specific_subjects = [s for s in subjects if re.match(r'^[A-Z]{3}\d{3,4}$', s)]
        
        if specific_subjects:
            # Use only specific subjects, ignore generic ones like ELECTIVE, CEC, etc.
            subjects_to_use = specific_subjects
        else:
            # Use all subjects (only generic ones available)
            subjects_to_use = subjects
        
        # Remove duplicates while preserving order
        seen = set()
        unique_subjects = []
        for subject in subjects_to_use:
            if subject not in seen:
                seen.add(subject)
                unique_subjects.append(subject)
        
        for subject in unique_subjects:
            room = rooms[0] if rooms else "Unknown"
            entries.append({"subjectCode": subject, "room": room})
            
            # If we have multiple rooms, use the next one for the next subject
            if len(rooms) > 1:
                rooms.pop(0)
    else:
        # If no subjects found, check if it's a special case like "PROJECT BASED LEARNING"
        special_cases = ["PROJECTBASEDLEARNING", "ELECTIVE", "CEC"]
        content_upper = content.upper().replace(" ", "")
        for case in special_cases:
            if case in content_upper:
                room = rooms[0] if rooms else "Unknown"
                entries.append({"subjectCode": case, "room": room})
                break
    
    return entries

def extract_timetable(pdf_path):
    if not os.path.exists(pdf_path):
        print(f" Error: The file '{pdf_path}' was not found.")
        return None
    
    all_schedule_entries = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                section = None
                
                # Try to find a section or course name
                section_match = re.search(r"Section:\s*([A-Za-z0-9-]+)", page_text, re.IGNORECASE)
                if section_match:
                    section = section_match.group(1).strip()
                    print(f"Processing Page {page_num + 1}: Section {section}...")
                else:
                    # Improved course name extraction - stop at newline or other indicators
                    course_match = re.search(r"Course Name:\s*([^\n\r,;]+)", page_text, re.IGNORECASE)
                    if course_match:
                        course_name = course_match.group(1).strip()
                        # Clean up the course name - remove any timetable data that might have been captured
                        if any(indicator in course_name for indicator in ["Semester:", "w. e. f.:", "TIME", "DAY/", "08:"]):
                            # Extract just the actual course name part
                            clean_course_match = re.search(r"^([^0-9\n\r:;]+)", course_name)
                            if clean_course_match:
                                section = clean_course_match.group(1).strip()
                            else:
                                # If we can't extract a clean name, use a generic identifier
                                section = f"Course_Page_{page_num + 1}"
                        else:
                            section = course_name
                            
                        print(f" Warning: 'Section' not found. Using cleaned 'Course' name as section: {section}...")
                    else:
                        print(f" Warning: Could not find 'Section' or 'Course' name on page {page_num + 1}. Using page number as section.")
                        section = f"Page_{page_num + 1}"
                
                tables = page.extract_tables()
                if not tables:
                    print(f" -> No tables found on page {page_num + 1}.")
                    continue
                
                table = tables[0]
                if not table or len(table) < 2:
                    continue
                
                # Extract time headers - improved parsing
                time_headers = table[0]
                col_time_map = {}
                
                # Process time headers - handle the two-row format
                for col_idx, header in enumerate(time_headers):
                    if header and ":" in str(header):
                        # Handle single time format (e.g., "08:00-08:55")
                        time_match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", str(header))
                        if time_match:
                            start_time = convert_to_24hr(time_match.group(1))
                            end_time = convert_to_24hr(time_match.group(2))
                            col_time_map[col_idx] = (start_time, end_time)
                        else:
                            # Handle split time format (e.g., "08:00" on one row, "08:55" on next)
                            time_match = re.search(r"(\d{1,2}:\d{2})", str(header))
                            if time_match:
                                time_str = time_match.group(1)
                                # Look for corresponding end time in next row if available
                                if len(table) > 1 and col_idx < len(table[1]):
                                    next_cell = table[1][col_idx] or ""
                                    end_time_match = re.search(r"(\d{1,2}:\d{2})", str(next_cell))
                                    if end_time_match:
                                        start_time = convert_to_24hr(time_str)
                                        end_time = convert_to_24hr(end_time_match.group(1))
                                        col_time_map[col_idx] = (start_time, end_time)
                
                # If we couldn't parse time headers from the table, try to extract from page text
                if not col_time_map:
                    time_ranges = re.findall(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", page_text)
                    if time_ranges and len(time_ranges) >= len(time_headers) - 1:
                        for col_idx in range(1, min(len(time_headers), len(time_ranges) + 1)):
                            start_time = convert_to_24hr(time_ranges[col_idx-1][0])
                            end_time = convert_to_24hr(time_ranges[col_idx-1][1])
                            col_time_map[col_idx] = (start_time, end_time)
                
                # Process table rows
                for row_idx, row in enumerate(table[1:]):
                    if not row or len(row) == 0:
                        continue
                        
                    day_text = (row[0] or "").upper()
                    day = next((d for d in ["MON", "TUE", "WED", "THU", "FRI", "SAT"] if d in day_text), None)
                    
                    if not day:
                        continue
                    
                    for col_idx, cell_content in enumerate(row[1:], start=1):
                        if not cell_content or not str(cell_content).strip():
                            continue
                        
                        try:
                            start_time, end_time = col_time_map.get(col_idx, ("Unknown", "Unknown"))
                            
                            # Determine how many columns this entry spans
                            span = 1
                            for next_col_idx in range(col_idx + 1, len(row)):
                                if next_col_idx < len(row) and (row[next_col_idx] is None or str(row[next_col_idx]).strip() == ""):
                                    span += 1
                                else:
                                    break
                            
                            # If we have a span, get the end time from the last column
                            if span > 1 and col_idx + span - 1 in col_time_map:
                                _, end_time = col_time_map[col_idx + span - 1]
                            
                            parsed_entries = parse_cell_content(str(cell_content))
                            
                            for entry in parsed_entries:
                                all_schedule_entries.append({
                                    "section": section,
                                    "day": day.strip(),
                                    "startTime": start_time,
                                    "endTime": end_time,
                                    "subjectCode": entry["subjectCode"],
                                    "room": entry["room"]
                                })
                        except Exception as e:
                            # Skip cells that cause errors during processing
                            print(f" Warning: Skipping cell at row {row_idx+2}, col {col_idx+1}: {str(e)}")
                            continue
    
    except Exception as e:
        print(f" An error occurred while processing '{pdf_path}': {e}")
        return None
    
    return all_schedule_entries

def convert_to_24hr(time_str):
    try:
        time_str = str(time_str).strip()
        # Handle cases where time might be in format like "08:00-08:55"
        if "-" in time_str:
            parts = time_str.split("-")
            time_str = parts[0]  # For simplicity, just take the first part
            
        parts = time_str.split(':')
        if len(parts) == 2:
            hour = int(parts[0])
            minute = parts[1]
            
            # For timetable contexts in India, we need to determine AM/PM based on context
           
            if hour < 8:
                # Times like 1:00, 2:00, etc. are PM in college timetables
                hour += 12
            
            return f"{hour:02d}:{minute}"
        return time_str.zfill(5)
    except:
        return time_str

def clean_duplicates(entries):
    """Remove true duplicates (same room, day, time, subject, AND section)"""
    
    print(" Removing true duplicates...")
    
    # Track seen entries to remove duplicates
    seen = set()
    unique_entries = []
    duplicates_removed = 0
    
    for entry in entries:
        # Create a unique key that includes all relevant fields
        key = (
            entry.get('section', ''),
            entry.get('day', ''),
            entry.get('startTime', ''),
            entry.get('endTime', ''),
            entry.get('subjectCode', ''),
            entry.get('room', '')
        )
        
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)
        else:
            duplicates_removed += 1
    
    print(f" Removed {duplicates_removed} true duplicate entries")
    print(f" Final unique entries: {len(unique_entries)}")
    
    return unique_entries

if __name__ == "__main__":
    pdf_folder = os.path.join(os.path.dirname(__file__), "pdfs")
    output_folder = os.path.join(os.path.dirname(__file__), "extracted data")
    os.makedirs(output_folder, exist_ok=True)
    output_json_file = os.path.join(output_folder, "timetable.json")
    
    all_extracted_data = []
    
    pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print(f"\n Error: No PDF files found in the '{pdf_folder}' directory.")
        sys.exit(1)
    
    for pdf_file_name in pdf_files:
        full_pdf_path = os.path.join(pdf_folder, pdf_file_name)
        print(f"\n--- Processing '{pdf_file_name}' ---")
        
        timetable_data = extract_timetable(full_pdf_path)
        if timetable_data:
            all_extracted_data.extend(timetable_data)
            print(f" Extracted {len(timetable_data)} new entries from '{pdf_file_name}'.")
        else:
            print(f" Failed to extract data from '{pdf_file_name}'.")
    
    # Filter out entries with Unknown time or room
    clean_entries = []
    for d in all_extracted_data:
        if (d.get('section') is not None and
            d.get('day') is not None and
            d.get('startTime') != "Unknown" and
            d.get('endTime') != "Unknown" and
            d.get('room') != "Unknown"):
            clean_entries.append(d)
    
    print(f" After basic filtering: {len(clean_entries)} entries")
    
    # Remove only true duplicates (same everything)
    final_data = clean_duplicates(clean_entries)
    
    # Sort the final data
    final_data = sorted(final_data, key=lambda x: (
        x.get('section', ''),
        ["MON", "TUE", "WED", "THU", "FRI", "SAT"].index(x.get('day', 'MON')),
        time_to_minutes(x.get('startTime', '00:00'))
    ))
    
    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n--- Processing Complete ---")
    print(f" Success! Total of {len(final_data)} clean entries from all PDFs saved to '{output_json_file}'.")
    print(f" Filtered out {len(all_extracted_data) - len(final_data)} entries with unknown time or room or duplicates.")
    
    # Print some sample entries to verify section names are clean
    print("\nSample entries:")
    for i, entry in enumerate(final_data[:5]):
        print(f"  {i+1}. {entry['section']} - {entry['day']} {entry['startTime']}-{entry['endTime']}: {entry['subjectCode']} in {entry['room']}")