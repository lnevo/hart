#!/usr/bin/env python3
import openpyxl
from collections import defaultdict

wb = openpyxl.load_workbook('HART_Industry_Routing_Matrix.xlsx')
ws = wb.active

def determine_railroad_timeline(company, location, interchange, current_rr):
    """Determine the appropriate railroad timeline based on location, routing, and current RR."""
    location_upper = location.upper()
    company_upper = company.upper()
    interchange_upper = interchange.upper() if interchange else ''
    current_rr_upper = current_rr.upper() if current_rr else ''
    
    # Bridgeville = W&LE territory (W&LE Bridgeville branch)
    if 'Bridgeville' in interchange_upper:
        return 'W&LE'
    
    # Glenwood/Scully = Pittsburgh area interchanges (check these BEFORE NS Interchange)
    if 'Glenwood' in interchange_upper or 'Scully' in interchange_upper:
        # Pittsburgh area companies
        if 'Pittsburgh' in location_upper:
            # Check specific companies
            if 'Koppers' in company_upper or 'McConway' in company_upper:
                return 'PRR, Penn Central (1968), Conrail (1976), CSX/NS (1999)'
            else:
                return 'P&LE, CSX (1992), AVR (1995)'
        # Other PA locations
        elif 'PA' in location_upper:
            if 'Beaver' in location_upper or 'Beaver Falls' in location_upper:
                return 'P&LE, CSX (1992), AVR (1995)'
            elif 'Lebanon' in location_upper:
                return 'PRR, Penn Central (1968), Conrail (1976), CSX/NS (1999)'
            elif 'Glendon' in location_upper:
                return 'PRR, Penn Central (1968), Conrail (1976), CSX/NS (1999)'
            else:
                return 'PRR, Penn Central (1968), Conrail (1976), CSX/NS (1999)'
        # Massachusetts - P&W/Conrail/AVR
        elif 'MA' in location_upper or 'Massachusetts' in location_upper or 'Worcester' in location_upper:
            return 'P&W, Conrail (1976), AVR (1995)'
        # New Jersey
        elif 'NJ' in location_upper or 'New Jersey' in location_upper:
            return 'CNJ, Conrail (1976), NS (1999)'
        else:
            return 'PRR, Penn Central (1968), Conrail (1976), CSX/NS (1999)'
    
    # NS Interchange = NS territory (check AFTER Glenwood/Scully)
    if 'NS Interchange' in interchange_upper:
        # Check if it was originally a different road
        if 'NJ' in location_upper or 'New Jersey' in location_upper or 'Bayonne' in location_upper:
            return 'CNJ, Conrail (1976), NS (1999)'
        elif 'PA' in location_upper and 'Pittsburgh' not in location_upper:
            # Could be PRR/Conrail or other
            if 'Lebanon' in location_upper:
                return 'PRR, Penn Central (1968), Conrail (1976), CSX/NS (1999)'
            else:
                return 'PRR, Penn Central (1968), Conrail (1976), CSX/NS (1999)'
        else:
            return 'NS'
    
    # If current RR is already a timeline, keep it
    if ',' in current_rr and '(' in current_rr:
        return current_rr
    
    # Default based on location if current RR is simple
    if current_rr_upper == 'NS':
        # Check if it should have a timeline
        if 'NJ' in location_upper:
            return 'CNJ, Conrail (1976), NS (1999)'
        elif 'PA' in location_upper and 'Pittsburgh' not in location_upper:
            return 'PRR, Penn Central (1968), Conrail (1976), CSX/NS (1999)'
        else:
            return 'NS'
    elif current_rr_upper == 'W&LE':
        return 'W&LE'
    elif 'CSX' in current_rr_upper:
        # Determine original
        if 'Pittsburgh' in location_upper or 'Beaver' in location_upper:
            return 'P&LE, CSX (1992), AVR (1995)'
        else:
            return 'B&O, Chessie (1973), CSX (1980)'
    else:
        # Default
        if 'OH' in location_upper or 'Ohio' in location_upper:
            return 'W&LE'
        elif 'MD' in location_upper or 'Maryland' in location_upper:
            return 'B&O, Chessie (1973), CSX (1980)'
        else:
            return 'NS'

# Read and update all entries
updates = []
for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
    if row[0]:
        company = str(row[3]) if len(row) > 3 and row[3] else ''
        location = str(row[4]) if len(row) > 4 and row[4] else ''
        interchange = str(row[6]) if len(row) > 6 and row[6] else ''  # Column 7 = Interchange
        current_rr = str(row[5]) if len(row) > 5 and row[5] else ''  # Column 6 = Foreign Railroad
        
        new_rr = determine_railroad_timeline(company, location, interchange, current_rr)
        if new_rr != current_rr:
            updates.append({
                'row': row_num,
                'old': current_rr,
                'new': new_rr,
                'company': company,
                'location': location
            })

print(f"Found {len(updates)} entries to update with full timelines:")
for update in updates[:15]:
    print(f"  Row {update['row']:3}: {update['company'][:35]:35} | {update['location'][:20]:20}")
    print(f"         {update['old']:50} → {update['new']}")

if len(updates) > 15:
    print(f"\n  ... and {len(updates) - 15} more")

# Apply updates
for update in updates:
    ws.cell(row=update['row'], column=6).value = update['new']  # Column 6 = Foreign Railroad

wb.save('HART_Industry_Routing_Matrix.xlsx')
print(f"\n✓ Updated {len(updates)} entries and saved file")

# Final summary
summary = defaultdict(int)
for update in updates:
    summary[update['new']] += 1

print("\nSummary by railroad timeline:")
for rr, count in sorted(summary.items()):
    print(f"  {rr:60} - {count:3} entries")
