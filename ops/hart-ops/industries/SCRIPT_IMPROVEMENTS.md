# Script Improvements to Prevent Recurrence of Issues

## Overview
This document describes the improvements made to prevent recurrence of common issues in the HART Industry Routing Matrix.

## Issues Addressed

### 1. Industrial Mix-Ups (Food Companies with Steel Industries)
**Problem:** Food companies like Hershey were incorrectly listed as customers for steel products.

**Solution:**
- Added validation that checks for food company keywords (Hershey, Nabisco, Kraft, etc.) when paired with steel-related industries or commodities
- Script now flags these as errors before they're added to the matrix
- Validation keywords are easily configurable in the script

**Prevention:** The `validate_entry()` function checks for this pattern and rejects entries that match.

### 2. Duplicate Entries
**Problem:** Same supplier/customer combinations were being added multiple times.

**Solution:**
- Added duplicate detection that checks Industry + Flow + Commodity + Company combinations
- Script automatically identifies and can remove duplicates
- `add_entry_safely()` function checks for duplicates before adding new entries

**Prevention:** All new entries are checked against existing entries before being added.

### 3. Missing Car Types
**Problem:** Car type column was sometimes lost or not populated.

**Solution:**
- Car type validation ensures only valid car types are used
- Valid car types: Boxcar, Covered Hopper, Flatcar, Gondola, Hopper, Tank Car, Coil Car
- Script validates car types when entries are added

**Prevention:** Car type column (Column 8) is preserved during all operations.

### 4. Generic Supplier/Customer Names
**Problem:** Generic names like "local supplier" or "various mills" were being used.

**Solution:**
- Validation checks for generic keywords (local, various, multiple, distributor, etc.)
- Allows specific known companies (Ryerson Steel Service, Metal Service Co, etc.)
- Flags generic entries for review

**Prevention:** Generic names are caught during validation before being added.

### 5. Sorting Issues
**Problem:** File wasn't always sorted correctly after updates.

**Solution:**
- Automatic sorting after any modification
- Sort order: Industry (alphabetical), then Flow (IN before OUT)
- `sort_worksheet()` function ensures consistent ordering

**Prevention:** All update operations automatically re-sort the file.

## New Validation Script

### File: `validate_and_update_matrix.py`

**Features:**
- Comprehensive validation of all entries
- Duplicate detection and removal
- Automatic sorting
- Industrial mix-up detection
- Generic name detection
- Car type validation

**Usage:**
```bash
# Validate only (no changes)
python3 validate_and_update_matrix.py HART_Industry_Routing_Matrix.xlsx --validate-only

# Validate and fix issues
python3 validate_and_update_matrix.py HART_Industry_Routing_Matrix.xlsx
```

**Functions:**
- `validate_entry()` - Validates a single entry
- `check_duplicates()` - Finds duplicate entries
- `validate_worksheet()` - Comprehensive validation
- `check_sorting()` - Verifies sort order
- `sort_worksheet()` - Sorts the worksheet
- `add_entry_safely()` - Adds entry with validation

## Best Practices Going Forward

1. **Always use `add_entry_safely()`** when adding new entries programmatically
2. **Run validation script** before making manual edits to catch issues early
3. **Check for duplicates** if you're copying/pasting entries
4. **Verify car types** are appropriate for the commodity
5. **Use specific company names** - avoid generic terms
6. **Maintain sort order** - the script handles this automatically

## Configuration

All validation rules are defined at the top of `validate_and_update_matrix.py`:

- `FOOD_KEYWORDS` - Keywords that identify food companies
- `STEEL_KEYWORDS` - Keywords that identify steel-related industries/commodities
- `GENERIC_KEYWORDS` - Keywords that indicate generic names
- `ALLOWED_GENERIC` - Generic-sounding names that are actually specific companies
- `CAR_TYPES` - Valid car type values

These can be easily modified if needed.

## Current Status

After running the validation script:
- ✅ No industrial mix-ups found
- ✅ Duplicates identified and can be removed
- ✅ Sorting is correct
- ✅ Car types are present
- ✅ No generic names found

## Notes

- The script preserves all existing data
- Sorting is non-destructive (only reorders rows)
- Validation is informational unless you explicitly fix issues
- All operations maintain the Excel file structure
