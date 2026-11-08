# SCS Class Schedule Generator

The **SCS Class Schedule Generator** is a Python desktop application for creating and managing class schedules for BSCS, BSIS, and BSIT programs. It imports course offerings from a CSV file, assigns days, rooms, and time slots, stores the results in MySQL, checks for conflicts, and provides table and room-grid views of the generated schedule.

## Features

- Import and normalize class data from CSV files.
- Accept common variations of CSV column names, such as `Year`, `yearlevel`, and `yr`.
- Group records by academic term and merge related subject records.
- Assign classes to day pairings:
  - Monday/Thursday
  - Tuesday/Friday
  - Wednesday/Saturday
- Use graph coloring to reduce same-year scheduling conflicts.
- Split large classes into sections of up to 40 students.
- Schedule classes in 20-minute increments between **7:00 AM and 9:00 PM**.
- Assign lecture classes to regular classrooms (`203`, `204`).
- Assign laboratory classes to computer laboratories (`ComLab1`, `ComLab5`, `ComLab6`).
- Balance room usage across available rooms.
- Use `ONLINE` when a physical room cannot be assigned without creating a conflict.
- Detect section overlaps and room double-bookings.
- Filter and sort schedules by section or term, and sort by day, time, subject, room, section, or program.
- Display a visual room allocation grid.
- Export schedules to CSV.
- Replace existing schedules when an imported CSV contains the same term, while preserving schedules for other terms.

## Technology Stack

- Python 3
- Tkinter and `ttk` for the desktop interface
- MySQL for schedule storage
- `mysql-connector-python` for database access
- NetworkX for conflict-graph construction and graph coloring
- Python's built-in `csv` module for import and export

## Requirements

1. Python 3.8 or newer.
2. A running MySQL Server instance.
3. A MySQL account that can create the `schedule_db` database and its tables.
4. Python dependencies:

   ```text
   mysql-connector-python
   networkx
   ```

The application currently connects using:

```text
Host: localhost
User: root
Password: empty
Database: schedule_db
```

These settings are defined in `init_db()` in [`Bibat_Borbon_Castillo_Estabaya_Natividad_SourceCode.py`](./Bibat_Borbon_Castillo_Estabaya_Natividad_SourceCode.py). Update that function before running the application if your MySQL installation uses different credentials.

## Installation

