import csv
import pymongo
import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Your MongoDB connection - SECURE VERSION
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set. Create a .env file with MONGODB_URI=your_connection_string")

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
        'LTEL': 'Long-Term English Learners',
        'RFEP': 'Reclassified Fluent English Proficient',
        'SED': 'Socioeconomically Disadvantaged',
        'SWD': 'Students with Disabilities',
        'HOM': 'Homeless',
        'FOS': 'Foster Youth'
    }
    return group_map.get(short_code, short_code)

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

def create_school_documents_complete():
    """Create school documents with ALL 6 CA Dashboard indicators"""
    print("📁 Loading ALL CA Dashboard CSV files...")
    
    # Load all 6 CSV files for complete CA Dashboard coverage
    csv_files = {
        'chronic_absenteeism': 'chronicdownload2024 - Sheet1.csv',
        'ela_performance': 'eladownload2024 - Sheet1.csv', 
        'math_performance': 'mathdownload2024 - Sheet1.csv',
        'suspension_rate': 'suspdownload2024 - Sheet1.csv',
        'college_career': 'ccidownload2024 - Sheet1.csv',
        'graduation_rate': 'graddownload2024 - Sheet1.csv',
        'english_learner_progress': 'elpidownload2024 - Sheet1.csv'  # English Learner Progress Indicator
    }
    
    # Load all data
    all_data = {}
    for indicator, filename in csv_files.items():
        all_data[indicator] = load_csv_file(filename)
        if not all_data[indicator]:
            print(f"⚠️  Warning: No data loaded for {indicator} from {filename}")
    
    # Group by school (cds) and organize by student groups
    schools = {}
    
    # Process each indicator type
    for indicator_name, data in all_data.items():
        print(f"📊 Processing {indicator_name} data...")
        
        for row in data:
            cds = row.get('cds', '')
            if cds == '00000000000000' or cds == '0':  # Skip state-level data
                continue
                
            # Handle different column names for student groups
            student_group = row.get('stugroupshort', 'ALL')
            if not student_group or student_group == 'ALL':
                # ELPI file uses 'studentgroup' instead of 'stugroupshort'
                if indicator_name == 'english_learner_progress':
                    # For ELPI, all data is for English Learners
                    student_group = 'EL'
                else:
                    student_group = 'ALL'
            
            # Initialize school if not exists
            if cds not in schools:
                schools[cds] = {
                    'cds_code': cds,
                    'county_name': row.get('countyname', ''),
                    'district_name': row.get('districtname', ''),
                    'school_name': row.get('schoolname', ''),
                    'year': '2024',
                    'student_groups': {}
                }
            
            # Initialize student group if not exists
            if student_group not in schools[cds]['student_groups']:
                schools[cds]['student_groups'][student_group] = {}
            
            # Add indicator data with proper field mapping
            indicator_data = {
                'status': get_color_status(row.get('color', '')),
                'color_code': row.get('color', ''),
                'student_group_name': get_student_group_name(student_group),
                'change': float(row.get('change', 0) or 0)
            }
            
            # Add indicator-specific value field based on actual data structure
            if indicator_name in ['chronic_absenteeism', 'suspension_rate', 'graduation_rate', 'english_learner_progress']:
                # These are percentage rates
                indicator_data['rate'] = float(row.get('currstatus', 0) or 0)
            elif indicator_name in ['ela_performance', 'math_performance']:
                # These are Distance from Standard (DFS) scores
                indicator_data['points_below_standard'] = float(row.get('currstatus', 0) or 0)
            elif indicator_name == 'college_career':
                # College/Career Indicator (CCI) - percentage prepared
                indicator_data['rate'] = float(row.get('currstatus', 0) or 0)
            else:
                # Default to rate for unknown indicators
                indicator_data['rate'] = float(row.get('currstatus', 0) or 0)
            
            schools[cds]['student_groups'][student_group][indicator_name] = indicator_data
    
    # Convert to documents with dashboard_indicators for overall school performance
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
    
    print(f"✅ Created {len(documents)} school documents with complete CA Dashboard data")
    return documents

def upload_to_mongodb(documents):
    """Upload documents to MongoDB"""
    print("📤 Uploading to MongoDB...")
    
    try:
        client = MongoClient(MONGODB_URI)
        db = client.ca_schools
        collection = db.schools
        
        # Clear existing data
        print("🗑️  Clearing existing data...")
        collection.delete_many({})
        
        # Insert new data
        result = collection.insert_many(documents)
        print(f"✅ Uploaded {len(result.inserted_ids)} documents to MongoDB!")
        
        # Test query with student groups
        test_doc = collection.find_one({"school_name": {"$ne": ""}})
        if test_doc:
            print(f"✅ Test document: {test_doc['school_name']} in {test_doc['district_name']}")
            print(f"   Student groups available: {list(test_doc.get('student_groups', {}).keys())}")
            
            # Show available indicators
            all_students_data = test_doc.get('student_groups', {}).get('ALL', {})
            if all_students_data:
                print(f"   Indicators available: {list(all_students_data.keys())}")
        
        # Get summary statistics
        total_schools = collection.count_documents({})
        districts_count = len(collection.distinct("district_name"))
        
        print(f"📊 Database Summary:")
        print(f"   Total Schools: {total_schools}")
        print(f"   Total Districts: {districts_count}")
        
        # Check each indicator availability
        indicator_counts = {}
        for indicator in ['chronic_absenteeism', 'ela_performance', 'math_performance', 
                         'suspension_rate', 'college_career', 'graduation_rate', 'english_learner_progress']:
            count = collection.count_documents({f"dashboard_indicators.{indicator}": {"$exists": True}})
            indicator_counts[indicator] = count
            print(f"   Schools with {indicator}: {count}")
        
    except Exception as e:
        print(f"❌ MongoDB upload failed: {e}")

if __name__ == "__main__":
    print("🚀 Starting COMPLETE CA Dashboard data import (ALL 6 indicators)...")
    documents = create_school_documents_complete()
    upload_to_mongodb(documents)
    print("🎉 Complete CA Dashboard data import finished!")
    print("✅ All indicators available: Chronic Absenteeism, ELA, Math, Suspensions, College/Career, Graduation Rate, English Learner Progress")