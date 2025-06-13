import csv
import pymongo
from pymongo import MongoClient

# Your MongoDB connection
MONGODB_URI = "mongodb+srv://admin:pcDRhXeTjrzG1tOF@ca-schools.mi7p1is.mongodb.net/?retryWrites=true&w=majority&appName=ca-schools"

def get_color_status(color_code):
    """Convert color code to status"""
    color_map = {
        '1': 'Red',
        '2': 'Orange', 
        '3': 'Yellow',
        '4': 'Green',
        '5': 'Blue',
        '0': 'No Data'
    }
    return color_map.get(str(color_code), 'Unknown')

def get_student_group_name(short_code):
    """Convert student group short codes to full names"""
    group_map = {
        'ALL': 'All Students',
        'AA': 'Black/African American',
        'AI': 'American Indian',
        'AS': 'Asian', 
        'FI': 'Filipino',
        'HI': 'Hispanic/Latino',
        'PI': 'Pacific Islander',
        'WH': 'White',
        'MR': 'Two or More Races',
        'EL': 'English Learners',
        'RFEP': 'Reclassified Fluent English Proficient',
        'SED': 'Socioeconomically Disadvantaged',
        'SWD': 'Students with Disabilities',
        'HOM': 'Homeless',
        'FOS': 'Foster Youth'
    }
    return group_map.get(short_code, short_code)

def create_school_documents_improved():
    print("📁 Loading CSV files with student group awareness...")
    
    # Load all CSV files
    chronic_data = load_csv_file('chronicdownload2024 - Sheet1.csv')
    ela_data = load_csv_file('eladownload2024 - Sheet1.csv')
    math_data = load_csv_file('mathdownload2024 - Sheet1.csv')
    
    # Group by school (cds) and organize by student groups
    schools = {}
    
    # Process chronic absenteeism data
    for row in chronic_data:
        cds = row.get('cds', '')
        if cds == '00000000000000':  # Skip state-level data
            continue
            
        student_group = row.get('stugroupshort', 'ALL')
        
        if cds not in schools:
            schools[cds] = {
                'cds_code': cds,
                'county_name': row.get('countyname', ''),
                'district_name': row.get('districtname', ''),
                'school_name': row.get('schoolname', ''),
                'year': '2024',
                'student_groups': {}
            }
        
        if student_group not in schools[cds]['student_groups']:
            schools[cds]['student_groups'][student_group] = {}
        
        schools[cds]['student_groups'][student_group]['chronic_absenteeism'] = {
            'status': get_color_status(row.get('color', '')),
            'rate': float(row.get('currstatus', 0) or 0),
            'change': float(row.get('change', 0) or 0),
            'color_code': row.get('color', ''),
            'student_group_name': get_student_group_name(student_group)
        }
    
    # Process ELA data
    for row in ela_data:
        cds = row.get('cds', '')
        if cds == '00000000000000' or cds not in schools:
            continue
            
        student_group = row.get('stugroupshort', 'ALL')
        
        if student_group not in schools[cds]['student_groups']:
            schools[cds]['student_groups'][student_group] = {}
            
        schools[cds]['student_groups'][student_group]['ela_performance'] = {
            'status': get_color_status(row.get('color', '')),
            'points_below_standard': float(row.get('currstatus', 0) or 0),
            'change': float(row.get('change', 0) or 0),
            'color_code': row.get('color', ''),
            'student_group_name': get_student_group_name(student_group)
        }
    
    # Process Math data  
    for row in math_data:
        cds = row.get('cds', '')
        if cds == '00000000000000' or cds not in schools:
            continue
            
        student_group = row.get('stugroupshort', 'ALL')
        
        if student_group not in schools[cds]['student_groups']:
            schools[cds]['student_groups'][student_group] = {}
            
        schools[cds]['student_groups'][student_group]['math_performance'] = {
            'status': get_color_status(row.get('color', '')),
            'points_below_standard': float(row.get('currstatus', 0) or 0),
            'change': float(row.get('change', 0) or 0),
            'color_code': row.get('color', ''),
            'student_group_name': get_student_group_name(student_group)
        }
    
    # Convert to documents
    documents = []
    for cds, school_data in schools.items():
        # Create overall indicators from "ALL" student group if available
        all_students = school_data['student_groups'].get('ALL', {})
        
        doc = {
            'cds_code': school_data['cds_code'],
            'county_name': school_data['county_name'],
            'district_name': school_data['district_name'],
            'school_name': school_data['school_name'],
            'year': school_data['year'],
            'dashboard_indicators': all_students,  # Overall school performance
            'student_groups': school_data['student_groups']  # All student group breakdowns
        }
        
        documents.append(doc)
    
    print(f"✅ Created {len(documents)} school documents with student group data")
    return documents

def load_csv_file(filename):
    """Load CSV file and return list of dictionaries"""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            data = list(reader)
            print(f"✅ Loaded {filename}: {len(data)} rows")
            return data
    except Exception as e:
        print(f"❌ Error loading {filename}: {e}")
        return []

def upload_to_mongodb(documents):
    print("📤 Uploading to MongoDB...")
    
    try:
        client = MongoClient(MONGODB_URI)
        db = client.ca_schools
        collection = db.schools
        
        # Clear existing data
        collection.delete_many({})
        
        # Insert new data
        result = collection.insert_many(documents)
        print(f"✅ Uploaded {len(result.inserted_ids)} documents to MongoDB!")
        
        # Test query with student groups
        test_doc = collection.find_one({"school_name": {"$ne": ""}})
        if test_doc:
            print(f"✅ Test document: {test_doc['school_name']} in {test_doc['district_name']}")
            print(f"   Student groups available: {list(test_doc.get('student_groups', {}).keys())}")
        
    except Exception as e:
        print(f"❌ MongoDB upload failed: {e}")

if __name__ == "__main__":
    documents = create_school_documents_improved()
    upload_to_mongodb(documents)
    print("🎉 Improved data import complete!")