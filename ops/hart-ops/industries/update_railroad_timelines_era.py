#!/usr/bin/env python3
"""
Update Foreign Railroad column to only show railroads from early 1980s - early 2000s era.
Remove pre-1980 railroads and correct P&LE and PC&Y merger dates.
"""
import openpyxl
from collections import defaultdict

wb = openpyxl.load_workbook('HART_Industry_Routing_Matrix.xlsx')
ws = wb.active

def update_railroad_timeline(current_rr, company, location, interchange):
    """Update railroad timeline to only include 1980s-2000s era, remove pre-1980."""
    location_upper = location.upper()
    company_upper = company.upper()
    interchange_upper = interchange.upper() if interchange else ''
    current_rr_upper = current_rr.upper() if current_rr else ''
    
    # If already correct format and doesn't have pre-1980, check if needs updating
    if ',' in current_rr and '(' in current_rr:
        # Check if it has pre-1980 dates that need removal
        if '1968' in current_rr or '1973' in current_rr:
            # Remove pre-1980 railroads
            if 'PRR, Penn Central (1968), Conrail (1976)' in current_rr:
                return 'Conrail (1976), CSX/NS (1999)'
            elif 'CNJ, Conrail (1976)' in current_rr:
                return 'Conrail (1976), NS (1999)'
            elif 'P&W, Conrail (1976)' in current_rr:
                return 'Conrail (1976), AVR (1995)'
            elif 'B&O, Chessie (1973), CSX (1980)' in current_rr:
                return 'CSX (1980)'
    
    # Bridgeville = W&LE territory
    if 'Bridgeville' in interchange_upper:
        return 'W&LE'
    
    # Glenwood/Scully = Pittsburgh area interchanges
    if 'Glenwood' in interchange_upper or 'Scully' in interchange_upper:
        if 'Pittsburgh' in location_upper:
            if 'Koppers' in company_upper or 'McConway' in company_upper:
                return 'Conrail (1976), CSX/NS (1999)'
            else:
                # P&LE stayed independent longer - user says longer than 1992
                # P&LE was likely independent through most of 1990s, then CSX, then AVR
                # Using P&LE (1980s-1997), CSX (1997), AVR (1999) as estimate - user can correct
                return 'P&LE, CSX (1997), AVR (1999)'
        elif 'PA' in location_upper:
            if 'Beaver' in location_upper or 'Beaver Falls' in location_upper:
                return 'P&LE, CSX (1997), AVR (1999)'
            elif 'Lebanon' in location_upper or 'Glendon' in location_upper:
                return 'Conrail (1976), CSX/NS (1999)'
            else:
                return 'Conrail (1976), CSX/NS (1999)'
        elif 'MA' in location_upper or 'Massachusetts' in location_upper or 'Worcester' in location_upper:
            return 'Conrail (1976), AVR (1995)'
        elif 'NJ' in location_upper or 'New Jersey' in location_upper:
            return 'Conrail (1976), NS (1999)'
        else:
            return 'Conrail (1976), CSX/NS (1999)'
    
    # NS Interchange
    if 'NS Interchange' in interchange_upper:
        if 'NJ' in location_upper or 'New Jersey' in location_upper or 'Bayonne' in location_upper:
            return 'Conrail (1976), NS (1999)'
        elif 'PA' in location_upper and 'Pittsburgh' not in location_upper:
            return 'Conrail (1976), CSX/NS (1999)'
        else:
            return 'NS'
    
    # If current RR is simple, determine based on location
    if current_rr_upper == 'NS':
        if 'NJ' in location_upper:
            return 'Conrail (1976), NS (1999)'
        elif 'PA' in location_upper and 'Pittsburgh' not in location_upper:
            return 'Conrail (1976), CSX/NS (1999)'
        else:
            return 'NS'
    elif current_rr_upper == 'W&LE':
        return 'W&LE'
    elif 'CSX' in current_rr_upper:
        if 'Pittsburgh' in location_upper or 'Beaver' in location_upper:
            return 'P&LE, CSX (1997), AVR (1999)'
        else:
            return 'CSX (1980)'
    else:
        # Default
        if 'OH' in location_upper or 'Ohio' in location_upper:
            return 'W&LE'
        elif 'MD' in location_upper or 'Maryland' in location_upper:
            return 'CSX (1980)'
        else:
            return 'NS'

# Read and update all entries
updates = []
for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
    if row[0]:
        company = str(row[3]) if len(row) > 3 and row[3] else ''
        location = str(row[4]) if len(row) > 4 and row[4] else ''
        interchange = str(row[6]) if len(row) > 6 and row[6] else ''
        current_rr = str(row[5]) if len(row) > 5 and row[5] else ''
        
        new_rr = update_railroad_timeline(current_rr, company, location, interchange)
        if new_rr != current_rr:
            updates.append({
                'row': row_num,
                'old': current_rr,
                'new': new_rr,
                'company': company,
                'location': location
            })

print(f"Found {len(updates)} entries to update:")
for update in updates[:20]:
    print(f"  Row {update['row']:3}: {update['company'][:35]:35} | {update['location'][:20]:20}")
    print(f"         OLD: {update['old']}")
    print(f"         NEW: {update['new']}")

if len(updates) > 20:
    print(f"\n  ... and {len(updates) - 20} more")

# Apply updates
for update in updates:
    ws.cell(row=update['row'], column=6).value = update['new']

wb.save('HART_Industry_Routing_Matrix.xlsx')
print(f"\n✓ Updated {len(updates)} entries and saved file")

# Final summary
summary = defaultdict(int)
for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
    if row[0] and len(row) > 5 and row[5]:
        foreign_rr = str(row[5])
        summary[foreign_rr] += 1

print("\nFinal summary by railroad timeline:")
for rr, count in sorted(summary.items()):
    print(f"  {rr:60} - {count:3} entries")