From the project directory, create and activate a virtual environment if desired:

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install mysql-connector-python networkx
```

If PowerShell prevents script activation, install the packages with:

```powershell
py -m pip install mysql-connector-python networkx
```

Make sure MySQL Server is running before launching the application. The program creates the `schedule_db` database and `schedules` table automatically on startup.

## Running the Application

Run the main source file:

```powershell
py .\Bibat_Borbon_Castillo_Estabaya_Natividad_SourceCode.py
```

On Windows, [`run_schedule.bat`](./run_schedule.bat) can also be used if it has been configured for the local Python installation.

The application opens a window titled **SCS Class Schedule Generator**.

## CSV Input Format

The CSV file should contain the following columns:

| Column | Required | Description |
|---|---:|---|
| `Program` | Yes | Academic program, such as `BSCS`, `BSIS`, or `BSIT` |
| `Year` | Yes | Year level as an integer |
| `Term` | Recommended | Academic term identifier |
| `Subject` | Yes | Subject or course code |
| `Lec_Hours` | Recommended | Lecture hours |
| `Lab_Hours` | Recommended | Laboratory hours |
| `Enrollees` | Recommended | Number of students |
| `Section` | Optional | Existing section name |

Example:

```csv
Program,Year,Term,Subject,Lec_Hours,Lab_Hours,Enrollees,Section
BSCS,1,1,CS101,2,0,35,BSCS1A
BSCS,1,1,CS102,2,1.5,85,
BSIT,2,1,IT201,3,0,40,BSIT2A
```

`Program`, `Year`, and `Subject` must be populated. Numeric fields should contain valid numbers; missing lecture or laboratory hours are treated as zero. The importer accepts several case-insensitive header aliases, including `prog`, `yearlevel`, `yr`, `subjectcode`, `lec hours`, and `lab hours`.

## Using the Interface

### 1. Load and generate a schedule

1. Click **Load CSV**.
2. Select a CSV file.
3. Review the CSV and database term analysis.
4. Confirm replacement when the file contains terms already stored in the database.
5. The schedule is generated, saved, and validated automatically.

### 2. Schedule Table tab

The table displays:

- Program
- Year
- Term
- Section
- Subject Code
- Room
- Day
- Time Slot

Use the filter fields to search by section or term. Use the sort selector to order records, then click **Refresh** to reload the table. **Export CSV** saves the currently displayed schedule data.

### 3. Room Allocation tab

The room view shows physical room usage for Monday through Saturday, using 20-minute time intervals. Regular classrooms and computer laboratories are color-coded separately. `ONLINE`, `NO_SCHEDULE_NEEDED`, and `UNSCHEDULED` records are not shown in the physical room grid.

Enter a term to narrow the view, then click **Refresh View**.

### 4. Clear stored schedules

**Clear Database** removes all stored schedules after confirmation. Use this carefully because it affects every term in the local `schedule_db` database.

## Scheduling Rules

- The scheduling window is 7:00 AM–9:00 PM.
- Candidate start times are evaluated in 20-minute increments.
- Lecture sessions use classrooms `203` and `204`.
- Laboratory sessions use `ComLab1`, `ComLab5`, and `ComLab6`.
- Sections are split when enrollment exceeds 40 students.
- Room and section availability are checked for the full duration of each session.
- Room selection favors less-used rooms to distribute utilization.
- Program- and year-specific rules influence lecture/lab splitting and physical-room priority.
- If no valid physical room is available, the scheduler uses an online or other explicit fallback status rather than double-booking a room.
- Conflict checking is performed within each term. It reports room double-bookings and overlapping sessions for the same section.


## Database Schema

At startup, the application creates the following table if it does not already exist:

```sql
CREATE TABLE schedules (
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
);
```

## Project Structure

| File | Purpose |
|---|---|
| [`Bibat_Borbon_Castillo_Estabaya_Natividad_SourceCode.py`](./Bibat_Borbon_Castillo_Estabaya_Natividad_SourceCode.py) | Main application, scheduler, database integration, GUI, validation, and export |
| [`README_ALGORITHM_OVERVIEW.md`](./README_ALGORITHM_OVERVIEW.md) | Plain-language explanation of the scheduling algorithm |
| [`SCHEDULING_SYSTEM_DOCUMENTATION.md`](./SCHEDULING_SYSTEM_DOCUMENTATION.md) | Detailed technical documentation |
| [`ALGORITHM_PSEUDOCODE.md`](./ALGORITHM_PSEUDOCODE.md) | Language-independent scheduling pseudocode |
| [`SCHEDULING_FIXES.md`](./SCHEDULING_FIXES.md) | Room allocation and conflict-prevention fixes |
| [`UI_ENHANCEMENTS.md`](./UI_ENHANCEMENTS.md) | User interface and room visualization notes |
| [`find_slot_flow.mmd`](./find_slot_flow.mmd) | Mermaid diagram for slot selection |
| [`pipeline.mmd`](./pipeline.mmd) | Mermaid diagram for the scheduling pipeline |
| [`schedule.db`](./schedule.db) | Existing local database artifact, if used by a separate project version |

The directory also contains earlier experimental versions of the scheduler. The supported GUI entry point documented here is `Bibat_Borbon_Castillo_Estabaya_Natividad_SourceCode.py`.

## Troubleshooting

### `ModuleNotFoundError`

Install the required packages:

```powershell
py -m pip install mysql-connector-python networkx
```

### MySQL connection error

Confirm that:

- MySQL Server is running.
- The configured host, username, and password are correct.
- The MySQL user can create databases and tables.
- Port or firewall settings are not blocking the connection.

### CSV validation error

Check that the file includes `Program`, `Year`, and `Subject` values for every row, and that `Year` contains integers. Remove blank or malformed rows and try again.

### `ONLINE` assignments

`ONLINE` means that no available physical room and time slot could satisfy the current constraints. Add rooms, adjust the input data, or review the schedule for unusually long sessions.
