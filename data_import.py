import csv
import pymongo
from pymongo import MongoClient

# Your MongoDB connection
MONGODB_URI = "mongodb+srv://admin:pcDRhXeTjrzG1tOF@ca-schools.mi7p1is.mongodb.net/?retryWrites=true&w=majority&appName=ca-schools"

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

def get_color_status(color_code):
    """Convert color code to status"""
    color_map = {
        '1': 'Red',
        '2': 'Orange', 
        '3': 'Yellow',
        '4': 'Green',
        '5': 'Blue'
    }
    return color_map.get(str(color_code), 'Unknown')

def create_school_documents():
    print("📁 Loading CSV files...")
    
    # Load all CSV files
    chronic_data = load_csv_file('chronicdownload2024 - Sheet1.csv')
    ela_data = load_csv_file('eladownload2024 - Sheet1.csv')
    math_data = load_csv_file('mathdownload2024 - Sheet1.csv')
    
    # Create lookup dictionaries for faster merging (by CDS code)
    ela_lookup = {}
    for row in ela_data:
        cds = row.get('cds', '')
        if cds not in ela_lookup:
            ela_lookup[cds] = []
        ela_lookup[cds].append(row)
    
    math_lookup = {}
    for row in math_data:
        cds = row.get('cds', '')
        if cds not in math_lookup:
            math_lookup[cds] = []
        math_lookup[cds].append(row)
    
    documents = []
    processed_schools = set()
    
    for row in chronic_data:
        try:
            cds = row.get('cds', '')
            
            # Skip duplicates and state-level data
            if cds in processed_schools or cds == '00000000000000':
                continue
            processed_schools.add(cds)
            
            doc = {
                "cds_code": cds,
                "county_name": row.get('countyname', ''),
                "district_name": row.get('districtname', ''),
                "school_name": row.get('schoolname', ''),
                "year": "2024",
                "dashboard_indicators": {
                    "chronic_absenteeism": {
                        "status": get_color_status(row.get('color', '')),
                        "rate": float(row.get('currstatus', 0) or 0),
                        "change": float(row.get('change', 0) or 0),
                        "color_code": row.get('color', '')
                    }
                }
            }
            
            # Add ELA data if exists (use first match for now)
            if cds in ela_lookup and len(ela_lookup[cds]) > 0:
                ela_row = ela_lookup[cds][0]  # Take first match
                doc["dashboard_indicators"]["ela_performance"] = {
                    "status": get_color_status(ela_row.get('color', '')),
                    "points_below_standard": float(ela_row.get('currstatus', 0) or 0),
                    "change": float(ela_row.get('change', 0) or 0),
                    "color_code": ela_row.get('color', '')
                }
            
            # Add Math data if exists
            if cds in math_lookup and len(math_lookup[cds]) > 0:
                math_row = math_lookup[cds][0]  # Take first match
                doc["dashboard_indicators"]["math_performance"] = {
                    "status": get_color_status(math_row.get('color', '')),
                    "points_below_standard": float(math_row.get('currstatus', 0) or 0),
                    "change": float(math_row.get('change', 0) or 0),
                    "color_code": math_row.get('color', '')
                }
            
            documents.append(doc)
            
        except Exception as e:
            print(f"Error processing row: {e}")
            continue
    
    print(f"✅ Created {len(documents)} school documents")
    return documents

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
        
        # Test query
        test_doc = collection.find_one({"school_name": {"$ne": ""}})
        if test_doc:
            print(f"✅ Test document: {test_doc['school_name']} in {test_doc['district_name']}")
        
        # Test red/orange query
        red_orange = list(collection.find({
            "$or": [
                {"dashboard_indicators.chronic_absenteeism.status": {"$in": ["Red", "Orange"]}},
                {"dashboard_indicators.ela_performance.status": {"$in": ["Red", "Orange"]}},
                {"dashboard_indicators.math_performance.status": {"$in": ["Red", "Orange"]}}
            ]
        }).limit(5))
        
        print(f"✅ Found {len(red_orange)} schools with Red/Orange indicators")
        for school in red_orange[:2]:
            print(f"   - {school.get('school_name', 'Unknown')} ({school.get('district_name', 'Unknown')})")
        
    except Exception as e:
        print(f"❌ MongoDB upload failed: {e}")

if __name__ == "__main__":
    # Create and upload documents
    documents = create_school_documents()
    upload_to_mongodb(documents)
    print("🎉 Data import complete!")