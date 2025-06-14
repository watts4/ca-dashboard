# check_elpi_structure.py
import csv

def check_elpi_columns():
    """Check the ELPI file structure"""
    filename = 'elpidownload2024 - Sheet1.csv'
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            first_row = next(reader)
            
            print(f"📁 {filename} columns:")
            for i, (col, value) in enumerate(first_row.items()):
                print(f"  {i+1:2d}. '{col}': '{value}'")
            
            print(f"\nTotal columns: {len(first_row.keys())}")
            
            # Count total rows
            file.seek(0)
            row_count = sum(1 for row in csv.DictReader(file))
            print(f"Total rows: {row_count}")
            
            # Check a few more sample rows
            file.seek(0)
            reader = csv.DictReader(file)
            print(f"\nSample data (first 3 rows):")
            for i, row in enumerate(reader):
                if i >= 3:
                    break
                print(f"Row {i+1}: CDS={row.get('cds', 'N/A')}, School={row.get('schoolname', 'N/A')}, Group={row.get('stugroupshort', 'N/A')}, Status={row.get('currstatus', 'N/A')}")
                
    except FileNotFoundError:
        print(f"❌ File not found: {filename}")
        print("Make sure the ELPI file is in the same directory")
    except Exception as e:
        print(f"❌ Error reading {filename}: {e}")

if __name__ == "__main__":
    check_elpi_columns()