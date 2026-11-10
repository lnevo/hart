#!/usr/bin/env python3
"""
Robust validation and update script for HART Industry Routing Matrix.
Prevents common issues like:
- Industrial mix-ups (food companies with steel industries)
- Duplicate entries
- Missing car types
- Generic supplier/customer names
- Sorting issues
"""

import openpyxl
from openpyxl.styles import Font, PatternFill
from collections import defaultdict
import sys

# Validation rules
FOOD_KEYWORDS = ['Hershey', 'Nabisco', 'Kraft', 'General Mills', 'Campbell', 
                 'Coca-Cola', 'Pepsi', 'Nestle', 'Del Monte', 'Libby', 
                 'Quaker', 'Chocolate', 'Candy', 'Bakery', 'Beverage', 'Food']

STEEL_KEYWORDS = ['Steel', 'Stainless', 'Iron', 'Metal', 'Alloy', 'Forged', 
                  'Bolt', 'Precision', 'Strip', 'Coil', 'Bar', 'Slab', 'Billet']

GENERIC_KEYWORDS = ['local', 'various', 'multiple', 'distributor', 'supplier', 
                    'customer', 'service center', 'mills', 'plants', 'warehouse', 
                    'whse', 'tbd', 'unknown', '??', '?', 'to be determined']

ALLOWED_GENERIC = ['Ryerson Steel Service', 'Metal Service Co', 'Univar', 
                   'Houghton Chemical', 'Strategic Materials']

CAR_TYPES = ['Boxcar', 'Covered Hopper', 'Flatcar', 'Gondola', 'Hopper', 
             'Tank Car', 'Coil Car']


def validate_entry(industry, flow, commodity, company, location, car_type=None):
    """Validate a single entry and return list of issues."""
    issues = []
    
    # Basic validation
    if not industry or not industry.strip():
        issues.append("Missing industry")
    if not flow or flow not in ['IN', 'OUT']:
        issues.append(f"Invalid flow: {flow}")
    if not commodity or not commodity.strip():
        issues.append("Missing commodity")
    if not company or not company.strip():
        issues.append("Missing company")
    
    # Check for generic names
    if company:
        company_lower = company.lower()
        is_generic = any(keyword in company_lower for keyword in GENERIC_KEYWORDS)
        is_allowed = any(allowed in company for allowed in ALLOWED_GENERIC)
        if is_generic and not is_allowed:
            issues.append(f"Generic company name: {company}")
    
    # Check for industrial mix-ups
    if company and industry:
        is_food = any(keyword in company for keyword in FOOD_KEYWORDS)
        is_steel_industry = any(keyword in industry for keyword in STEEL_KEYWORDS)
        is_steel_commodity = any(keyword in commodity for keyword in STEEL_KEYWORDS) if commodity else False
        
        if is_food and (is_steel_industry or is_steel_commodity):
            issues.append(f"Food company ({company}) with steel industry/commodity")
    
    # Check car type if provided
    if car_type and car_type not in CAR_TYPES:
        issues.append(f"Invalid car type: {car_type}")
    
    return issues


def check_duplicates(ws, start_row=2):
    """Check for duplicate entries in the worksheet."""
    seen = {}
    duplicates = []
    
    for row_num in range(start_row, ws.max_row + 1):
        industry = ws.cell(row=row_num, column=1).value
        flow = ws.cell(row=row_num, column=2).value
        commodity = ws.cell(row=row_num, column=3).value
        company = ws.cell(row=row_num, column=4).value
        
        if industry:
            key = (str(industry).strip(), str(flow).strip(), 
                   str(commodity).strip() if commodity else '', 
                   str(company).strip() if company else '')
            
            if key in seen:
                duplicates.append((row_num, key, seen[key]))
            else:
                seen[key] = row_num
    
    return duplicates


def validate_worksheet(ws):
    """Comprehensive validation of the entire worksheet."""
    issues = []
    duplicates = check_duplicates(ws)
    
    if duplicates:
        issues.append({
            'type': 'duplicates',
            'count': len(duplicates),
            'details': duplicates
        })
    
    validation_errors = []
    for row_num in range(2, ws.max_row + 1):
        industry = ws.cell(row=row_num, column=1).value
        flow = ws.cell(row=row_num, column=2).value
        commodity = ws.cell(row=row_num, column=3).value
        company = ws.cell(row=row_num, column=4).value
        location = ws.cell(row=row_num, column=5).value
        car_type = ws.cell(row=row_num, column=8).value if ws.max_column >= 8 else None
        
        if industry:
            entry_issues = validate_entry(industry, flow, commodity, company, location, car_type)
            if entry_issues:
                validation_errors.append({
                    'row': row_num,
                    'industry': industry,
                    'issues': entry_issues
                })
    
    if validation_errors:
        issues.append({
            'type': 'validation',
            'count': len(validation_errors),
            'details': validation_errors
        })
    
    # Check sorting
    sort_issues = check_sorting(ws)
    if sort_issues:
        issues.append({
            'type': 'sorting',
            'count': len(sort_issues),
            'details': sort_issues
        })
    
    return issues


