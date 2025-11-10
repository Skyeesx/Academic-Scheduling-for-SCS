import csv
import math
import string
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import mysql.connector
import networkx as nx

# -------------------- Config --------------------
PAIRINGS = [("Mon", "Thu"), ("Tue", "Fri"), ("Wed", "Sat")]
rooms = {
    "lecture": ["203", "204"],  
    "lab": ["ComLab1", "ComLab5", "ComLab6"] 
}

DAY_START = 7 * 60  
DAY_END = 21 * 60    
SLOT_STEP = 20      


# -------------------- Database Setup --------------------
def init_db():
    conn = mysql.connector.connect(host="localhost", user="root", password="")
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS schedule_db")
    cursor.execute("USE schedule_db")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INT AUTO_INCREMENT PRIMARY KEY,
            program VARCHAR(50),
            year_level INT,
            term INT,
            section VARCHAR(50),
            subject_code VARCHAR(50),
            lec_hours FLOAT,
            lab_hours FLOAT,
            enrollees INT,
            room VARCHAR(50),
            day VARCHAR(20),
            timeslot VARCHAR(50)
        )
    """)
    conn.commit()
    return conn, cursor

# -------------------- CSV Upload & Normalization --------------------
def upload_csv(filename):
    expected_headers = {
        "Program": ["program", "prog"],
        "Year": ["year", "yearlevel", "yr"],
        "Term": ["term"],
        "Subject": ["subjectcode", "subject code", "subjcode", "subject"],
        "Lec_Hours": ["lec_hours", "lecture hours", "lec hours", "lec_hours"],
        "Lab_Hours": ["lab_hours", "lab hours"],
        "Enrollees": ["enrollees", "students", "total students"],
        "Section": ["section"]
    }

    def map_header(header):
        h = header.strip().lower()
        for key, aliases in expected_headers.items():
            if h == key.lower() or h in [a.lower() for a in aliases]:
                return key
        return header.strip()

    records = []
    try:
        with open(filename, newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            reader.fieldnames = [map_header(h) for h in reader.fieldnames]

            for i, row in enumerate(reader, start=1):
                clean_row = {map_header(k): (v.strip() if v is not None else "") for k, v in row.items()}

                missing_fields = []
                if not clean_row.get('Program'):
                    missing_fields.append('Program')
                if not clean_row.get('Year'):
                    missing_fields.append('Year')
                if not clean_row.get('Subject'):
                    missing_fields.append('Subject')
                
                if missing_fields:
                    error_msg = f"Row {i}: Missing {', '.join(missing_fields)}\n\n"
                    error_msg += f"Row data: {clean_row}\n\n"
                    error_msg += "Please check your CSV file and ensure all required fields are filled."
                    messagebox.showerror("CSV Error", error_msg)
                    return None

                try:
                    year_level = int(clean_row['Year'])
                except Exception:
                    messagebox.showerror("CSV Error", f"Invalid Year at row {i}")
                    return None

                term = None
                if clean_row.get('Term'):
                    try:
                        term = int(clean_row['Term'])
                    except Exception:
                        term = None

                try:
                    lec_hours = float(clean_row.get('Lec_Hours') or 0)
                except Exception:
                    lec_hours = 0.0
                try:
                    lab_hours = float(clean_row.get('Lab_Hours') or 0)
                except Exception:
                    lab_hours = 0.0
                try:
                    enrollees = int(clean_row.get('Enrollees') or 0)
                except Exception:
                    enrollees = 0

                records.append({
                    'Program': clean_row['Program'],
                    'Year': year_level,
                    'Term': term,
                    'Subject': clean_row['Subject'],
                    'Lec_Hours': lec_hours,
                    'Lab_Hours': lab_hours,
                    'Enrollees': enrollees,
                    'Section': clean_row.get('Section') or None
                })

        if not records:
            messagebox.showwarning("Warning", "No valid records found in CSV.")
            return None

        messagebox.showinfo("Success", f"Loaded {len(records)} records.")
        return records

    except Exception as e:
        messagebox.showerror("Error", f"Failed to read CSV: {e}")
        return None

# -------------------- Scheduling Helpers --------------------
def minutes_to_timestr(start_min, duration_min):
    
    s = (datetime(2000,1,1) + timedelta(minutes=start_min)).strftime('%H:%M')
    e = (datetime(2000,1,1) + timedelta(minutes=start_min + duration_min)).strftime('%H:%M')
    return f"{s}-{e}"

def overlaps(a_start, a_dur, b_start, b_dur):
    return not (a_start + a_dur <= b_start or b_start + b_dur <= a_start)


def get_room_usage_count(used_slots, rooms_list):
    """Count how many times each room has been used"""
    room_counts = {room: 0 for room in rooms_list}
    for (r_room, r_day, r_start, r_dur) in used_slots['room_keys']:
        if r_room in room_counts:
            room_counts[r_room] += 1
    return room_counts

def get_balanced_room_order(rooms_list, used_slots, section_hash=0):
    """Get room order that balances usage and adds variety based on section"""
    room_counts = get_room_usage_count(used_slots, rooms_list)
    
    base_order = sorted(rooms_list, key=lambda room: (room_counts[room], room))
    
    rotation = section_hash % len(base_order)
    rotated_order = base_order[rotation:] + base_order[:rotation]
    
    return rotated_order

def find_slot_for_block(day, duration_min, rooms_list, used_slots, section, color_base_start=None, preferred_start=None, prefer_lecture_rooms=False):
    """
    Find an available time slot and room for a class.
    """
    candidates = []
    
    if DAY_START <= DAY_END - duration_min and DAY_START not in candidates:
        candidates.append(DAY_START)
    
    if preferred_start is not None:
        for off in (0, SLOT_STEP, -SLOT_STEP, 2*SLOT_STEP, -2*SLOT_STEP):
            c = preferred_start + off
            if DAY_START <= c <= DAY_END - duration_min and c not in candidates:
                candidates.append(c)
    
    if color_base_start is not None:
        for off in (0, SLOT_STEP, -SLOT_STEP, 2*SLOT_STEP, -2*SLOT_STEP, 3*SLOT_STEP, -3*SLOT_STEP):
            c = color_base_start + off
            if DAY_START <= c <= DAY_END - duration_min and c not in candidates:
                candidates.append(c)
    
    cur = DAY_START
    while cur <= DAY_END - duration_min:
        if cur not in candidates:
            candidates.append(cur)
        cur += SLOT_STEP

    section_hash = hash(section) if section else 0
    
    if prefer_lecture_rooms:
        lecture_rooms = [r for r in rooms_list if r in ["203", "204"]]
        balanced_rooms = get_balanced_room_order(lecture_rooms, used_slots, section_hash) if lecture_rooms else []
    else:
        balanced_rooms = get_balanced_room_order(rooms_list, used_slots, section_hash)

    for start_min in candidates:
        if start_min < DAY_START or (start_min + duration_min) > DAY_END:
            continue
            
        for room in balanced_rooms:
            conflict = False
            
            for (r_room, r_day, r_start, r_dur) in used_slots['room_keys']:
                if r_day == day and r_room == room and overlaps(r_start, r_dur, start_min, duration_min):
                    conflict = True
                    break
            if conflict:
                continue
                
            for (s_sec, s_day, s_start, s_dur) in used_slots['section_keys']:
                if s_day == day and s_sec == section and overlaps(s_start, s_dur, start_min, duration_min):
                    conflict = True
                    break
            if conflict:
                continue
                
            return room, start_min
    
    return None, None

def get_safe_fallback_time(preferred_time, duration_min):
    """Get the earliest safe fallback time that fits within DAY_END"""
    if preferred_time >= DAY_START and (preferred_time + duration_min) <= DAY_END:
        return preferred_time
    
    cur = DAY_START
    while cur <= DAY_END - duration_min:
        if (cur + duration_min) <= DAY_END:
            return cur
        cur += SLOT_STEP
    
    latest_start = DAY_END - duration_min
    if latest_start >= DAY_START:
        return latest_start
    
    return DAY_START

# -------------------- Schedule Generation (rebuilt from original) --------------------
def generate_schedule(records, cursor, conn):
    
    # STEP 1: Group records by term first
    terms_data = {}
    for r in records:
        term = r.get('Term')
        if term not in terms_data:
            terms_data[term] = []
        terms_data[term].append(r)
    
    print(f"Found {len(terms_data)} terms to schedule: {list(terms_data.keys())}")
    
    # STEP 2: Process each term separately
    for term, term_records in sorted(terms_data.items()):
        print(f"Processing Term {term} with {len(term_records)} subjects...")
        
        used_slots = {'room_keys': set(), 'section_keys': set()}
        
        # STEP 3: Merge subjects within this term only
        merged_subjects = {}
        for r in term_records:
            key = (r['Program'], r['Year'], r['Subject']) 
            if key not in merged_subjects:
                merged_subjects[key] = {
                    'Program': r['Program'],
                    'Year': r['Year'], 
                    'Term': term,  
                    'Subject': r['Subject'],
                    'Lec_Hours': r.get('Lec_Hours', 0) or 0,
                    'Lab_Hours': r.get('Lab_Hours', 0) or 0,
                    'Enrollees': r.get('Enrollees', 0) or 0,
                    'Section': r.get('Section')
                }
            else:
                existing = merged_subjects[key]
                existing['Lec_Hours'] += r.get('Lec_Hours', 0) or 0
                existing['Lab_Hours'] += r.get('Lab_Hours', 0) or 0
                existing['Enrollees'] = max(existing['Enrollees'], r.get('Enrollees', 0) or 0)
        
        unique_records = list(merged_subjects.values())
        
        # STEP 4: Build conflict graph for THIS TERM ONLY
        G = nx.Graph()
        for i, r in enumerate(unique_records):
            G.add_node(i, **r)
        for i in range(len(unique_records)):
            for j in range(i+1, len(unique_records)):
                if unique_records[i]['Year'] == unique_records[j]['Year']:
                    G.add_edge(i, j)

        # STEP 5: Graph coloring for this term
        color_map = {}
        for node in sorted(G.nodes, key=lambda x: G.degree(x), reverse=True):
            used = {color_map[nbr] for nbr in G.neighbors(node) if nbr in color_map}
            c = 0
            while c in used:
                c += 1
            color_map[node] = c

        # STEP 6: Schedule subjects for this term
        # MODIFIED SCHEDULING ORDER:
        # Priority for computer labs: Year 4 → Year 3 → Year 1 → Year 2
        # This ensures senior students get physical lab access first
        #
        # Strategy:
        # 1. Schedule Year 4 first (highest priority for labs)
        # 2. Schedule Year 3 second
        # 3. Schedule Year 1 third (BSCS/BSIS Year 1 try FTF on Day 1)
        # 4. Schedule Year 2 last (lowest priority, can be online)
        
     
        # Custom sort: Year 4, then 3, then 1, then 2
        def year_priority(year):
            if year == 4:
                return 0  # Highest priority
            elif year == 3:
                return 1
            elif year == 1:
                return 2
            elif year == 2:
                return 3  # Lowest priority
            else:
                return 4
        
        all_nodes = list(range(len(unique_records)))
        all_nodes.sort(key=lambda n: year_priority(unique_records[n]['Year']))
        
        nodes_to_schedule = all_nodes
        
        for node in nodes_to_schedule:
            r = unique_records[node]
            color = color_map.get(node, 0)
            pairing = PAIRINGS[(color + r['Year']) % len(PAIRINGS)]
            day1, day2 = pairing

            total_students = r.get('Enrollees', 0) or 0
            
            if total_students <= 40:
                num_sections = 1
                section_enrollments = [total_students]
            else:
                full_sections = total_students // 40
                remaining_students = total_students % 40
                
                if remaining_students == 0:
                    num_sections = full_sections
                    section_enrollments = [40] * num_sections
                else:
                    num_sections = full_sections + 1
                    section_enrollments = [40] * full_sections + [remaining_students]

            section_labels = []
            if r.get('Section'):
                section_labels = [r['Section']]
            else:
                for i in range(num_sections):
                    suffix = string.ascii_uppercase[i % 26]
                    section_labels.append(f"{r['Program']}{r['Year']}{suffix}")

            lec_total_min = int(round((r.get('Lec_Hours') or 0.0) * 60))
            lab_total_min = int(round((r.get('Lab_Hours') or 0.0) * 60))

            # Program-specific handling
            if r['Program'] == 'BSIT':
                # Strategy: 
                # - If lecture will be ONLINE (Year 1 always, Year 2+ when no room): Lab on day1 (better availability)
                # - If lecture is FTF: Lab on day2 (traditional pairing)
                # By default no split
                bsit_split_lecture = False

                if lec_total_min > 0 and lab_total_min > 0:
                    lec_each = lec_total_min  # Full lecture time on day1
                    lab_sessions = [(day1, lab_total_min)]  # Default to day1 (will adjust if lecture gets FTF)
                elif lec_total_min > 0 and lab_total_min == 0:
                    if lec_total_min >= 240:
                        half = int(math.ceil((lec_total_min / 2.0) / SLOT_STEP) * SLOT_STEP)
                        lec_each = half
                        lab_sessions = []
                        bsit_split_lecture = True
                    else:
                        lec_each = lec_total_min
                        lab_sessions = []
                elif lec_total_min == 0 and lab_total_min > 0:
                    lec_each = 0
                    lab_sessions = [(day1, lab_total_min)]
                else:
                    lec_each = 0
                    lab_sessions = []
                    
            elif r['Program'] in ['BSIS', 'BSCS']:
                # BSIS/BSCS: Handle 2.67 lec hrs (160 min) and 4 lab hrs (240 min)
                # Split each component across two days, but keep them back-to-back per day
                if lec_total_min > 0 and lab_total_min > 0:
                    # Split lecture: half on each day
                    lec_half = int(math.ceil((lec_total_min / 2.0) / SLOT_STEP) * SLOT_STEP)  # ~80 min = 1:20
                    # Split lab: half on each day  
                    lab_half = int(math.ceil((lab_total_min / 2.0) / SLOT_STEP) * SLOT_STEP)  # 120 min = 2:00
                    
                    lec_each = lec_half  
                    lab_sessions = [(day1, lab_half), (day2, lab_half)] 
                elif lec_total_min > 0:
                    lec_each = int(math.ceil((lec_total_min / 2.0) / SLOT_STEP) * SLOT_STEP)
                    lab_sessions = []
                elif lab_total_min > 0:
                    lec_each = 0  
                    if lab_total_min > 180:
                        half = int(math.ceil((lab_total_min / 2.0) / SLOT_STEP) * SLOT_STEP)
                        lab_sessions = [(day1, half), (day2, half)]
                    else:
                        lab_sessions = [(day1, lab_total_min)]
                else:
                    lec_each = 0
                    lab_sessions = []

            # base start heuristic from color - BUT PRIORITIZE EARLY STARTS
            color_base_start = DAY_START + (color % 6) * 90

            for i, sec in enumerate(section_labels):
                sec_enrollees = section_enrollments[i]
                
                if r['Program'] == 'BSIT':
                    has_lecture = lec_total_min > 0
                    has_lab = lab_total_min > 0
                    
                    # --- Schedule LECTURE (if exists) ---
                    if lec_each > 0 and has_lecture:
                        if r['Year'] == 1:
                            lec_room = 'ONLINE'
                            lec_start = get_safe_fallback_time(color_base_start if color_base_start is not None else DAY_START, lec_each)

                        elif r['Year'] == 2:
                            lec_room, lec_start = find_slot_for_block(day1, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room is None:
                                lec_start = get_safe_fallback_time(DAY_START, lec_each)
                                lec_room = 'ONLINE'

                        else:
                            lec_room, lec_start = find_slot_for_block(day1, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room is None:
                                lec_room, lec_start = find_slot_for_block(day1, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room is None:
                                lec_start = get_safe_fallback_time(DAY_START, lec_each)
                                lec_room = 'ONLINE'  

                        lec_timestr = minutes_to_timestr(lec_start, lec_each)
                        cursor.execute("""
                            INSERT INTO schedules (program, year_level, term, section, subject_code, lec_hours, lab_hours, enrollees, room, day, timeslot)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (r['Program'], r['Year'], r.get('Term'), sec, r['Subject'], r['Lec_Hours'], r['Lab_Hours'], sec_enrollees, lec_room, day1, lec_timestr))
                        if lec_room not in ('ONLINE', 'NO ROOM AVAILABLE'):
                            used_slots['room_keys'].add((lec_room, day1, lec_start, lec_each))
                        used_slots['section_keys'].add((sec, day1, lec_start, lec_each))

                    # If BSIT lecture was split, schedule the second half on the paired day
                    if r['Program'] == 'BSIT' and bsit_split_lecture:
                        if r['Year'] == 1:
                            lec2_room, lec2_start = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, color_base_start, lec_start, prefer_lecture_rooms=True)
                            if lec2_room is None:
                                lec2_room, lec2_start = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, color_base_start, None, prefer_lecture_rooms=True)
                            if lec2_room is None:
                                lec2_room, lec2_start = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec2_room is None:
                                lec2_start = lec_start
                                lec2_room = 'ONLINE'
                        elif r['Year'] == 2:
                            lec2_room, lec2_start = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, lec_start, prefer_lecture_rooms=True)
                            if lec2_room is None:
                                lec2_start = lec_start
                                lec2_room = 'ONLINE'
                        else:
                            lec2_room, lec2_start = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, lec_start, prefer_lecture_rooms=True)
                            if lec2_room is None:
                                lec2_room, lec2_start = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec2_room is None:
                                lec2_start = lec_start
                                lec2_room = 'ONLINE'  

                        lec2_timestr = minutes_to_timestr(lec2_start, lec_each)
                        cursor.execute("""
                            INSERT INTO schedules (program, year_level, term, section, subject_code, lec_hours, lab_hours, enrollees, room, day, timeslot)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (r['Program'], r['Year'], r.get('Term'), sec, r['Subject'], r['Lec_Hours'], r['Lab_Hours'], sec_enrollees, lec2_room, day2, lec2_timestr))
                        if lec2_room not in ('ONLINE', 'NO ROOM AVAILABLE'):
                            used_slots['room_keys'].add((lec2_room, day2, lec2_start, lec_each))
                        used_slots['section_keys'].add((sec, day2, lec2_start, lec_each))

                    # --- Schedule LAB (if exists) - ALL YEARS MUST BE FTF ---
                    if lab_sessions and has_lab:
                        lab_day, lab_min = lab_sessions[0]
                        
                        # If lecture is ONLINE, prioritize day1 for lab (better comlab availability)
                        # If lecture is FTF, use day2 for lab (traditional pairing)
                        if lec_room == 'ONLINE':
                            # Lecture is online, so prioritize day1 for lab (more availability)
                            preferred_lab_days = [day1, day2]
                        else:
                            # Lecture got FTF room, so try day2 first for lab (pairing)
                            preferred_lab_days = [day2, day1]
                        
                        lab_room = None
                        lab_start = None
                        
                        for try_day in preferred_lab_days:
                            lab_room, lab_start = find_slot_for_block(try_day, lab_min, rooms['lab'], used_slots, sec, color_base_start)
                            if lab_room is None:
                                lab_room, lab_start = find_slot_for_block(try_day, lab_min, rooms['lab'], used_slots, sec, None)
                            if lab_room is not None:
                                lab_day = try_day  
                                break
                        
                        if lab_room is None:
                            lab_start = get_safe_fallback_time(DAY_START, lab_min)
                            lab_room = 'ONLINE'
                            print(f"  WARNING: {r['Program']} Year {r['Year']} {r['Subject']} Section {sec} LAB forced ONLINE - no physical lab available!")

                        lab_timestr = minutes_to_timestr(lab_start, lab_min)
                        cursor.execute("""
                            INSERT INTO schedules (program, year_level, term, section, subject_code, lec_hours, lab_hours, enrollees, room, day, timeslot)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (r['Program'], r['Year'], r.get('Term'), sec, r['Subject'], r['Lec_Hours'], r['Lab_Hours'], sec_enrollees, lab_room, lab_day, lab_timestr))
                        if lab_room not in ('ONLINE', 'NO ROOM AVAILABLE'):
                            used_slots['room_keys'].add((lab_room, lab_day, lab_start, lab_min))
                        used_slots['section_keys'].add((sec, lab_day, lab_start, lab_min))
                elif r['Program'] in ['BSIS', 'BSCS']:
                    # Year 1: Try FTF on Day 1, if no room try Day 2, whichever gets FTF the other goes online
                    # Year 2: LOWEST PRIORITY - accepts online readily, minimal retries
                    # Year 3&4: HIGH PRIORITY - both days try aggressively for FTF
                    
                    # --- Day 1 Scheduling ---
                    if lec_each > 0:
                        if r['Year'] == 1:
                            lec_room1, lec_start1 = find_slot_for_block(day1, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room1 is None:
                                lec_room1, lec_start1 = find_slot_for_block(day1, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room1 is None:
                                lec_start1 = get_safe_fallback_time(DAY_START, lec_each)
                                lec_room1 = 'ONLINE'
                        
                        elif r['Year'] == 2:
                            lec_room1, lec_start1 = find_slot_for_block(day1, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room1 is None:
                                lec_start1 = get_safe_fallback_time(DAY_START, lec_each)
                                lec_room1 = 'ONLINE'
                        
                        else:
                            lec_room1, lec_start1 = find_slot_for_block(day1, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room1 is None:
                                lec_room1, lec_start1 = find_slot_for_block(day1, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room1 is None:
                                lec_start1 = get_safe_fallback_time(DAY_START, lec_each)
                                lec_room1 = 'ONLINE'
                        
                        # Insert day1 lecture entry
                        lec_timestr1 = minutes_to_timestr(lec_start1, lec_each)
                        cursor.execute("""
                            INSERT INTO schedules (program, year_level, term, section, subject_code, lec_hours, lab_hours, enrollees, room, day, timeslot)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (r['Program'], r['Year'], r.get('Term'), sec, r['Subject'], r['Lec_Hours'], r['Lab_Hours'], sec_enrollees, lec_room1, day1, lec_timestr1))
                        if lec_room1 not in ('ONLINE', 'NO ROOM AVAILABLE'):
                            used_slots['room_keys'].add((lec_room1, day1, lec_start1, lec_each))
                        used_slots['section_keys'].add((sec, day1, lec_start1, lec_each))
                        
                        # Schedule lab immediately after lecture on day1 (if exists)
                        if lab_sessions and len(lab_sessions) >= 1:
                            lab_min1 = lab_sessions[0][1]
                            lab_start1_target = lec_start1 + lec_each
                            
                            if r['Year'] == 1:
                                lab_room1, lab_start1 = find_slot_for_block(day1, lab_min1, rooms['lab'], used_slots, sec, color_base_start, lab_start1_target)
                                if lab_room1 is None:
                                    lab_room1, lab_start1 = find_slot_for_block(day1, lab_min1, rooms['lab'], used_slots, sec, color_base_start)
                                if lab_room1 is None:
                                    lab_room1, lab_start1 = find_slot_for_block(day1, lab_min1, rooms['lab'], used_slots, sec, None)
                                if lab_room1 is None:
                                    lab_start1 = lab_start1_target
                                    lab_room1 = 'ONLINE'
                            
                            elif r['Year'] == 2:
                                if lec_room1 == 'ONLINE':
                                    lab_room1 = 'ONLINE'
                                    lab_start1 = lab_start1_target
                                else:
                                    lab_room1, lab_start1 = find_slot_for_block(day1, lab_min1, rooms['lab'], used_slots, sec, None, lab_start1_target)
                                    if lab_room1 is None:
                                        lab_start1 = lab_start1_target
                                        lab_room1 = 'ONLINE'
                            
                            else:
                                lab_room1, lab_start1 = find_slot_for_block(day1, lab_min1, rooms['lab'], used_slots, sec, color_base_start, lab_start1_target)
                                if lab_room1 is None:
                                    lab_room1, lab_start1 = find_slot_for_block(day1, lab_min1, rooms['lab'], used_slots, sec, color_base_start)
                                if lab_room1 is None:
                                    lab_room1, lab_start1 = find_slot_for_block(day1, lab_min1, rooms['lab'], used_slots, sec, None)
                                if lab_room1 is None:
                                    lab_start1 = lab_start1_target
                                    lab_room1 = 'ONLINE'  
                            
                            # Insert day1 lab entry
                            lab_timestr1 = minutes_to_timestr(lab_start1, lab_min1)
                            cursor.execute("""
                                INSERT INTO schedules (program, year_level, term, section, subject_code, lec_hours, lab_hours, enrollees, room, day, timeslot)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """, (r['Program'], r['Year'], r.get('Term'), sec, r['Subject'], r['Lec_Hours'], r['Lab_Hours'], sec_enrollees, lab_room1, day1, lab_timestr1))
                            if lab_room1 not in ('ONLINE', 'NO ROOM AVAILABLE'):
                                used_slots['room_keys'].add((lab_room1, day1, lab_start1, lab_min1))
                            used_slots['section_keys'].add((sec, day1, lab_start1, lab_min1))
                    
                    # --- Day 2 Scheduling ---
                    if lec_each > 0:
                        if r['Year'] == 1:
                            # Year 1 Day 2: If Day 1 was ONLINE, try FTF on Day 2. Otherwise assign ONLINE.
                            if lec_room1 == 'ONLINE':
                                # Day 1 didn't get physical room, so try FTF on Day 2
                                lec_room2, lec_start2 = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, lec_start1, prefer_lecture_rooms=True)
                                if lec_room2 is None:
                                    lec_room2, lec_start2 = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                                if lec_room2 is None:
                                    # No physical room on either day - keep Day 2 ONLINE
                                    lec_start2 = lec_start1
                                    lec_room2 = 'ONLINE'
                            else:
                                # Day 1 got physical room, so Day 2 is ONLINE
                                lec_room2 = 'ONLINE'
                                lec_start2 = lec_start1
                        
                        elif r['Year'] == 2:
                            lec_room2, lec_start2 = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, lec_start1, prefer_lecture_rooms=True)
                            if lec_room2 is None:
                                lec_start2 = lec_start1
                                lec_room2 = 'ONLINE'
                        
                        else:
                            lec_room2, lec_start2 = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, lec_start1, prefer_lecture_rooms=True)
                            if lec_room2 is None:
                                lec_room2, lec_start2 = find_slot_for_block(day2, lec_each, rooms['lecture'], used_slots, sec, None, None, prefer_lecture_rooms=True)
                            if lec_room2 is None:
                                lec_start2 = lec_start1
                                lec_room2 = 'ONLINE' 

                        # Insert day2 lecture entry
                        lec_timestr2 = minutes_to_timestr(lec_start2, lec_each)
                        cursor.execute("""
                            INSERT INTO schedules (program, year_level, term, section, subject_code, lec_hours, lab_hours, enrollees, room, day, timeslot)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (r['Program'], r['Year'], r.get('Term'), sec, r['Subject'], r['Lec_Hours'], r['Lab_Hours'], sec_enrollees, lec_room2, day2, lec_timestr2))
                        if lec_room2 not in ('ONLINE', 'NO ROOM AVAILABLE'):
                            used_slots['room_keys'].add((lec_room2, day2, lec_start2, lec_each))
                        used_slots['section_keys'].add((sec, day2, lec_start2, lec_each))

                        # Schedule lab on day2 (if exists)
                        if lab_sessions and len(lab_sessions) >= 2:
                            lab_min2 = lab_sessions[1][1]
                            lab_start2_target = lec_start2 + lec_each

                            if r['Year'] == 1:
                                if lab_room1 == 'ONLINE':
                                    # Day 1 lab didn't get physical room, so try aggressively on Day 2
                                    lab_room2, lab_start2 = find_slot_for_block(day2, lab_min2, rooms['lab'], used_slots, sec, color_base_start, lab_start2_target)
                                    if lab_room2 is None:
                                        lab_room2, lab_start2 = find_slot_for_block(day2, lab_min2, rooms['lab'], used_slots, sec, color_base_start)
                                    if lab_room2 is None:
                                        lab_room2, lab_start2 = find_slot_for_block(day2, lab_min2, rooms['lab'], used_slots, sec, None)
                                    if lab_room2 is None:
                                        lab_start2 = lab_start2_target
                                        lab_room2 = 'ONLINE'
                                else:
                                    lab_room2 = 'ONLINE'
                                    lab_start2 = lab_start2_target
                            
                            elif r['Year'] == 2:
                                lab_room2, lab_start2 = find_slot_for_block(day2, lab_min2, rooms['lab'], used_slots, sec, None, lab_start2_target)
                                if lab_room2 is None:
                                    lab_start2 = lab_start2_target
                                    lab_room2 = 'ONLINE'
                            
                            else:
                                lab_room2, lab_start2 = find_slot_for_block(day2, lab_min2, rooms['lab'], used_slots, sec, color_base_start, lab_start2_target)
                                if lab_room2 is None:
                                    lab_room2, lab_start2 = find_slot_for_block(day2, lab_min2, rooms['lab'], used_slots, sec, color_base_start)
                                if lab_room2 is None:
                                    lab_room2, lab_start2 = find_slot_for_block(day2, lab_min2, rooms['lab'], used_slots, sec, None)
                                if lab_room2 is None:
                                    lab_start2 = lab_start2_target
                                    lab_room2 = 'ONLINE'  

                            # Insert day2 lab entry
                            lab_timestr2 = minutes_to_timestr(lab_start2, lab_min2)
                            cursor.execute("""
                                INSERT INTO schedules (program, year_level, term, section, subject_code, lec_hours, lab_hours, enrollees, room, day, timeslot)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """, (r['Program'], r['Year'], r.get('Term'), sec, r['Subject'], r['Lec_Hours'], r['Lab_Hours'], sec_enrollees, lab_room2, day2, lab_timestr2))
                            if lab_room2 not in ('ONLINE', 'NO ROOM AVAILABLE'):
                                used_slots['room_keys'].add((lab_room2, day2, lab_start2, lab_min2))
                            used_slots['section_keys'].add((sec, day2, lab_start2, lab_min2))
                
    conn.commit()
    
def find_combined_slot(day, lec_duration, lab_duration, rooms, used_slots, section, color_base_start=None):
    """Find consecutive slots for lecture + lab combination for BSIS/BSCS"""
    total_duration = lec_duration + lab_duration
    
    candidates = []
    if color_base_start is not None:
        for off in (0, SLOT_STEP, -SLOT_STEP, 2*SLOT_STEP, -2*SLOT_STEP):
            c = color_base_start + off
            if DAY_START <= c <= DAY_END - total_duration:
                candidates.append(c)
    
    cur = DAY_START
    while cur <= DAY_END - total_duration:
        if cur not in candidates:
            candidates.append(cur)
        cur += SLOT_STEP
    
    for start_min in candidates:
        if start_min < DAY_START or (start_min + total_duration) > DAY_END:
            continue
            
        combined_rooms = list(set(rooms['lecture'] + rooms['lab']))  
        
        for room in combined_rooms:
            conflict = False
            
            # Check room conflicts for entire duration
            for (r_room, r_day, r_start, r_dur) in used_slots['room_keys']:
                if r_day == day and r_room == room and overlaps(r_start, r_dur, start_min, total_duration):
                    conflict = True
                    break
            if conflict:
                continue
                
            # Check section conflicts for entire duration
            for (s_sec, s_day, s_start, s_dur) in used_slots['section_keys']:
                if s_day == day and s_sec == section and overlaps(s_start, s_dur, start_min, total_duration):
                    conflict = True
                    break
            if conflict:
                continue
                
            return room, start_min
    
    return None, None

# -------------------- Term Management Functions --------------------
def get_terms_from_records(records):
    """Extract unique terms from CSV records"""
    terms = set()
    for r in records:
        term = r.get('Term')
        if term is not None:
            terms.add(term)
        else:
            terms.add(None) 
    return sorted([t for t in terms if t is not None]) + ([None] if None in terms else [])

def get_terms_from_database(cursor):
    """Get list of unique terms currently in the database"""
    cursor.execute("SELECT DISTINCT term FROM schedules ORDER BY term")
    rows = cursor.fetchall()
    terms = []
    for (term,) in rows:
        terms.append(term)
    return terms

def delete_terms_from_database(cursor, conn, terms_to_delete):
    """Delete schedules for specific terms from database"""
    if not terms_to_delete:
        return 0
    
    deleted_count = 0
    for term in terms_to_delete:
        if term is None:
            cursor.execute("DELETE FROM schedules WHERE term IS NULL")
        else:
            cursor.execute("DELETE FROM schedules WHERE term = %s", (term,))
        deleted_count += cursor.rowcount
    
    conn.commit()
    return deleted_count

# -------------------- Conflict Checker (improved) --------------------
def check_conflicts(cursor):
    cursor.execute("SELECT section, room, day, timeslot, subject_code, term FROM schedules")
    rows = cursor.fetchall()

    def parse_timeslot(ts):
        try:
            s, e = ts.split('-')
            sh, sm = map(int, s.split(':'))
            eh, em = map(int, e.split(':'))
            start = sh * 60 + sm
            duration = (eh * 60 + em) - start
            return start, duration
        except Exception:
            return None, None

    # Group by TERM first - conflicts only matter within the same term
    terms_data = {}
    for sec, room, day, ts, subj, term in rows:
        # Skip non-physical sessions - these cannot have room conflicts
        if room in ('ONLINE', 'UNSCHEDULED', 'NO_SCHEDULE_NEEDED', 'NO ROOM AVAILABLE'):
            continue
        start, dur = parse_timeslot(ts)
        if start is None:
            continue
        terms_data.setdefault(term, {'section_bookings': {}, 'room_bookings': {}})
        terms_data[term]['section_bookings'].setdefault((sec, day), []).append((start, dur, subj))
        terms_data[term]['room_bookings'].setdefault((room, day), []).append((start, dur, subj))

    conflicts = []

    # Check conflicts WITHIN each term separately
    for term, term_data in terms_data.items():
        # Section conflicts within the term
        for (sec, day), bookings in term_data['section_bookings'].items():
            bookings_sorted = sorted(bookings, key=lambda x: x[0])
            for i in range(len(bookings_sorted)):
                for j in range(i+1, len(bookings_sorted)):
                    if overlaps(bookings_sorted[i][0], bookings_sorted[i][1], bookings_sorted[j][0], bookings_sorted[j][1]):
                        conflicts.append(f"Term {term} - Section {sec} overlap on {day}: {bookings_sorted[i][2]} vs {bookings_sorted[j][2]}")

        # Room conflicts within the term
        for (room, day), bookings in term_data['room_bookings'].items():
            bookings_sorted = sorted(bookings, key=lambda x: x[0])
            for i in range(len(bookings_sorted)):
                for j in range(i+1, len(bookings_sorted)):
                    if overlaps(bookings_sorted[i][0], bookings_sorted[i][1], bookings_sorted[j][0], bookings_sorted[j][1]):
                        conflicts.append(f"Term {term} - Room {room} double-booked on {day}: {bookings_sorted[i][2]} vs {bookings_sorted[j][2]}")

    return conflicts

# -------------------- GUI --------------------
class ScheduleApp:
    def __init__(self, root):
        self.conn, self.cursor = init_db()

        self.root = root
        self.root.title("SCS Class Schedule Generator")
        self.root.geometry("1400x800")
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Header.TFrame', background='#2c3e50')
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'), foreground='#2c3e50')
        style.configure('Control.TButton', font=('Arial', 10), padding=5)
        
        header_frm = tk.Frame(root, bg='#2c3e50', height=60)
        header_frm.pack(fill='x', padx=0, pady=0)
        header_frm.pack_propagate(False)
        
        title_label = tk.Label(header_frm, text="📅 SCS Class Schedule Generator", 
                               font=('Arial', 18, 'bold'), bg='#2c3e50', fg='white')
        title_label.pack(side='left', padx=20, pady=15)
        
        tk.Button(header_frm, text="📁 Load CSV", command=self.upload_and_generate,
                 bg='#3498db', fg='white', font=('Arial', 10, 'bold'), 
                 padx=15, pady=8, relief='flat', cursor='hand2').pack(side='right', padx=5, pady=12)
        tk.Button(header_frm, text="🗑️ Clear Database", command=self.clear_db,
                 bg='#e74c3c', fg='white', font=('Arial', 10, 'bold'), 
                 padx=15, pady=8, relief='flat', cursor='hand2').pack(side='right', padx=5, pady=12)
        
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)
        
        # Tab 1: Schedule Table View
        self.table_frame = tk.Frame(self.notebook, bg='white')
        self.notebook.add(self.table_frame, text='📋 Schedule Table')
        
        filter_frm = tk.Frame(self.table_frame, bg='#ecf0f1', relief='raised', bd=1)
        filter_frm.pack(fill='x', padx=5, pady=5)
        
        filter_label = tk.Label(filter_frm, text="Filters:", font=('Arial', 10, 'bold'), 
                               bg='#ecf0f1', fg='#2c3e50')
        filter_label.grid(row=0, column=0, padx=10, pady=8, sticky='w')
        
        tk.Label(filter_frm, text="Section:", bg='#ecf0f1', font=('Arial', 9)).grid(row=0, column=1, padx=(20,5), pady=8)
        self.section_entry = tk.Entry(filter_frm, width=15, font=('Arial', 9))
        self.section_entry.grid(row=0, column=2, padx=(0,15), pady=8)
        self.section_entry.bind('<Return>', self.on_filter_change)
        
        tk.Label(filter_frm, text="Term:", bg='#ecf0f1', font=('Arial', 9)).grid(row=0, column=3, padx=5, pady=8)
        self.term_entry = tk.Entry(filter_frm, width=10, font=('Arial', 9))
        self.term_entry.grid(row=0, column=4, padx=(0,15), pady=8)
        self.term_entry.bind('<Return>', self.on_filter_change)
        
        tk.Button(filter_frm, text="Apply", command=self.add_filters, bg='#27ae60', fg='white',
                 font=('Arial', 9, 'bold'), padx=12, pady=4, relief='flat', cursor='hand2').grid(row=0, column=5, padx=5, pady=8)
        tk.Button(filter_frm, text="Clear", command=self.clear_filters, bg='#95a5a6', fg='white',
                 font=('Arial', 9, 'bold'), padx=12, pady=4, relief='flat', cursor='hand2').grid(row=0, column=6, padx=5, pady=8)
        
        tk.Label(filter_frm, text="Sort by:", bg='#ecf0f1', font=('Arial', 9)).grid(row=0, column=7, padx=(30,5), pady=8)
        self.sort_option = ttk.Combobox(filter_frm, values=["Day", "Time", "Subject", "Room", "Section", "Program"], 
                                       state="readonly", width=12, font=('Arial', 9))
        self.sort_option.set("Day")
        self.sort_option.grid(row=0, column=8, padx=(0,15), pady=8)
        self.sort_option.bind('<<ComboboxSelected>>', self.on_filter_change)
        
        tk.Button(filter_frm, text="🔄 Refresh", command=self.refresh_tree, bg='#3498db', fg='white',
                 font=('Arial', 9, 'bold'), padx=12, pady=4, relief='flat', cursor='hand2').grid(row=0, column=9, padx=5, pady=8)
        tk.Button(filter_frm, text="📥 Export CSV", command=self.export_csv, bg='#16a085', fg='white',
                 font=('Arial', 9, 'bold'), padx=12, pady=4, relief='flat', cursor='hand2').grid(row=0, column=10, padx=5, pady=8)
        
        filter_frm.columnconfigure(11, weight=1)
        
        self.current_section_filter = None
        self.current_term_filter = None

        table_container = tk.Frame(self.table_frame)
        table_container.pack(expand=True, fill='both', padx=5, pady=5)
        
        vsb = ttk.Scrollbar(table_container, orient="vertical")
        hsb = ttk.Scrollbar(table_container, orient="horizontal")
        
        cols = ("program","year_level","term","section","subject_code","room","day","timeslot")
        self.tree = ttk.Treeview(table_container, columns=cols, show="headings", 
                                yscrollcommand=vsb.set, xscrollcommand=hsb.set, height=20)
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        column_configs = {
            "program": ("Program", 100),
            "year_level": ("Year", 60),
            "term": ("Term", 60),
            "section": ("Section", 100),
            "subject_code": ("Subject Code", 150),
            "room": ("Room", 120),
            "day": ("Day", 100),
            "timeslot": ("Time Slot", 150)
        }
        
        for col, (header, width) in column_configs.items():
            self.tree.heading(col, text=header, anchor='center')
            self.tree.column(col, width=width, anchor='center')
        
        self.tree.tag_configure('oddrow', background='#f9f9f9')
        self.tree.tag_configure('evenrow', background='#ffffff')
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)
        
        # Tab 2: Room Visualization
        self.visual_frame = tk.Frame(self.notebook, bg='white')
        self.notebook.add(self.visual_frame, text='🏫 Room Allocation')
        
        self.create_room_visualization()
        
        self.refresh_tree()

    def upload_and_generate(self):
        filename = filedialog.askopenfilename(title="Select CSV file", filetypes=[("CSV Files", "*.csv")])
        if not filename:
            return
        records = upload_csv(filename)
        if not records:
            return

        csv_terms = get_terms_from_records(records)
        db_terms = get_terms_from_database(self.cursor)
        
        conflicting_terms = [t for t in csv_terms if t in db_terms]
        new_terms = [t for t in csv_terms if t not in db_terms]
        existing_only_terms = [t for t in db_terms if t not in csv_terms]
        
        message_parts = []
        message_parts.append("📊 CSV Analysis:")
        message_parts.append(f"  • CSV contains {len(csv_terms)} term(s): {', '.join([str(t) if t is not None else 'None' for t in csv_terms])}")
        message_parts.append(f"  • Database has {len(db_terms)} term(s): {', '.join([str(t) if t is not None else 'None' for t in db_terms])}")
        message_parts.append("")
        
        if conflicting_terms:
            message_parts.append("⚠️ CONFLICTS DETECTED:")
            message_parts.append(f"  • Term(s) {', '.join([str(t) if t is not None else 'None' for t in conflicting_terms])} exist in BOTH CSV and database")
            message_parts.append("")
            message_parts.append("📋 What will happen:")
            message_parts.append(f"  ✓ DELETE existing data for term(s): {', '.join([str(t) if t is not None else 'None' for t in conflicting_terms])}")
            message_parts.append(f"  ✓ INSERT new data for term(s): {', '.join([str(t) if t is not None else 'None' for t in csv_terms])}")
            if existing_only_terms:
                message_parts.append(f"  ✓ KEEP existing data for term(s): {', '.join([str(t) if t is not None else 'None' for t in existing_only_terms])}")
            message_parts.append("")
            message_parts.append("Do you want to proceed?")
        elif new_terms:
            message_parts.append("✅ NO CONFLICTS:")
            message_parts.append(f"  • New term(s) {', '.join([str(t) if t is not None else 'None' for t in new_terms])} will be ADDED to database")
            if existing_only_terms:
                message_parts.append(f"  • Existing term(s) {', '.join([str(t) if t is not None else 'None' for t in existing_only_terms])} will be KEPT")
            message_parts.append("")
            message_parts.append("Proceed with import?")
        else:
            message_parts.append("✅ Database is empty. All terms will be added.")
            message_parts.append("")
            message_parts.append("Proceed with import?")
        
        proceed = messagebox.askyesno("Term Import", "\n".join(message_parts))
        
        if not proceed:
            messagebox.showinfo("Cancelled", "Import cancelled by user.")
            return
        
        if conflicting_terms:
            deleted_count = delete_terms_from_database(self.cursor, self.conn, conflicting_terms)
            print(f"Deleted {deleted_count} existing schedule entries for conflicting terms.")
        
        generate_schedule(records, self.cursor, self.conn)
        
        conflicts = check_conflicts(self.cursor)
        
        success_msg = f"✅ Schedule generated successfully!\n\n"
        success_msg += f"📊 Terms in database: {', '.join([str(t) if t is not None else 'None' for t in get_terms_from_database(self.cursor)])}"
        messagebox.showinfo("Success", success_msg)
        
        if conflicts:
            conflict_msg = "⚠️ SCHEDULE CONFLICTS DETECTED\n\n"
            conflict_msg += "The following conflicts were found in the generated schedule:\n\n"
            conflict_msg += "\n".join(conflicts)
            conflict_msg += "\n\nPlease review and resolve these conflicts."
            messagebox.showwarning("Schedule Conflicts Detected", conflict_msg)
        else:
            no_conflict_msg = "✅ NO CONFLICTS DETECTED\n\n"
            no_conflict_msg += "All schedules have been validated:\n"
            no_conflict_msg += "  • No room double-bookings\n"
            no_conflict_msg += "  • No section overlaps\n"
            no_conflict_msg += "  • All time slots are valid\n\n"
            no_conflict_msg += "The schedule is ready to use!"
            messagebox.showinfo("Validation Passed", no_conflict_msg)
        
        self.refresh_tree()

    def add_filters(self):
        """Apply section and term filters based on user input"""
        section = self.section_entry.get().strip()
        term = self.term_entry.get().strip()
        
        if section or term:
            self.current_section_filter = section if section else None
            self.current_term_filter = term if term else None
            self.refresh_tree()
        else:
            messagebox.showwarning("Warning", "Please enter a section name and/or term to filter.")
    
    def clear_filters(self):
        """Clear both section and term filters"""
        self.current_section_filter = None
        self.current_term_filter = None
        self.section_entry.delete(0, tk.END)
        self.term_entry.delete(0, tk.END)
        self.refresh_tree()
    
    def on_filter_change(self, event=None):
        """Handle filter or sort option changes"""
        if event and (event.widget == self.section_entry or event.widget == self.term_entry):
    
            self.add_filters()
        else:
            self.refresh_tree()
    
    def create_room_visualization(self):
        """Create visual room allocation grid similar to the provided image"""
      
        control_frm = tk.Frame(self.visual_frame, bg='#ecf0f1', relief='raised', bd=1)
        control_frm.pack(fill='x', padx=5, pady=5)
        
        tk.Label(control_frm, text="Room View Filters:", font=('Arial', 10, 'bold'), 
                bg='#ecf0f1', fg='#2c3e50').pack(side='left', padx=10, pady=8)
        
        tk.Label(control_frm, text="Term:", bg='#ecf0f1', font=('Arial', 9)).pack(side='left', padx=(20,5), pady=8)
        self.visual_term_entry = tk.Entry(control_frm, width=10, font=('Arial', 9))
        self.visual_term_entry.pack(side='left', padx=(0,15), pady=8)
        
        tk.Button(control_frm, text="🔄 Refresh View", command=self.refresh_room_visualization, 
                 bg='#3498db', fg='white', font=('Arial', 9, 'bold'), 
                 padx=12, pady=4, relief='flat', cursor='hand2').pack(side='left', padx=5, pady=8)
       
        canvas_frame = tk.Frame(self.visual_frame)
        canvas_frame.pack(expand=True, fill='both', padx=5, pady=5)
        
        self.room_canvas = tk.Canvas(canvas_frame, bg='white')
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient='vertical', command=self.room_canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient='horizontal', command=self.room_canvas.xview)
        
        self.room_canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        v_scrollbar.pack(side='right', fill='y')
        h_scrollbar.pack(side='bottom', fill='x')
        self.room_canvas.pack(side='left', expand=True, fill='both')
        
        
        self.room_grid_frame = tk.Frame(self.room_canvas, bg='white')
        self.canvas_window = self.room_canvas.create_window((0, 0), window=self.room_grid_frame, anchor='nw')
        
      
        self.room_grid_frame.bind('<Configure>', lambda e: self.room_canvas.configure(scrollregion=self.room_canvas.bbox('all')))
        
       
        self.refresh_room_visualization()
    
    def refresh_room_visualization(self):
        """Refresh the room allocation grid"""

        for widget in self.room_grid_frame.winfo_children():
            widget.destroy()
        
      
        term_filter = self.visual_term_entry.get().strip()
        
    
        query = "SELECT room, day, timeslot, subject_code, section FROM schedules WHERE room NOT IN ('ONLINE', 'NO_SCHEDULE_NEEDED', 'UNSCHEDULED')"
        params = []
        
        if term_filter:
            query += " AND term = %s"
            params.append(term_filter)
        
        query += " ORDER BY FIELD(day, 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'), timeslot"
        
        self.cursor.execute(query, tuple(params))
        schedules = self.cursor.fetchall()
        
        room_data = {}
        all_rooms = ['203', '204', 'ComLab1', 'ComLab5', 'ComLab6']
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        
        for room in all_rooms:
            room_data[room] = {day: [] for day in days}
        
        for room, day, timeslot, subject, section in schedules:
            if room in room_data:
                room_data[room][day].append((timeslot, subject, section))
        
        def time_to_minutes(time_str):
            parts = time_str.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        
        def calculate_rowspan(start_time, end_time):
            start_min = time_to_minutes(start_time)
            end_min = time_to_minutes(end_time)
            duration = end_min - start_min
            return (duration // 20) * 2
        
        header_bg = '#2c3e50'
        header_fg = 'white'
        
        tk.Label(self.room_grid_frame, text="From", bg=header_bg, fg=header_fg, 
                font=('Arial', 9, 'bold'), relief='raised', bd=1, width=8).grid(row=0, column=0, sticky='nsew', padx=1, pady=1)
        tk.Label(self.room_grid_frame, text="To", bg=header_bg, fg=header_fg, 
                font=('Arial', 9, 'bold'), relief='raised', bd=1, width=8).grid(row=1, column=0, sticky='nsew', padx=1, pady=1)
        
        col = 1
        for room in all_rooms:
            room_color = '#27ae60' if room.startswith('ComLab') else '#3498db'
            for day in days:
                tk.Label(self.room_grid_frame, text=day, bg=room_color, fg='white', 
                        font=('Arial', 8, 'bold'), relief='raised', bd=1, width=12).grid(row=0, column=col, sticky='nsew', padx=1, pady=1)
                col += 1
        
        col = 1
        for room in all_rooms:
            room_color = '#d5f4e6' if room.startswith('ComLab') else '#d6eaf8'
            for day in days:
                tk.Label(self.room_grid_frame, text=room, bg=room_color, 
                        font=('Arial', 8, 'bold'), relief='raised', bd=1).grid(row=1, column=col, sticky='nsew', padx=1, pady=1)
                col += 1
        
        time_slots = []
        for hour in range(7, 21):
            for minute in [0, 20, 40]:
                if hour < 21 or minute == 0:
                    time_slots.append(f"{hour:02d}:{minute:02d}")
        
        row_idx = 2
        for i, start_time in enumerate(time_slots[:-1]):
            end_time = time_slots[i + 1]
            
            tk.Label(self.room_grid_frame, text=start_time, bg='#ecf0f1', 
                    font=('Arial', 8), relief='solid', bd=1, width=8).grid(row=row_idx, column=0, sticky='nsew', padx=1, pady=1)
            row_idx += 1
            
            tk.Label(self.room_grid_frame, text=end_time, bg='#ecf0f1', 
                    font=('Arial', 8), relief='solid', bd=1, width=8).grid(row=row_idx, column=0, sticky='nsew', padx=1, pady=1)
            row_idx += 1
        
        occupied_cells = {}
        
        col = 1
        for room in all_rooms:
            for day in days:
                occupied_cells[col] = set()
                
                classes = sorted(room_data[room][day], key=lambda x: x[0])
                
                for timeslot, subject, section in classes:
                    slot_start, slot_end = timeslot.split('-')
                    
                    start_row = 2  # Start after headers
                    for i, ts in enumerate(time_slots[:-1]):
                        if ts == slot_start:
                            start_row = 2 + (i * 2)
                            break
                    
                    rowspan = calculate_rowspan(slot_start, slot_end)
                    
                    cell_range = set(range(start_row, start_row + rowspan))
                    if not cell_range.intersection(occupied_cells.get(col, set())):
                       
                        cell_text = f"{subject}\n{section}\n{timeslot}"
                        cell = tk.Label(self.room_grid_frame, text=cell_text, bg='#fff3cd', 
                                      font=('Arial', 8, 'bold'), relief='solid', bd=2, 
                                      wraplength=90, justify='center', anchor='center',
                                      fg='#2c3e50')
                        cell.grid(row=start_row, column=col, rowspan=rowspan, sticky='nsew', padx=1, pady=1)
                        
                        occupied_cells[col] = occupied_cells.get(col, set()).union(cell_range)
                
                for row in range(2, row_idx):
                    if row not in occupied_cells.get(col, set()):
                        empty_cell = tk.Label(self.room_grid_frame, text="", bg='white', 
                                            relief='solid', bd=1)
                        empty_cell.grid(row=row, column=col, sticky='nsew', padx=1, pady=1)
                
                col += 1
        
        for i in range(row_idx):
            self.room_grid_frame.grid_rowconfigure(i, weight=1, minsize=20)
        for i in range(col):
            self.room_grid_frame.grid_columnconfigure(i, weight=1)

    def refresh_tree(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        
        query = "SELECT program, year_level, term, section, subject_code, room, day, timeslot FROM schedules"
        params = []
        where_conditions = []
        
        if self.current_section_filter:
            where_conditions.append("section LIKE %s")
            params.append(f"%{self.current_section_filter}%")
        
        if self.current_term_filter:
            where_conditions.append("term = %s")
            params.append(self.current_term_filter)
        
        if where_conditions:
            query += " WHERE " + " AND ".join(where_conditions)
        
        sort_option_value = getattr(self, 'sort_option', None)
        if sort_option_value:
            sort_by = sort_option_value.get()
            if sort_by == "Day":
                query += " ORDER BY FIELD(day, 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')"
            elif sort_by == "Time":
                query += " ORDER BY timeslot, FIELD(day, 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')"
            elif sort_by == "Subject":
                query += " ORDER BY subject_code"
            elif sort_by == "Room":
                query += " ORDER BY room"
            elif sort_by == "Section":  
                query += " ORDER BY section"
            elif sort_by == "Program":
                query += " ORDER BY program, year_level"
        
        self.cursor.execute(query, params)
        
        for idx, row in enumerate(self.cursor.fetchall()):
            tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
            self.tree.insert('', 'end', values=row, tags=(tag,))
        
        if self.notebook.index(self.notebook.select()) == 1:
            self.refresh_room_visualization()

    def clear_db(self):
        if messagebox.askyesno("Confirm", "Clear all schedules from database?"):
            self.cursor.execute("TRUNCATE TABLE schedules")
            self.conn.commit()
            self.refresh_tree()
            messagebox.showinfo("Cleared", "All schedules cleared.")

    def export_csv(self):
        """Export schedule to CSV file"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Save Schedule As"
        )
        if not filepath:
            return

        query = "SELECT program, year_level, term, section, subject_code, room, day, timeslot FROM schedules"
        params = []
        where_conditions = []

        if self.current_section_filter:
            where_conditions.append("section LIKE %s")
            params.append(f"%{self.current_section_filter}%")

        if self.current_term_filter:
            where_conditions.append("term = %s")
            params.append(self.current_term_filter)

        if where_conditions:
            query += " WHERE " + " AND ".join(where_conditions)

        sort_option_value = getattr(self, 'sort_option', None)
        if sort_option_value:
            sort_by = sort_option_value.get()
            if sort_by == "Day":
                query += " ORDER BY FIELD(day, 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')"
            elif sort_by == "Time":
                query += " ORDER BY timeslot"
            elif sort_by == "Subject":
                query += " ORDER BY subject_code"
            elif sort_by == "Room":
                query += " ORDER BY room"
            elif sort_by == "Section":
                query += " ORDER BY section"
            elif sort_by == "Program":
                query += " ORDER BY program, year_level"

        # Execute and fetch data
        self.cursor.execute(query, tuple(params))
        rows = self.cursor.fetchall()

        # Write to CSV
        with open(filepath, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            headers = ["Program", "Year Level", "Term", "Section", "Subject Code", "Room", "Day", "Timeslot"]
            writer.writerow(headers)
            writer.writerows(rows)

        messagebox.showinfo("Export Complete", f"Schedule exported successfully to:\n{filepath}")
if __name__ == '__main__':
    root = tk.Tk()
    app = ScheduleApp(root)
    root.mainloop()
