# debug_columns.py
import csv

# Check what columns we actually have
def check_columns(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        first_row = next(reader)
        print(f"\n{filename} columns:")
        for col in first_row.keys():
            print(f"  '{col}': '{first_row[col]}'")

# Check all files
check_columns('chronicdownload2024 - Sheet1.csv')
check_columns('eladownload2024 - Sheet1.csv')
check_columns('mathdownload2024 - Sheet1.csv')