def check_sorting(ws):
    """Check if the worksheet is properly sorted."""
    issues = []
    prev_industry = None
    prev_flow_order = None
    
    for row_num in range(2, ws.max_row + 1):
        industry = ws.cell(row=row_num, column=1).value
        flow = ws.cell(row=row_num, column=2).value
        
        if not industry:
            continue
        
        industry = str(industry).strip()
        flow_order = 0 if flow == 'IN' else 1
        
        if prev_industry is not None:
            if industry < prev_industry:
                issues.append(f"Row {row_num}: Industry out of order ({prev_industry} -> {industry})")
            elif industry == prev_industry and flow_order < prev_flow_order:
                issues.append(f"Row {row_num}: Flow out of order in {industry} (IN should come before OUT)")
        
        prev_industry = industry
        prev_flow_order = flow_order
    
    return issues


def sort_worksheet(ws):
    """Sort the worksheet by Industry, then Flow (IN before OUT)."""
    all_rows = []
    
    # Read all data rows
    for row_num in range(2, ws.max_row + 1):
        row_data = []
        for col in range(1, ws.max_column + 1):
            row_data.append(ws.cell(row=row_num, column=col).value)
        if row_data[0]:  # Has an industry
            all_rows.append(row_data)
    
    # Sort
    def sort_key(row):
        industry = str(row[0]) if row[0] else ''
        flow = str(row[1]) if len(row) > 1 and row[1] else ''
        flow_order = 0 if flow == 'IN' else 1
        return (industry, flow_order)
    
    all_rows.sort(key=sort_key)
    
    # Clear existing data
    for row in range(2, ws.max_row + 1):
        for col in range(1, ws.max_column + 1):
            ws.cell(row=row, column=col).value = None
    
    # Write sorted data
    for idx, row_data in enumerate(all_rows, start=2):
        for col_idx, value in enumerate(row_data, start=1):
            ws.cell(row=idx, column=col_idx).value = value
    
    return len(all_rows)


def add_entry_safely(ws, industry, flow, commodity, company, location, region=None, 
                     foreign_rr=None, interchange=None, car_type=None):
    """Safely add a new entry with validation."""
    # Validate before adding
    issues = validate_entry(industry, flow, commodity, company, location, car_type)
    if issues:
        return {'success': False, 'issues': issues}
    
    # Check for duplicates
    for row_num in range(2, ws.max_row + 1):
        existing_industry = ws.cell(row=row_num, column=1).value
        existing_flow = ws.cell(row=row_num, column=2).value
        existing_commodity = ws.cell(row=row_num, column=3).value
        existing_company = ws.cell(row=row_num, column=4).value
        
        if (str(existing_industry).strip() == str(industry).strip() and
            str(existing_flow).strip() == str(flow).strip() and
            str(existing_commodity).strip() == str(commodity).strip() and
            str(existing_company).strip() == str(company).strip()):
            return {'success': False, 'issues': ['Duplicate entry already exists']}
    
    # Find next empty row
    next_row = ws.max_row + 1
    for row_num in range(2, ws.max_row + 1):
        if not ws.cell(row=row_num, column=1).value:
            next_row = row_num
            break
    
    # Add entry
    ws.cell(row=next_row, column=1).value = industry
    ws.cell(row=next_row, column=2).value = flow
    ws.cell(row=next_row, column=3).value = commodity
    ws.cell(row=next_row, column=4).value = company
    ws.cell(row=next_row, column=5).value = location
    if region:
        ws.cell(row=next_row, column=5).value = region  # Assuming region is column 5
    if foreign_rr:
        ws.cell(row=next_row, column=6).value = foreign_rr
    if interchange:
        ws.cell(row=next_row, column=7).value = interchange
    if car_type:
        ws.cell(row=next_row, column=8).value = car_type
    
    # Re-sort
    sort_worksheet(ws)
    
    return {'success': True, 'row': next_row}


def main():
    """Main function for command-line usage."""
    if len(sys.argv) < 2:
        print("Usage: python validate_and_update_matrix.py <excel_file> [--validate-only]")
        sys.exit(1)
    
    excel_file = sys.argv[1]
    validate_only = '--validate-only' in sys.argv
    
    try:
        wb = openpyxl.load_workbook(excel_file)
        ws = wb.active
        
        print("=" * 80)
        print("VALIDATING ROUTING MATRIX")
        print("=" * 80)
        
        issues = validate_worksheet(ws)
        
        if issues:
            print("\n⚠️  ISSUES FOUND:")
            for issue_group in issues:
                print(f"\n{issue_group['type'].upper()}: {issue_group['count']} issue(s)")
                for detail in issue_group['details'][:10]:  # Show first 10
                    if issue_group['type'] == 'duplicates':
                        print(f"  Row {detail[0]} duplicates Row {detail[2]}: {detail[1]}")
                    elif issue_group['type'] == 'validation':
                        print(f"  Row {detail['row']}: {detail['industry']}")
                        for issue in detail['issues']:
                            print(f"    - {issue}")
                    elif issue_group['type'] == 'sorting':
                        print(f"  {detail}")
        else:
            print("\n✓ No issues found!")
        
        if not validate_only:
            # Fix sorting if needed
            if any(issue['type'] == 'sorting' for issue in issues):
                print("\nFixing sort order...")
                rows_sorted = sort_worksheet(ws)
                print(f"✓ Sorted {rows_sorted} rows")
            
            wb.save(excel_file)
            print(f"\n✓ File saved: {excel_file}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
