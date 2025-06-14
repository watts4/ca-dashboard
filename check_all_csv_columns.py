# check_all_csv_columns.py
import csv

def check_columns(filename):
    """Check what columns we actually have in each CSV file"""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            first_row = next(reader)
            print(f"\n📁 {filename} columns:")
            for col in first_row.keys():
                print(f"  '{col}': '{first_row[col]}'")
            print(f"  Total columns: {len(first_row.keys())}")
            print(f"  Total rows: Checking...")
            
            # Count total rows
            file.seek(0)  # Reset to beginning
            row_count = sum(1 for row in csv.DictReader(file)) 
            print(f"  Total rows: {row_count}")
            
    except FileNotFoundError:
        print(f"❌ File not found: {filename}")
    except Exception as e:
        print(f"❌ Error reading {filename}: {e}")

# Check all CA Dashboard CSV files
csv_files = [
    'chronicdownload2024 - Sheet1.csv',      # Chronic Absenteeism
    'eladownload2024 - Sheet1.csv',          # ELA Performance  
    'mathdownload2024 - Sheet1.csv',         # Math Performance
    'suspdownload2024 - Sheet1.csv',         # Suspension Rate
    'ccidownload2024 - Sheet1.csv',          # College/Career Indicator
    'graddownload2024 - Sheet1.csv'          # Graduation Rate (might be ELPI)
]

print("🔍 Checking all CA Dashboard CSV files...")
for filename in csv_files:
    check_columns(filename)

print("\n✅ Column check complete!")