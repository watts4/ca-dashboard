from flask import Flask, request, jsonify, render_template_string
import pymongo
from pymongo import MongoClient
import vertexai
try:
    from vertexai.generative_models import GenerativeModel
except ImportError:
    try:
        from vertexai.preview.generative_models import GenerativeModel
    except ImportError:
        from google.cloud import aiplatform
        from google.cloud.aiplatform import gapic
        GenerativeModel = None
        print("❌ Could not import GenerativeModel - check google-cloud-aiplatform version")

import json
import re
import os
from dotenv import load_dotenv
from typing import Dict, List, Any

app = Flask(__name__)
# Load environment variables
load_dotenv()
# MongoDB connection - SECURE VERSION
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")

client = MongoClient(MONGODB_URI)
db = client.ca_schools
schools_collection = db.schools

# Google Cloud AI setup - SECURE VERSION
PROJECT_ID = os.getenv("PROJECT_ID", "ca-schools-ai-dashboard")
try:
    vertexai.init(project=PROJECT_ID, location="us-central1")
    model = GenerativeModel("gemini-2.0-flash")
    AI_ENABLED = True
    print("✅ Vertex AI initialized successfully!")
except Exception as e:
    print(f"❌ Vertex AI initialization failed: {e}")
    AI_ENABLED = False
def analyze_query_with_gemini(user_query: str) -> Dict[str, Any]:
    """Use Gemini to intelligently understand the user's question"""
    
    system_prompt = """
You are an expert in California School Dashboard data analysis. Parse the user's natural language query and extract structured information.

AVAILABLE DATA INDICATORS (only these 3 exist in the database):
1. chronic_absenteeism - Percentage of students absent 10%+ of school days
2. ela_performance - ELA test scores (Distance from Standard - negative = below, positive = above)  
3. math_performance - Math test scores (Distance from Standard - negative = below, positive = above)

AVAILABLE STUDENT GROUPS:
- ALL (All Students)
- AA (Black/African American)  
- AI (American Indian)
- AS (Asian)
- EL (English Learners)
- FI (Filipino)
- FOS (Foster Youth)
- HI (Hispanic/Latino)
- HOM (Homeless)
- LTEL (Long-Term English Learners)
- MR (Two or More Races)
- PI (Pacific Islander)
- SED (Socioeconomically Disadvantaged)
- SWD (Students with Disabilities)
- WH (White)

PERFORMANCE LEVELS (Colors):
- Red = Lowest performance (most concerning)
- Orange = Below average performance  
- Yellow = Average performance
- Green = Above average performance
- Blue = Highest performance (best)

IMPORTANT: If the user asks about suspension rates, college/career readiness, or any other indicators NOT in the list above, respond that this data is not available.

Parse this query and return ONLY a JSON object with this exact structure:
{
    "district_name": "exact search term for district (e.g., 'sunnyvale' for flexible matching)",
    "school_name": "exact school name if mentioned, or null",
    "colors": ["Red", "Orange"] (performance levels user is interested in),
    "indicators": ["chronic_absenteeism"] (only from available list above),
    "student_groups": ["HI", "EL"] (codes from available list above),
    "data_availability": "available" or "not_available",
    "explanation": "brief explanation of what data is available vs requested"
}

Query: """ + user_query

    try:
        response = model.generate_content(system_prompt)
        response_text = response.text.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            parsed_json = json.loads(json_match.group())
            return parsed_json
        else:
            print(f"No JSON found in AI response: {response_text}")
            return None
            
    except Exception as e:
        print(f"Gemini API error: {e}")
        return None

def parse_query_with_real_ai(user_query: str) -> Dict[str, Any]:
    """Use Vertex AI to intelligently parse user queries about CA Dashboard data"""
    
    # First, try AI-powered analysis if available
    if AI_ENABLED:
        try:
            ai_parsed = analyze_query_with_gemini(user_query)
            if ai_parsed:
                print(f"DEBUG - AI parsed query: {ai_parsed}")
                return ai_parsed
        except Exception as e:
            print(f"AI parsing failed, falling back to pattern matching: {e}")
    
    # Fallback to pattern matching
    return parse_query_with_patterns(user_query)

    """Enhanced string-based query parsing with ALL SIX CA Dashboard indicators"""
    query_lower = user_query.lower()
    
    parsed = {
        "district_name": None,
        "school_name": None, 
        "colors": [],
        "indicators": [],
        "student_groups": []
    }
    
    # IMPROVED: More flexible district matching
    district_patterns = [
        ("sunnyvale", ["Sunnyvale", "Sunnyvale Elementary", "Sunnyvale School District"]),
        ("san francisco", ["San Francisco Unified"]),
        ("los angeles", ["Los Angeles Unified"]),
        ("oakland", ["Oakland Unified"]),
        ("san diego", ["San Diego Unified"]),
        ("alameda", ["Alameda Unified", "Alameda County Office of Education"]),
        ("fresno", ["Fresno Unified"]),
        ("sacramento", ["Sacramento City Unified"]),
        ("long beach", ["Long Beach Unified"]),
        ("san bernardino", ["San Bernardino City Unified"]),
        ("san juan", ["San Juan Unified"]),
        ("elk grove", ["Elk Grove Unified"])
    ]
    
    # Try flexible district matching
    for pattern, possible_names in district_patterns:
        if pattern in query_lower:
            # We'll use regex to find the actual district name in the database
            parsed["district_name"] = pattern  # Store search term, not exact name
            break
    
    # Extract school name (same as before)
    school_patterns = [
        ("san miguel elementary", "San Miguel Elementary"),
        ("bishop elementary", "Bishop Elementary"),
        ("sunnyvale middle", "Sunnyvale Middle"),
        ("columbia middle", "Columbia Middle"),
        ("vargas elementary", "Vargas Elementary"),
        ("cherry chase elementary", "Cherry Chase Elementary"),
        ("fairwood elementary", "Fairwood Elementary"),
        ("lakewood elementary", "Lakewood Elementary"),
        ("ellis elementary", "Ellis Elementary"),
        ("cumberland elementary", "Cumberland Elementary"),
        ("jefferson high", "Jefferson High"),
        ("roosevelt high", "Roosevelt High"),
        ("lincoln high", "Lincoln High")
    ]
    
    for pattern, school in school_patterns:
        if pattern in query_lower:
            parsed["school_name"] = school
            break
    
    # Extract student groups (same as before)
    student_group_patterns = [
        ("hispanic", "HI"), ("latino", "HI"), ("black", "AA"), ("african american", "AA"),
        ("asian", "AS"), ("white", "WH"), ("filipino", "FI"), ("pacific islander", "PI"),
        ("american indian", "AI"), ("two or more races", "MR"), ("english learners", "EL"),
        ("english learner", "EL"), ("long-term english learners", "LTEL"), ("long term english learners", "LTEL"),
        ("socioeconomically disadvantaged", "SED"), ("low income", "SED"), ("economically disadvantaged", "SED"),
        ("students with disabilities", "SWD"), ("special education", "SWD"), ("special needs", "SWD"),
        ("homeless", "HOM"), ("foster", "FOS"), ("foster youth", "FOS"), ("all students", "ALL")
    ]
    
    for pattern, code in student_group_patterns:
        if pattern in query_lower:
            parsed["student_groups"].append(code)
    
    # Extract colors
    color_words = ["red", "orange", "yellow", "green", "blue"]
    for color in color_words:
        if color in query_lower:
            parsed["colors"].append(color.title())
    
    # FIXED: Extract indicators with COMPREHENSIVE matching including suspensions
    if any(word in query_lower for word in ["chronic", "absenteeism", "attendance", "absent", "truancy"]):
        parsed["indicators"].append("chronic_absenteeism")
    
    if any(word in query_lower for word in ["ela", "english language arts", "reading", "language arts", "literacy"]):
        parsed["indicators"].append("ela_performance") 
    
    if any(word in query_lower for word in ["math", "mathematics", "arithmetic", "algebra", "geometry"]):
        parsed["indicators"].append("math_performance")
    
    if any(word in query_lower for word in ["english learner progress", "elpi", "elpac", "language proficiency"]):
        parsed["indicators"].append("english_learner_progress")
    
    # ADDED: Suspension rate detection
    if any(word in query_lower for word in ["suspension", "suspensions", "suspended", "discipline", "disciplinary", "behavior"]):
        parsed["indicators"].append("suspension_rate")
    
    # ADDED: College/Career detection
    college_career_terms = [
        "college", "career", "cci", "college career", "a-g", "ag", "uc", "csu", 
        "ap", "advanced placement", "ib", "international baccalaureate", 
        "cte", "career technical education", "dual enrollment", "college credit",
        "prepared", "graduation", "graduates", "post-secondary", "workforce",
        "apprenticeship", "biliteracy", "seal of biliteracy"
    ]
    
    if any(term in query_lower for term in college_career_terms):
        parsed["indicators"].append("college_career")
    
    # Better context understanding
    problem_phrases = [
        "lowest", "worst", "poorest", "struggling", "needs improvement", 
        "problem areas", "areas of concern", "failing", "underperforming",
        "below standard", "not meeting", "deficient", "high rates", "concerning",
        "not prepared", "unprepared"
    ]
    
    if any(phrase in query_lower for phrase in problem_phrases):
        if not parsed["colors"]:
            parsed["colors"] = ["Red", "Orange"]
    
    success_phrases = [
        "best", "highest", "top", "excellent", "performing well", 
        "exceeding", "outstanding", "successful", "above standard", "low rates",
        "prepared", "college ready", "career ready"
    ]
    
    if any(phrase in query_lower for phrase in success_phrases):
        if not parsed["colors"]:
            parsed["colors"] = ["Green", "Blue"]
    
    print(f"DEBUG - Parsed query: {parsed}")
    return parsed


    """Convert parsed query into MongoDB filter with flexible district matching"""
    query_filter = {}
    
    # IMPROVED: Flexible district filter using regex
    if parsed_query.get("district_name"):
        # Use case-insensitive regex that matches district names containing the search term
        query_filter["district_name"] = {
            "$regex": parsed_query["district_name"], 
            "$options": "i"
        }
    
    # School filter (same as before)
    if parsed_query.get("school_name"):
        query_filter["school_name"] = {"$regex": parsed_query["school_name"], "$options": "i"}
    
    # Student group and color filters with ALL SIX indicators
    if parsed_query.get("colors"):
        color_conditions = []
        
        # If specific student groups mentioned
        if parsed_query.get("student_groups"):
            for student_group in parsed_query["student_groups"]:
                if parsed_query.get("indicators"):
                    # Specific indicators for specific groups
                    for indicator in parsed_query["indicators"]:
                        color_conditions.append({
                            f"student_groups.{student_group}.{indicator}.status": {"$in": parsed_query["colors"]}
                        })
                else:
                    # All indicators for specific groups (NOW INCLUDING SUSPENSION & COLLEGE/CAREER)
                    for indicator in ["chronic_absenteeism", "ela_performance", "math_performance", "english_learner_progress", "suspension_rate", "college_career"]:
                        color_conditions.append({
                            f"student_groups.{student_group}.{indicator}.status": {"$in": parsed_query["colors"]}
                        })
        else:
            # Default to overall indicators (ALL student group)
            if parsed_query.get("indicators"):
                for indicator in parsed_query["indicators"]:
                    color_conditions.append({
                        f"dashboard_indicators.{indicator}.status": {"$in": parsed_query["colors"]}
                    })
            else:
                # ALL SIX indicators
                for indicator in ["chronic_absenteeism", "ela_performance", "math_performance", "english_learner_progress", "suspension_rate", "college_career"]:
                    color_conditions.append({
                        f"dashboard_indicators.{indicator}.status": {"$in": parsed_query["colors"]}
                    })
        
        if color_conditions:
            query_filter["$or"] = color_conditions
    
    # Specific indicator filters without colors
    elif parsed_query.get("indicators"):
        indicator_conditions = []
        
        if parsed_query.get("student_groups"):
            for student_group in parsed_query["student_groups"]:
                for indicator in parsed_query["indicators"]:
                    indicator_conditions.append({
                        f"student_groups.{student_group}.{indicator}": {"$exists": True}
                    })
        else:
            for indicator in parsed_query["indicators"]:
                indicator_conditions.append({
                    f"dashboard_indicators.{indicator}": {"$exists": True}
                })
        
        if indicator_conditions:
            query_filter["$or"] = indicator_conditions
    
    return query_filter
    """Enhanced string-based query parsing with ALL SIX CA Dashboard indicators"""
    query_lower = user_query.lower()
    
    parsed = {
        "district_name": None,
        "school_name": None, 
        "colors": [],
        "indicators": [],
        "student_groups": []
    }
    
    # Extract district name (same as before)
    district_patterns = [
        ("sunnyvale", "Sunnyvale"),
        ("san francisco", "San Francisco Unified"),
        ("los angeles", "Los Angeles Unified"),
        ("oakland", "Oakland Unified"),
        ("san diego", "San Diego Unified"),
        ("alameda unified", "Alameda Unified"),
        ("alameda county", "Alameda County Office of Education"),
        ("fresno", "Fresno Unified"),
        ("sacramento", "Sacramento City Unified"),
        ("long beach", "Long Beach Unified"),
        ("san bernardino", "San Bernardino City Unified"),
        ("san juan", "San Juan Unified"),
        ("elk grove", "Elk Grove Unified")
    ]
    
    for pattern, district in district_patterns:
        if pattern in query_lower:
            parsed["district_name"] = district
            break
    
    # Extract school name (same as before)
    school_patterns = [
        ("san miguel elementary", "San Miguel Elementary"),
        ("bishop elementary", "Bishop Elementary"),
        ("sunnyvale middle", "Sunnyvale Middle"),
        ("columbia middle", "Columbia Middle"),
        ("vargas elementary", "Vargas Elementary"),
        ("cherry chase elementary", "Cherry Chase Elementary"),
        ("fairwood elementary", "Fairwood Elementary"),
        ("lakewood elementary", "Lakewood Elementary"),
        ("ellis elementary", "Ellis Elementary"),
        ("cumberland elementary", "Cumberland Elementary"),
        ("jefferson high", "Jefferson High"),
        ("roosevelt high", "Roosevelt High"),
        ("lincoln high", "Lincoln High")
    ]
    
    for pattern, school in school_patterns:
        if pattern in query_lower:
            parsed["school_name"] = school
            break
    
    # Extract student groups (same as before)
    student_group_patterns = [
        ("hispanic", "HI"), ("latino", "HI"), ("black", "AA"), ("african american", "AA"),
        ("asian", "AS"), ("white", "WH"), ("filipino", "FI"), ("pacific islander", "PI"),
        ("american indian", "AI"), ("two or more races", "MR"), ("english learners", "EL"),
        ("english learner", "EL"), ("long-term english learners", "LTEL"), ("long term english learners", "LTEL"),
        ("socioeconomically disadvantaged", "SED"), ("low income", "SED"), ("economically disadvantaged", "SED"),
        ("students with disabilities", "SWD"), ("special education", "SWD"), ("special needs", "SWD"),
        ("homeless", "HOM"), ("foster", "FOS"), ("foster youth", "FOS"), ("all students", "ALL")
    ]
    
    for pattern, code in student_group_patterns:
        if pattern in query_lower:
            parsed["student_groups"].append(code)
    
    # Extract colors
    color_words = ["red", "orange", "yellow", "green", "blue"]
    for color in color_words:
        if color in query_lower:
            parsed["colors"].append(color.title())
    
    # Extract indicators with COMPREHENSIVE matching including college/career
    if any(word in query_lower for word in ["chronic", "absenteeism", "attendance", "absent", "truancy"]):
        parsed["indicators"].append("chronic_absenteeism")
    
    if any(word in query_lower for word in ["ela", "english language arts", "reading", "language arts", "literacy"]):
        parsed["indicators"].append("ela_performance") 
    
    if any(word in query_lower for word in ["math", "mathematics", "arithmetic", "algebra", "geometry"]):
        parsed["indicators"].append("math_performance")
    
    if any(word in query_lower for word in ["english learner progress", "elpi", "elpac", "language proficiency"]):
        parsed["indicators"].append("english_learner_progress")
    
    if any(word in query_lower for word in ["suspension", "suspensions", "suspended", "discipline", "disciplinary", "behavior"]):
        parsed["indicators"].append("suspension_rate")
    
    # NEW: College/Career detection
    college_career_terms = [
        "college", "career", "cci", "college career", "a-g", "ag", "uc", "csu", 
        "ap", "advanced placement", "ib", "international baccalaureate", 
        "cte", "career technical education", "dual enrollment", "college credit",
        "prepared", "graduation", "graduates", "post-secondary", "workforce",
        "apprenticeship", "biliteracy", "seal of biliteracy"
    ]
    
    if any(term in query_lower for term in college_career_terms):
        parsed["indicators"].append("college_career")
    
    # Better context understanding
    problem_phrases = [
        "lowest", "worst", "poorest", "struggling", "needs improvement", 
        "problem areas", "areas of concern", "failing", "underperforming",
        "below standard", "not meeting", "deficient", "high rates", "concerning",
        "not prepared", "unprepared"
    ]
    
    if any(phrase in query_lower for phrase in problem_phrases):
        if not parsed["colors"]:
            parsed["colors"] = ["Red", "Orange"]
    
    success_phrases = [
        "best", "highest", "top", "excellent", "performing well", 
        "exceeding", "outstanding", "successful", "above standard", "low rates",
        "prepared", "college ready", "career ready"
    ]
    
    if any(phrase in query_lower for phrase in success_phrases):
        if not parsed["colors"]:
            parsed["colors"] = ["Green", "Blue"]
    
    print(f"DEBUG - Parsed query: {parsed}")
    return parsed
def parse_query_with_patterns(user_query: str) -> Dict[str, Any]:
    """Fallback pattern-based parsing (improved version of your existing logic)"""
    query_lower = user_query.lower()
    
    parsed = {
        "district_name": None,
        "school_name": None, 
        "colors": [],
        "indicators": [],
        "student_groups": [],
        "data_availability": "available",
        "explanation": "Using pattern matching for query analysis"
    }
    
    # District matching - more flexible
    district_keywords = {
        "sunnyvale": "sunnyvale",
        "san francisco": "san francisco",
        "los angeles": "los angeles", 
        "oakland": "oakland",
        "san diego": "san diego",
        "alameda": "alameda",
        "fresno": "fresno",
        "sacramento": "sacramento"
    }
    
    for keyword, search_term in district_keywords.items():
        if keyword in query_lower:
            parsed["district_name"] = search_term
            break
    
    # Student group extraction
    student_group_patterns = {
        "hispanic": "HI", "latino": "HI", "black": "AA", "african american": "AA",
        "asian": "AS", "white": "WH", "filipino": "FI", "pacific islander": "PI",
        "american indian": "AI", "two or more races": "MR", "english learners": "EL",
        "english learner": "EL", "long-term english learners": "LTEL", 
        "socioeconomically disadvantaged": "SED", "low income": "SED",
        "students with disabilities": "SWD", "special education": "SWD",
        "homeless": "HOM", "foster": "FOS", "all students": "ALL"
    }
    
    for pattern, code in student_group_patterns.items():
        if pattern in query_lower:
            parsed["student_groups"].append(code)
    
    # Color extraction
    color_words = ["red", "orange", "yellow", "green", "blue"]
    for color in color_words:
        if color in query_lower:
            parsed["colors"].append(color.title())
    
    # ONLY extract indicators that exist in the database
    if any(word in query_lower for word in ["chronic", "absenteeism", "attendance", "absent"]):
        parsed["indicators"].append("chronic_absenteeism")
    
    if any(word in query_lower for word in ["ela", "english language arts", "reading", "literacy"]):
        parsed["indicators"].append("ela_performance") 
    
    if any(word in query_lower for word in ["math", "mathematics", "arithmetic"]):
        parsed["indicators"].append("math_performance")
    
    # Check for unavailable data
    unavailable_terms = [
        "suspension", "discipline", "college", "career", "graduation", 
        "english learner progress", "elpi", "elpac"
    ]
    
    if any(term in query_lower for term in unavailable_terms):
        parsed["data_availability"] = "not_available"
        parsed["explanation"] = "Requested data (suspensions, college/career, EL progress) is not available in the current dataset. Available indicators: chronic absenteeism, ELA performance, math performance."
    
    # Context-based color inference
    problem_phrases = ["lowest", "worst", "struggling", "red", "problem", "concerning"]
    if any(phrase in query_lower for phrase in problem_phrases):
        if not parsed["colors"]:
            parsed["colors"] = ["Red", "Orange"]
    
    return parsed

# ADD these debug routes to your app.py to test the AI system


    """Test if Vertex AI is working"""
    if not AI_ENABLED:
        return jsonify({"error": "AI is not enabled", "ai_enabled": AI_ENABLED})
    
    try:
        # Simple test prompt
        test_prompt = "Respond with exactly: 'AI is working correctly'"
        response = model.generate_content(test_prompt)
        return jsonify({
            "ai_enabled": AI_ENABLED,
            "test_response": response.text.strip(),
            "status": "AI is working" if response else "AI failed"
        })
    except Exception as e:
        return jsonify({
            "ai_enabled": AI_ENABLED,
            "error": str(e),
            "status": "AI failed"
        })


    """Debug the query parsing process step by step"""
    try:
        user_query = request.json['query']
        
        # Test AI parsing first
        ai_result = None
        ai_error = None
        
        if AI_ENABLED:
            try:
                ai_result = analyze_query_with_gemini(user_query)
            except Exception as e:
                ai_error = str(e)
        
        # Test pattern parsing
        pattern_result = parse_query_with_patterns(user_query)
        
        # Test MongoDB query building
        mongo_query = build_mongodb_query(pattern_result)
        
        # Test MongoDB results
        results = list(schools_collection.find(mongo_query, {"_id": 0}).limit(5))
        
        return jsonify({
            "user_query": user_query,
            "ai_enabled": AI_ENABLED,
            "ai_parsing": {
                "result": ai_result,
                "error": ai_error,
                "used": ai_result is not None
            },
            "pattern_parsing": pattern_result,
            "mongo_query": str(mongo_query),
            "results_count": len(results),
            "sample_results": results[:2] if results else [],
            "debug_info": {
                "district_search": pattern_result.get("district_name"),
                "colors_requested": pattern_result.get("colors"),
                "indicators_requested": pattern_result.get("indicators")
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})


    """Check what Sunnyvale data actually exists"""
    try:
        # Find all Sunnyvale schools
        all_sunnyvale = list(schools_collection.find(
            {"district_name": {"$regex": "sunnyvale", "$options": "i"}},
            {"school_name": 1, "district_name": 1, "dashboard_indicators": 1, "_id": 0}
        ))
        
        # Find schools with Red indicators
        red_chronic = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.chronic_absenteeism.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.chronic_absenteeism": 1, "_id": 0}
        ))
        
        red_ela = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.ela_performance.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.ela_performance": 1, "_id": 0}
        ))
        
        red_math = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.math_performance.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.math_performance": 1, "_id": 0}
        ))
        
        # Check student groups with Red status
        red_student_groups = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "$or": [
                    {"student_groups.HI.chronic_absenteeism.status": "Red"},
                    {"student_groups.HI.ela_performance.status": "Red"},
                    {"student_groups.HI.math_performance.status": "Red"},
                    {"student_groups.EL.chronic_absenteeism.status": "Red"},
                    {"student_groups.EL.ela_performance.status": "Red"},
                    {"student_groups.EL.math_performance.status": "Red"},
                    {"student_groups.SWD.chronic_absenteeism.status": "Red"},
                    {"student_groups.SWD.ela_performance.status": "Red"},
                    {"student_groups.SWD.math_performance.status": "Red"}
                ]
            },
            {"school_name": 1, "student_groups": 1, "_id": 0}
        ))
        
        return jsonify({
            "total_sunnyvale_schools": len(all_sunnyvale),
            "sunnyvale_schools": [s["school_name"] for s in all_sunnyvale],
            "red_overall_indicators": {
                "chronic_absenteeism": len(red_chronic),
                "ela_performance": len(red_ela),
                "math_performance": len(red_math)
            },
            "red_overall_details": {
                "chronic_schools": [s["school_name"] for s in red_chronic],
                "ela_schools": [s["school_name"] for s in red_ela],
                "math_schools": [s["school_name"] for s in red_math]
            },
            "red_student_groups_count": len(red_student_groups),
            "sample_red_student_data": red_student_groups[:2] if red_student_groups else []
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})

# ALSO UPDATE your build_mongodb_query function to be more flexible:
def build_mongodb_query(parsed_query):
    """Improved MongoDB query builder with better debugging"""
    query_filter = {}
    
    print(f"DEBUG - Building query from: {parsed_query}")
    
    # District filter with case-insensitive regex
    if parsed_query.get("district_name"):
        district_pattern = parsed_query["district_name"]
        query_filter["district_name"] = {"$regex": district_pattern, "$options": "i"}
        print(f"DEBUG - District filter: {query_filter['district_name']}")
    
    # School filter
    if parsed_query.get("school_name"):
        query_filter["school_name"] = {"$regex": parsed_query["school_name"], "$options": "i"}
    
    # Color-based filters
    if parsed_query.get("colors"):
        color_conditions = []
        colors = parsed_query["colors"]
        
        print(f"DEBUG - Looking for colors: {colors}")
        
        # If specific student groups mentioned
        if parsed_query.get("student_groups"):
            for student_group in parsed_query["student_groups"]:
                if parsed_query.get("indicators"):
                    # Specific indicators for specific groups
                    for indicator in parsed_query["indicators"]:
                        condition = {f"student_groups.{student_group}.{indicator}.status": {"$in": colors}}
                        color_conditions.append(condition)
                        print(f"DEBUG - Added condition: {condition}")
                else:
                    # All indicators for specific groups
                    for indicator in ["chronic_absenteeism", "ela_performance", "math_performance"]:
                        condition = {f"student_groups.{student_group}.{indicator}.status": {"$in": colors}}
                        color_conditions.append(condition)
                        print(f"DEBUG - Added condition: {condition}")
        else:
            # Default to overall indicators (dashboard_indicators)
            if parsed_query.get("indicators"):
                for indicator in parsed_query["indicators"]:
                    condition = {f"dashboard_indicators.{indicator}.status": {"$in": colors}}
                    color_conditions.append(condition)
                    print(f"DEBUG - Added overall condition: {condition}")
            else:
                # All indicators overall
                for indicator in ["chronic_absenteeism", "ela_performance", "math_performance"]:
                    condition = {f"dashboard_indicators.{indicator}.status": {"$in": colors}}
                    color_conditions.append(condition)
                    print(f"DEBUG - Added overall condition: {condition}")
        
        if color_conditions:
            query_filter["$or"] = color_conditions
            print(f"DEBUG - Final $or conditions: {len(color_conditions)} conditions")
    
    print(f"DEBUG - Final MongoDB query: {query_filter}")
    return query_filter

    """Convert parsed query into MongoDB filter with ALL six indicators support"""
    query_filter = {}
    
    # District filter
    if parsed_query.get("district_name"):
        query_filter["district_name"] = {"$regex": parsed_query["district_name"], "$options": "i"}
    
    # School filter
    if parsed_query.get("school_name"):
        query_filter["school_name"] = {"$regex": parsed_query["school_name"], "$options": "i"}
    
    # Student group and color filters
    if parsed_query.get("colors"):
        color_conditions = []
        
        # If specific student groups mentioned
        if parsed_query.get("student_groups"):
            for student_group in parsed_query["student_groups"]:
                if parsed_query.get("indicators"):
                    # Specific indicators for specific groups
                    for indicator in parsed_query["indicators"]:
                        color_conditions.append({
                            f"student_groups.{student_group}.{indicator}.status": {"$in": parsed_query["colors"]}
                        })
                else:
                    # All indicators for specific groups
                    for indicator in ["chronic_absenteeism", "ela_performance", "math_performance", "english_learner_progress", "suspension_rate", "college_career"]:
                        color_conditions.append({
                            f"student_groups.{student_group}.{indicator}.status": {"$in": parsed_query["colors"]}
                        })
        else:
            # Default to overall indicators (ALL student group)
            if parsed_query.get("indicators"):
                for indicator in parsed_query["indicators"]:
                    color_conditions.append({
                        f"dashboard_indicators.{indicator}.status": {"$in": parsed_query["colors"]}
                    })
            else:
                for indicator in ["chronic_absenteeism", "ela_performance", "math_performance", "english_learner_progress", "suspension_rate", "college_career"]:
                    color_conditions.append({
                        f"dashboard_indicators.{indicator}.status": {"$in": parsed_query["colors"]}
                    })
        
        if color_conditions:
            query_filter["$or"] = color_conditions
    
    # Specific indicator filters without colors
    elif parsed_query.get("indicators"):
        indicator_conditions = []
        
        if parsed_query.get("student_groups"):
            for student_group in parsed_query["student_groups"]:
                for indicator in parsed_query["indicators"]:
                    indicator_conditions.append({
                        f"student_groups.{student_group}.{indicator}": {"$exists": True}
                    })
        else:
            for indicator in parsed_query["indicators"]:
                indicator_conditions.append({
                    f"dashboard_indicators.{indicator}": {"$exists": True}
                })
        
        if indicator_conditions:
            query_filter["$or"] = indicator_conditions
    
    return query_filter

def generate_intelligent_response(user_query: str, results: List[Dict], parsed_query: Dict) -> str:
    """Generate AI-powered response using Gemini for analysis"""
    
    # Check if data is available
    if parsed_query.get("data_availability") == "not_available":
        return f"❌ **Data Not Available**: {parsed_query.get('explanation', 'Requested data is not in the current dataset.')}\n\n✅ **Available Data**: I can help you analyze chronic absenteeism, ELA performance, and math performance across all student groups."
    
    if not results:
        return "I didn't find any schools matching your criteria. Try adjusting your search terms."
    
    # Use AI to generate intelligent response if available
    if AI_ENABLED and len(results) <= 10:  # Use AI for smaller result sets
        try:
            ai_response = generate_ai_analysis(user_query, results, parsed_query)
            if ai_response:
                return ai_response
        except Exception as e:
            print(f"AI response generation failed: {e}")
    
    # Fallback to template-based response
    return generate_template_response(user_query, results, parsed_query)
    """Generate enhanced natural language response with ALL SIX CA Dashboard indicators"""
    if not results:
        return "I didn't find any schools matching your criteria. Try adjusting your search terms or check the spelling of district/school names."
    
    # Analyze results with complete technical understanding
    analysis = {
        "total_schools": len(results),
        "districts": list(set([r.get("district_name", "") for r in results if r.get("district_name")])),
        "problem_areas": {},
        "performance_summary": {"Red": [], "Orange": [], "Yellow": [], "Green": [], "Blue": []}
    }
    
    # Determine target student groups
    target_student_groups = parsed_query.get("student_groups", ["ALL"])
    if not target_student_groups:
        target_student_groups = ["ALL"]
    
    # Analyze each school's indicators with complete technical context
    for school in results:
        school_name = school.get("school_name", "Unknown School")
        
        for group_code in target_student_groups:
            group_name = get_student_group_name(group_code)
            
            # Get indicators from appropriate location
            if group_code == "ALL":
                indicators = school.get("dashboard_indicators", {})
            else:
                indicators = school.get("student_groups", {}).get(group_code, {})
            
            for indicator_name, indicator_data in indicators.items():
                if isinstance(indicator_data, dict):
                    status = indicator_data.get("status", "Unknown")
                    
                    if status in ["Red", "Orange", "Yellow", "Green", "Blue"]:
                        analysis["performance_summary"][status].append({
                            "school": school_name,
                            "indicator": indicator_name,
                            "student_group": group_name,
                            "value": indicator_data.get("rate", indicator_data.get("points_below_standard", 0)),
                            "change": indicator_data.get("change", 0)
                        })
                    
                    # Track problem areas (Red/Orange)
                    if status in ["Red", "Orange"]:
                        key = f"{indicator_name}_{group_name}"
                        if key not in analysis["problem_areas"]:
                            analysis["problem_areas"][key] = []
                        
                        analysis["problem_areas"][key].append({
                            "school": school_name,
                            "status": status,
                            "value": indicator_data.get("rate", indicator_data.get("points_below_standard", 0)),
                            "change": indicator_data.get("change", 0),
                            "student_group": group_name,
                            "indicator": indicator_name
                        })
    
    # Generate technically accurate response
    response_parts = []
    
    # Context header
    if len(analysis["districts"]) == 1:
        district = analysis["districts"][0]
        response_parts.append(f"**📊 {district} Analysis:**")
    
    # Single school detailed analysis
    if len(results) == 1:
        school = results[0]
        school_name = school.get("school_name", "Unknown School")
        district_name = school.get("district_name", "Unknown District")
        
        response_parts.append(f"**🏫 {school_name}** ({district_name})")
        
        for group_code in target_student_groups:
            group_name = get_student_group_name(group_code)
            
            if group_code == "ALL":
                indicators = school.get("dashboard_indicators", {})
                response_parts.append(f"\n**📈 Overall School Performance:**")
            else:
                indicators = school.get("student_groups", {}).get(group_code, {})
                response_parts.append(f"\n**👥 {group_name} Performance:**")
            
            if not indicators:
                response_parts.append(f"• No data available for {group_name}")
                continue
            
            # Analyze each indicator with complete technical context
            for indicator_name, indicator_data in indicators.items():
                if isinstance(indicator_data, dict):
                    status = indicator_data.get("status", "Unknown")
                    if status == "Unknown":
                        continue
                    
                    indicator_display = indicator_name.replace("_", " ").title()
                    value = indicator_data.get("rate", indicator_data.get("points_below_standard", 0))
                    change = indicator_data.get("change", 0)
                    
                    # Technical interpretation by indicator type
                    if indicator_name == "chronic_absenteeism":
                        # REVERSE GOAL: Lower is better
                        interpretation = f"{value:.1f}% students chronically absent"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (concerning - target <5%)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (excellent - well below 10% threshold)"
                        
                        # Change interpretation (reverse goal)
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "worsened (increased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ⚠️"
                            else:
                                direction = "improved (decreased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ✅"
                    
                    elif indicator_name == "suspension_rate":
                        # REVERSE GOAL: Lower is better (like chronic absenteeism)
                        interpretation = f"{value:.1f}% students suspended (≥1 full day)"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (concerning - target <2%)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (excellent - low suspension rates)"
                        
                        # Change interpretation (reverse goal)
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "worsened (increased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ⚠️"
                            else:
                                direction = "improved (decreased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ✅"
                    
                    elif indicator_name == "college_career":
                        # NEW: College/Career readiness - higher is better
                        interpretation = f"{value:.1f}% graduates college/career prepared"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (needs improvement - target 60%+)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (excellent - strong post-secondary preparation)"
                        
                        # Change interpretation (higher is better)
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "improved (increased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ✅"
                            else:
                                direction = "declined (decreased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ⚠️"
                    
                    elif indicator_name in ["ela_performance", "math_performance"]:
                        # DFS: negative = below standard, positive = above standard
                        subject = "ELA" if indicator_name == "ela_performance" else "Math"
                        if value >= 0:
                            interpretation = f"{value:.1f} points above standard (meeting {subject} expectations)"
                        else:
                            interpretation = f"{abs(value):.1f} points below standard (needs {subject} improvement)"
                        
                        # Change context
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "improved"
                                change_text = f", {direction} by {abs(change):.1f} points ✅"
                            else:
                                direction = "declined"
                                change_text = f", {direction} by {abs(change):.1f} points ⚠️"
                    
                    elif indicator_name == "english_learner_progress":
                        # ELPI: Percentage making progress toward English proficiency
                        interpretation = f"{value:.1f}% of English learners making progress toward proficiency"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (needs improvement - target 60%+)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (strong progress rates)"
                        
                        change_text = ""
                        if change != 0:
                            direction = "improved" if change > 0 else "declined"
                            change_text = f", {direction} by {abs(change):.1f} percentage points"
                    
                    else:
                        interpretation = f"Score: {value:.1f}"
                        change_text = ""
                        if change != 0:
                            direction = "improved" if change > 0 else "declined"
                            change_text = f", {direction} by {abs(change):.1f} points"
                    
                    response_parts.append(f"• **{indicator_display}**: {status} ({interpretation}{change_text})")
    
    # Multiple schools - problem areas summary
    elif analysis["problem_areas"]:
        red_orange_count = sum(len(schools) for schools in analysis["problem_areas"].values())
        response_parts.append(f"\n**🚨 Areas Needing Attention** ({red_orange_count} Red/Orange indicators across {len(results)} schools):")
        
        for problem_key, schools in analysis["problem_areas"].items():
            indicator_name, group_name = problem_key.rsplit("_", 1)
            indicator_display = indicator_name.replace("_", " ").title()
            
            red_count = len([s for s in schools if s["status"] == "Red"])
            orange_count = len([s for s in schools if s["status"] == "Orange"])
            
            status_summary = []
            if red_count > 0:
                status_summary.append(f"🔴 {red_count} Red")
            if orange_count > 0:
                status_summary.append(f"🟠 {orange_count} Orange")
            
            response_parts.append(f"• **{indicator_display}** ({group_name}): {' + '.join(status_summary)}")
            
            # Show specific schools for small result sets
            if len(schools) <= 3:
                for school_data in schools:
                    value = school_data["value"]
                    change = school_data.get("change", 0)
                    change_text = f" (Δ{change:+.1f})" if change != 0 else ""
                    indicator = school_data.get("indicator", "")
                    
                    if indicator in ["chronic_absenteeism", "suspension_rate"]:
                        metric = "chronically absent" if indicator == "chronic_absenteeism" else "suspended"
                        response_parts.append(f"  - {school_data['school']}: {value:.1f}% {metric}{change_text}")
                    elif indicator == "college_career":
                        response_parts.append(f"  - {school_data['school']}: {value:.1f}% college/career prepared{change_text}")
                    elif indicator in ["ela_performance", "math_performance"]:
                        if value >= 0:
                            response_parts.append(f"  - {school_data['school']}: +{value:.1f} pts above standard{change_text}")
                        else:
                            response_parts.append(f"  - {school_data['school']}: {value:.1f} pts below standard{change_text}")
                    else:
                        response_parts.append(f"  - {school_data['school']}: {value:.1f}%{change_text}")
    
    # Performance summary for larger datasets
    else:
        total_indicators = sum(len(perf_list) for perf_list in analysis["performance_summary"].values())
        if total_indicators > 0:
            response_parts.append(f"\n**📊 Performance Summary** ({total_indicators} indicators across {len(results)} schools):")
            
            for color, indicators in analysis["performance_summary"].items():
                if indicators:
                    color_emoji = {"Red": "🔴", "Orange": "🟠", "Yellow": "🟡", "Green": "🟢", "Blue": "🔵"}
                    response_parts.append(f"• {color_emoji.get(color, '')} **{color}**: {len(indicators)} indicators")
    
    # Add actionable insights for educators
    if analysis["problem_areas"]:
        response_parts.append(f"\n**💡 Recommended Actions:**")
        
        if any("chronic_absenteeism" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **Attendance Crisis**: Implement PBIS, family engagement, and attendance recovery programs")
            response_parts.append("• **Root Causes**: Address transportation, health, housing instability, and school climate issues")
        
        if any("suspension_rate" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **Discipline Reform**: Implement restorative justice, PBIS, and alternative discipline strategies")
            response_parts.append("• **Climate Focus**: Address bias, improve school culture, and provide trauma-informed practices")
        
        if any("college_career" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **College/Career Prep**: Expand a-g course access, CTE pathways, and dual enrollment opportunities")
            response_parts.append("• **Pathways**: Strengthen AP/IB programs, industry partnerships, and post-secondary counseling")
        
        if any("ela_performance" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **ELA Support**: Enhanced literacy intervention, reading specialists, and professional development")
            response_parts.append("• **Strategy**: Focus on phonics, comprehension strategies, and differentiated instruction")
        
        if any("math_performance" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **Math Intervention**: Targeted support, manipulatives, and conceptual understanding focus")
            response_parts.append("• **Approach**: Address foundational skills gaps and mathematical reasoning")
        
        if any("english_learner_progress" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **EL Support**: Designated ELD time, SDAIE strategies, and bilingual resources")
            response_parts.append("• **Focus**: Academic language development and ELPAC preparation")
    
    return "\n".join(response_parts) if response_parts else f"Found {len(results)} schools. Check the detailed results below for specific performance data."
    """Generate enhanced natural language response with ALL five CA Dashboard indicators"""
    if not results:
        return "I didn't find any schools matching your criteria. Try adjusting your search terms or check the spelling of district/school names."
    
    # Analyze results with complete technical understanding
    analysis = {
        "total_schools": len(results),
        "districts": list(set([r.get("district_name", "") for r in results if r.get("district_name")])),
        "problem_areas": {},
        "performance_summary": {"Red": [], "Orange": [], "Yellow": [], "Green": [], "Blue": []}
    }
    
    # Determine target student groups
    target_student_groups = parsed_query.get("student_groups", ["ALL"])
    if not target_student_groups:
        target_student_groups = ["ALL"]
    
    # Analyze each school's indicators with complete technical context
    for school in results:
        school_name = school.get("school_name", "Unknown School")
        
        for group_code in target_student_groups:
            group_name = get_student_group_name(group_code)
            
            # Get indicators from appropriate location
            if group_code == "ALL":
                indicators = school.get("dashboard_indicators", {})
            else:
                indicators = school.get("student_groups", {}).get(group_code, {})
            
            for indicator_name, indicator_data in indicators.items():
                if isinstance(indicator_data, dict):
                    status = indicator_data.get("status", "Unknown")
                    
                    if status in ["Red", "Orange", "Yellow", "Green", "Blue"]:
                        analysis["performance_summary"][status].append({
                            "school": school_name,
                            "indicator": indicator_name,
                            "student_group": group_name,
                            "value": indicator_data.get("rate", indicator_data.get("points_below_standard", 0)),
                            "change": indicator_data.get("change", 0)
                        })
                    
                    # Track problem areas (Red/Orange)
                    if status in ["Red", "Orange"]:
                        key = f"{indicator_name}_{group_name}"
                        if key not in analysis["problem_areas"]:
                            analysis["problem_areas"][key] = []
                        
                        analysis["problem_areas"][key].append({
                            "school": school_name,
                            "status": status,
                            "value": indicator_data.get("rate", indicator_data.get("points_below_standard", 0)),
                            "change": indicator_data.get("change", 0),
                            "student_group": group_name,
                            "indicator": indicator_name
                        })
    
    # Generate technically accurate response
    response_parts = []
    
    # Context header
    if len(analysis["districts"]) == 1:
        district = analysis["districts"][0]
        response_parts.append(f"**📊 {district} Analysis:**")
    
    # Single school detailed analysis
    if len(results) == 1:
        school = results[0]
        school_name = school.get("school_name", "Unknown School")
        district_name = school.get("district_name", "Unknown District")
        
        response_parts.append(f"**🏫 {school_name}** ({district_name})")
        
        for group_code in target_student_groups:
            group_name = get_student_group_name(group_code)
            
            if group_code == "ALL":
                indicators = school.get("dashboard_indicators", {})
                response_parts.append(f"\n**📈 Overall School Performance:**")
            else:
                indicators = school.get("student_groups", {}).get(group_code, {})
                response_parts.append(f"\n**👥 {group_name} Performance:**")
            
            if not indicators:
                response_parts.append(f"• No data available for {group_name}")
                continue
            
            # Analyze each indicator with complete technical context
            for indicator_name, indicator_data in indicators.items():
                if isinstance(indicator_data, dict):
                    status = indicator_data.get("status", "Unknown")
                    if status == "Unknown":
                        continue
                    
                    indicator_display = indicator_name.replace("_", " ").title()
                    value = indicator_data.get("rate", indicator_data.get("points_below_standard", 0))
                    change = indicator_data.get("change", 0)
                    
                    # Technical interpretation by indicator type
                    if indicator_name == "chronic_absenteeism":
                        # REVERSE GOAL: Lower is better
                        interpretation = f"{value:.1f}% students chronically absent"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (concerning - target <5%)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (excellent - well below 10% threshold)"
                        
                        # Change interpretation (reverse goal)
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "worsened (increased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ⚠️"
                            else:
                                direction = "improved (decreased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ✅"
                    
                    elif indicator_name == "suspension_rate":
                        # NEW: REVERSE GOAL: Lower is better (like chronic absenteeism)
                        interpretation = f"{value:.1f}% students suspended (≥1 full day)"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (concerning - target <2%)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (excellent - low suspension rates)"
                        
                        # Change interpretation (reverse goal)
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "worsened (increased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ⚠️"
                            else:
                                direction = "improved (decreased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ✅"
                    
                    elif indicator_name in ["ela_performance", "math_performance"]:
                        # DFS: negative = below standard, positive = above standard
                        subject = "ELA" if indicator_name == "ela_performance" else "Math"
                        if value >= 0:
                            interpretation = f"{value:.1f} points above standard (meeting {subject} expectations)"
                        else:
                            interpretation = f"{abs(value):.1f} points below standard (needs {subject} improvement)"
                        
                        # Change context
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "improved"
                                change_text = f", {direction} by {abs(change):.1f} points ✅"
                            else:
                                direction = "declined"
                                change_text = f", {direction} by {abs(change):.1f} points ⚠️"
                    
                    elif indicator_name == "english_learner_progress":
                        # ELPI: Percentage making progress toward English proficiency
                        interpretation = f"{value:.1f}% of English learners making progress toward proficiency"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (needs improvement - target 60%+)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (strong progress rates)"
                        
                        change_text = ""
                        if change != 0:
                            direction = "improved" if change > 0 else "declined"
                            change_text = f", {direction} by {abs(change):.1f} percentage points"
                    
                    else:
                        interpretation = f"Score: {value:.1f}"
                        change_text = ""
                        if change != 0:
                            direction = "improved" if change > 0 else "declined"
                            change_text = f", {direction} by {abs(change):.1f} points"
                    
                    response_parts.append(f"• **{indicator_display}**: {status} ({interpretation}{change_text})")
    
    # Multiple schools - problem areas summary
    elif analysis["problem_areas"]:
        red_orange_count = sum(len(schools) for schools in analysis["problem_areas"].values())
        response_parts.append(f"\n**🚨 Areas Needing Attention** ({red_orange_count} Red/Orange indicators across {len(results)} schools):")
        
        for problem_key, schools in analysis["problem_areas"].items():
            indicator_name, group_name = problem_key.rsplit("_", 1)
            indicator_display = indicator_name.replace("_", " ").title()
            
            red_count = len([s for s in schools if s["status"] == "Red"])
            orange_count = len([s for s in schools if s["status"] == "Orange"])
            
            status_summary = []
            if red_count > 0:
                status_summary.append(f"🔴 {red_count} Red")
            if orange_count > 0:
                status_summary.append(f"🟠 {orange_count} Orange")
            
            response_parts.append(f"• **{indicator_display}** ({group_name}): {' + '.join(status_summary)}")
            
            # Show specific schools for small result sets
            if len(schools) <= 3:
                for school_data in schools:
                    value = school_data["value"]
                    change = school_data.get("change", 0)
                    change_text = f" (Δ{change:+.1f})" if change != 0 else ""
                    indicator = school_data.get("indicator", "")
                    
                    if indicator in ["chronic_absenteeism", "suspension_rate"]:
                        metric = "chronically absent" if indicator == "chronic_absenteeism" else "suspended"
                        response_parts.append(f"  - {school_data['school']}: {value:.1f}% {metric}{change_text}")
                    elif indicator in ["ela_performance", "math_performance"]:
                        if value >= 0:
                            response_parts.append(f"  - {school_data['school']}: +{value:.1f} pts above standard{change_text}")
                        else:
                            response_parts.append(f"  - {school_data['school']}: {value:.1f} pts below standard{change_text}")
                    else:
                        response_parts.append(f"  - {school_data['school']}: {value:.1f}%{change_text}")
    
    # Performance summary for larger datasets
    else:
        total_indicators = sum(len(perf_list) for perf_list in analysis["performance_summary"].values())
        if total_indicators > 0:
            response_parts.append(f"\n**📊 Performance Summary** ({total_indicators} indicators across {len(results)} schools):")
            
            for color, indicators in analysis["performance_summary"].items():
                if indicators:
                    color_emoji = {"Red": "🔴", "Orange": "🟠", "Yellow": "🟡", "Green": "🟢", "Blue": "🔵"}
                    response_parts.append(f"• {color_emoji.get(color, '')} **{color}**: {len(indicators)} indicators")
    
    # Add actionable insights for educators
    if analysis["problem_areas"]:
        response_parts.append(f"\n**💡 Recommended Actions:**")
        
        if any("chronic_absenteeism" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **Attendance Crisis**: Implement PBIS, family engagement, and attendance recovery programs")
            response_parts.append("• **Root Causes**: Address transportation, health, housing instability, and school climate issues")
        
        if any("suspension_rate" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **Discipline Reform**: Implement restorative justice, PBIS, and alternative discipline strategies")
            response_parts.append("• **Climate Focus**: Address bias, improve school culture, and provide trauma-informed practices")
        
        if any("ela_performance" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **ELA Support**: Enhanced literacy intervention, reading specialists, and professional development")
            response_parts.append("• **Strategy**: Focus on phonics, comprehension strategies, and differentiated instruction")
        
        if any("math_performance" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **Math Intervention**: Targeted support, manipulatives, and conceptual understanding focus")
            response_parts.append("• **Approach**: Address foundational skills gaps and mathematical reasoning")
        
        if any("english_learner_progress" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **EL Support**: Designated ELD time, SDAIE strategies, and bilingual resources")
            response_parts.append("• **Focus**: Academic language development and ELPAC preparation")
    
    return "\n".join(response_parts) if response_parts else f"Found {len(results)} schools. Check the detailed results below for specific performance data."
    """Enhanced string-based query parsing with comprehensive CA Dashboard awareness"""
    query_lower = user_query.lower()
    
    parsed = {
        "district_name": None,
        "school_name": None, 
        "colors": [],
        "indicators": [],
        "student_groups": []
    }
    
    # Extract district name (expanded list)
    district_patterns = [
        ("sunnyvale", "Sunnyvale"),
        ("san francisco", "San Francisco Unified"),
        ("los angeles", "Los Angeles Unified"),
        ("oakland", "Oakland Unified"),
        ("san diego", "San Diego Unified"),
        ("alameda unified", "Alameda Unified"),
        ("alameda county", "Alameda County Office of Education"),
        ("fresno", "Fresno Unified"),
        ("sacramento", "Sacramento City Unified"),
        ("long beach", "Long Beach Unified"),
        ("san bernardino", "San Bernardino City Unified"),
        ("san juan", "San Juan Unified"),
        ("elk grove", "Elk Grove Unified"),
        ("santa clara", "Santa Clara Unified"),
        ("palo alto", "Palo Alto Unified"),
        ("fremont", "Fremont Unified")
    ]
    
    for pattern, district in district_patterns:
        if pattern in query_lower:
            parsed["district_name"] = district
            break
    
    # Extract school name (expanded list)
    school_patterns = [
        ("san miguel elementary", "San Miguel Elementary"),
        ("bishop elementary", "Bishop Elementary"),
        ("sunnyvale middle", "Sunnyvale Middle"),
        ("columbia middle", "Columbia Middle"),
        ("vargas elementary", "Vargas Elementary"),
        ("cherry chase elementary", "Cherry Chase Elementary"),
        ("fairwood elementary", "Fairwood Elementary"),
        ("lakewood elementary", "Lakewood Elementary"),
        ("ellis elementary", "Ellis Elementary"),
        ("cumberland elementary", "Cumberland Elementary"),
        ("lincoln elementary", "Lincoln Elementary"),
        ("washington elementary", "Washington Elementary"),
        ("roosevelt middle", "Roosevelt Middle"),
        ("jefferson high", "Jefferson High"),
        ("kennedy elementary", "Kennedy Elementary")
    ]
    
    for pattern, school in school_patterns:
        if pattern in query_lower:
            parsed["school_name"] = school
            break
    
    # Extract student groups (comprehensive)
    student_group_patterns = [
        ("hispanic", "HI"),
        ("latino", "HI"), 
        ("black", "AA"),
        ("african american", "AA"),
        ("asian", "AS"),
        ("white", "WH"),
        ("filipino", "FI"),
        ("pacific islander", "PI"),
        ("american indian", "AI"),
        ("two or more races", "MR"),
        ("english learners", "EL"),
        ("english learner", "EL"),
        ("long-term english learners", "LTEL"),
        ("long term english learners", "LTEL"),
        ("socioeconomically disadvantaged", "SED"),
        ("low income", "SED"),
        ("economically disadvantaged", "SED"),
        ("students with disabilities", "SWD"),
        ("special education", "SWD"),
        ("special needs", "SWD"),
        ("homeless", "HOM"),
        ("foster", "FOS"),
        ("foster youth", "FOS"),
        ("all students", "ALL")
    ]
    
    for pattern, code in student_group_patterns:
        if pattern in query_lower:
            parsed["student_groups"].append(code)
    
    # Extract colors
    color_words = ["red", "orange", "yellow", "green", "blue"]
    for color in color_words:
        if color in query_lower:
            parsed["colors"].append(color.title())
    
    # Extract indicators with comprehensive matching
    if any(word in query_lower for word in ["chronic", "absenteeism", "attendance", "absent", "truancy"]):
        parsed["indicators"].append("chronic_absenteeism")
    
    if any(word in query_lower for word in ["ela", "english language arts", "reading", "language arts", "literacy"]):
        parsed["indicators"].append("ela_performance") 
    
    if any(word in query_lower for word in ["math", "mathematics", "arithmetic", "algebra", "geometry"]):
        parsed["indicators"].append("math_performance")
    
    if any(word in query_lower for word in ["english learner progress", "elpi", "elpac", "language proficiency"]):
        parsed["indicators"].append("english_learner_progress")
    
    # Better context understanding
    problem_phrases = [
        "lowest", "worst", "poorest", "struggling", "needs improvement", 
        "problem areas", "areas of concern", "failing", "underperforming",
        "below standard", "not meeting", "deficient"
    ]
    
    if any(phrase in query_lower for phrase in problem_phrases):
        if not parsed["colors"]:
            parsed["colors"] = ["Red", "Orange"]
    
    success_phrases = [
        "best", "highest", "top", "excellent", "performing well", 
        "exceeding", "outstanding", "successful", "above standard"
    ]
    
    if any(phrase in query_lower for phrase in success_phrases):
        if not parsed["colors"]:
            parsed["colors"] = ["Green", "Blue"]
    
    print(f"DEBUG - Parsed query: {parsed}")
    return parsed


    """Convert parsed query into MongoDB filter with comprehensive student group support"""
    query_filter = {}
    
    # District filter
    if parsed_query.get("district_name"):
        query_filter["district_name"] = {"$regex": parsed_query["district_name"], "$options": "i"}
    
    # School filter
    if parsed_query.get("school_name"):
        query_filter["school_name"] = {"$regex": parsed_query["school_name"], "$options": "i"}
    
    # Student group and color filters
    if parsed_query.get("colors"):
        color_conditions = []
        
        # If specific student groups mentioned
        if parsed_query.get("student_groups"):
            for student_group in parsed_query["student_groups"]:
                if parsed_query.get("indicators"):
                    # Specific indicators for specific groups
                    for indicator in parsed_query["indicators"]:
                        color_conditions.append({
                            f"student_groups.{student_group}.{indicator}.status": {"$in": parsed_query["colors"]}
                        })
                else:
                    # All indicators for specific groups
                    for indicator in ["chronic_absenteeism", "ela_performance", "math_performance", "english_learner_progress"]:
                        color_conditions.append({
                            f"student_groups.{student_group}.{indicator}.status": {"$in": parsed_query["colors"]}
                        })
        else:
            # Default to overall indicators (ALL student group)
            if parsed_query.get("indicators"):
                for indicator in parsed_query["indicators"]:
                    color_conditions.append({
                        f"dashboard_indicators.{indicator}.status": {"$in": parsed_query["colors"]}
                    })
            else:
                for indicator in ["chronic_absenteeism", "ela_performance", "math_performance", "english_learner_progress"]:
                    color_conditions.append({
                        f"dashboard_indicators.{indicator}.status": {"$in": parsed_query["colors"]}
                    })
        
        if color_conditions:
            query_filter["$or"] = color_conditions
    
    # Specific indicator filters without colors
    elif parsed_query.get("indicators"):
        indicator_conditions = []
        
        if parsed_query.get("student_groups"):
            for student_group in parsed_query["student_groups"]:
                for indicator in parsed_query["indicators"]:
                    indicator_conditions.append({
                        f"student_groups.{student_group}.{indicator}": {"$exists": True}
                    })
        else:
            for indicator in parsed_query["indicators"]:
                indicator_conditions.append({
                    f"dashboard_indicators.{indicator}": {"$exists": True}
                })
        
        if indicator_conditions:
            query_filter["$or"] = indicator_conditions
    
    return query_filter
def generate_template_response(user_query: str, results: List[Dict], parsed_query: Dict) -> str:
    """Generate template-based response (fallback)"""
    
    if len(results) == 1:
        # Single school detailed analysis
        school = results[0]
        school_name = school.get("school_name", "Unknown School")
        district_name = school.get("district_name", "Unknown District")
        
        response_parts = [f"**🏫 {school_name}** ({district_name})"]
        
        # Show overall performance
        overall_indicators = school.get("dashboard_indicators", {})
        if overall_indicators:
            response_parts.append("\n**📈 Overall School Performance:**")
            for indicator, data in overall_indicators.items():
                if isinstance(data, dict) and data.get("status") != "No Data":
                    status = data.get("status", "Unknown")
                    value = data.get("rate", data.get("points_below_standard", 0))
                    
                    if indicator == "chronic_absenteeism":
                        response_parts.append(f"• **Chronic Absenteeism**: {status} ({value:.1f}% students chronically absent)")
                    elif indicator == "ela_performance":
                        if value >= 0:
                            response_parts.append(f"• **ELA Performance**: {status} ({value:.1f} points above standard)")
                        else:
                            response_parts.append(f"• **ELA Performance**: {status} ({abs(value):.1f} points below standard)")
                    elif indicator == "math_performance":
                        if value >= 0:
                            response_parts.append(f"• **Math Performance**: {status} ({value:.1f} points above standard)")
                        else:
                            response_parts.append(f"• **Math Performance**: {status} ({abs(value):.1f} points below standard)")
        
        return "\n".join(response_parts)
    else:
        # Multiple schools summary
        return f"**📊 Found {len(results)} schools matching your criteria.** Check the detailed results below for specific performance data by school and student group."


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


    """Generate enhanced natural language response with complete CA Dashboard technical accuracy"""
    if not results:
        return "I didn't find any schools matching your criteria. Try adjusting your search terms or check the spelling of district/school names."
    
    # Analyze results with complete technical understanding
    analysis = {
        "total_schools": len(results),
        "districts": list(set([r.get("district_name", "") for r in results if r.get("district_name")])),
        "problem_areas": {},
        "performance_summary": {"Red": [], "Orange": [], "Yellow": [], "Green": [], "Blue": []}
    }
    
    # Determine target student groups
    target_student_groups = parsed_query.get("student_groups", ["ALL"])
    if not target_student_groups:
        target_student_groups = ["ALL"]
    
    # Analyze each school's indicators with complete technical context
    for school in results:
        school_name = school.get("school_name", "Unknown School")
        
        for group_code in target_student_groups:
            group_name = get_student_group_name(group_code)
            
            # Get indicators from appropriate location
            if group_code == "ALL":
                indicators = school.get("dashboard_indicators", {})
            else:
                indicators = school.get("student_groups", {}).get(group_code, {})
            
            for indicator_name, indicator_data in indicators.items():
                if isinstance(indicator_data, dict):
                    status = indicator_data.get("status", "Unknown")
                    
                    if status in ["Red", "Orange", "Yellow", "Green", "Blue"]:
                        analysis["performance_summary"][status].append({
                            "school": school_name,
                            "indicator": indicator_name,
                            "student_group": group_name,
                            "value": indicator_data.get("rate", indicator_data.get("points_below_standard", 0)),
                            "change": indicator_data.get("change", 0)
                        })
                    
                    # Track problem areas (Red/Orange)
                    if status in ["Red", "Orange"]:
                        key = f"{indicator_name}_{group_name}"
                        if key not in analysis["problem_areas"]:
                            analysis["problem_areas"][key] = []
                        
                        analysis["problem_areas"][key].append({
                            "school": school_name,
                            "status": status,
                            "value": indicator_data.get("rate", indicator_data.get("points_below_standard", 0)),
                            "change": indicator_data.get("change", 0),
                            "student_group": group_name,
                            "indicator": indicator_name
                        })
    
    # Generate technically accurate response
    response_parts = []
    
    # Context header
    if len(analysis["districts"]) == 1:
        district = analysis["districts"][0]
        response_parts.append(f"**📊 {district} Analysis:**")
    
    # Single school detailed analysis
    if len(results) == 1:
        school = results[0]
        school_name = school.get("school_name", "Unknown School")
        district_name = school.get("district_name", "Unknown District")
        
        response_parts.append(f"**🏫 {school_name}** ({district_name})")
        
        for group_code in target_student_groups:
            group_name = get_student_group_name(group_code)
            
            if group_code == "ALL":
                indicators = school.get("dashboard_indicators", {})
                response_parts.append(f"\n**📈 Overall School Performance:**")
            else:
                indicators = school.get("student_groups", {}).get(group_code, {})
                response_parts.append(f"\n**👥 {group_name} Performance:**")
            
            if not indicators:
                response_parts.append(f"• No data available for {group_name}")
                continue
            
            # Analyze each indicator with complete technical context
            for indicator_name, indicator_data in indicators.items():
                if isinstance(indicator_data, dict):
                    status = indicator_data.get("status", "Unknown")
                    if status == "Unknown":
                        continue
                    
                    indicator_display = indicator_name.replace("_", " ").title()
                    value = indicator_data.get("rate", indicator_data.get("points_below_standard", 0))
                    change = indicator_data.get("change", 0)
                    
                    # Technical interpretation by indicator type
                    if indicator_name == "chronic_absenteeism":
                        # REVERSE GOAL: Lower is better
                        interpretation = f"{value:.1f}% students chronically absent"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (concerning - target <5%)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (excellent - well below 10% threshold)"
                        
                        # Change interpretation (reverse goal)
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "worsened (increased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ⚠️"
                            else:
                                direction = "improved (decreased)"
                                change_text = f", {direction} by {abs(change):.1f} percentage points ✅"
                    
                    elif indicator_name in ["ela_performance", "math_performance"]:
                        # DFS: negative = below standard, positive = above standard
                        subject = "ELA" if indicator_name == "ela_performance" else "Math"
                        if value >= 0:
                            interpretation = f"{value:.1f} points above standard (meeting {subject} expectations)"
                        else:
                            interpretation = f"{abs(value):.1f} points below standard (needs {subject} improvement)"
                        
                        # Change context
                        change_text = ""
                        if change != 0:
                            if change > 0:
                                direction = "improved"
                                change_text = f", {direction} by {abs(change):.1f} points ✅"
                            else:
                                direction = "declined"
                                change_text = f", {direction} by {abs(change):.1f} points ⚠️"
                    
                    elif indicator_name == "english_learner_progress":
                        # ELPI: Percentage making progress toward English proficiency
                        interpretation = f"{value:.1f}% of English learners making progress toward proficiency"
                        if status in ["Red", "Orange"]:
                            interpretation += f" (needs improvement - target 60%+)"
                        elif status in ["Green", "Blue"]:
                            interpretation += f" (strong progress rates)"
                        
                        change_text = ""
                        if change != 0:
                            direction = "improved" if change > 0 else "declined"
                            change_text = f", {direction} by {abs(change):.1f} percentage points"
                    
                    else:
                        interpretation = f"Score: {value:.1f}"
                        change_text = ""
                        if change != 0:
                            direction = "improved" if change > 0 else "declined"
                            change_text = f", {direction} by {abs(change):.1f} points"
                    
                    response_parts.append(f"• **{indicator_display}**: {status} ({interpretation}{change_text})")
    
    # Multiple schools - problem areas summary
    elif analysis["problem_areas"]:
        red_orange_count = sum(len(schools) for schools in analysis["problem_areas"].values())
        response_parts.append(f"\n**🚨 Areas Needing Attention** ({red_orange_count} Red/Orange indicators across {len(results)} schools):")
        
        for problem_key, schools in analysis["problem_areas"].items():
            indicator_name, group_name = problem_key.rsplit("_", 1)
            indicator_display = indicator_name.replace("_", " ").title()
            
            red_count = len([s for s in schools if s["status"] == "Red"])
            orange_count = len([s for s in schools if s["status"] == "Orange"])
            
            status_summary = []
            if red_count > 0:
                status_summary.append(f"🔴 {red_count} Red")
            if orange_count > 0:
                status_summary.append(f"🟠 {orange_count} Orange")
            
            response_parts.append(f"• **{indicator_display}** ({group_name}): {' + '.join(status_summary)}")
            
            # Show specific schools for small result sets
            if len(schools) <= 3:
                for school_data in schools:
                    value = school_data["value"]
                    change = school_data.get("change", 0)
                    change_text = f" (Δ{change:+.1f})" if change != 0 else ""
                    indicator = school_data.get("indicator", "")
                    
                    if indicator == "chronic_absenteeism":
                        response_parts.append(f"  - {school_data['school']}: {value:.1f}% chronically absent{change_text}")
                    elif indicator in ["ela_performance", "math_performance"]:
                        if value >= 0:
                            response_parts.append(f"  - {school_data['school']}: +{value:.1f} pts above standard{change_text}")
                        else:
                            response_parts.append(f"  - {school_data['school']}: {value:.1f} pts below standard{change_text}")
                    else:
                        response_parts.append(f"  - {school_data['school']}: {value:.1f}%{change_text}")
    
    # Performance summary for larger datasets
    else:
        total_indicators = sum(len(perf_list) for perf_list in analysis["performance_summary"].values())
        if total_indicators > 0:
            response_parts.append(f"\n**📊 Performance Summary** ({total_indicators} indicators across {len(results)} schools):")
            
            for color, indicators in analysis["performance_summary"].items():
                if indicators:
                    color_emoji = {"Red": "🔴", "Orange": "🟠", "Yellow": "🟡", "Green": "🟢", "Blue": "🔵"}
                    response_parts.append(f"• {color_emoji.get(color, '')} **{color}**: {len(indicators)} indicators")
    
    # Add actionable insights for educators
    if analysis["problem_areas"]:
        response_parts.append(f"\n**💡 Recommended Actions:**")
        
        if any("chronic_absenteeism" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **Attendance Crisis**: Implement PBIS, family engagement, and attendance recovery programs")
            response_parts.append("• **Root Causes**: Address transportation, health, housing instability, and school climate issues")
        
        if any("ela_performance" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **ELA Support**: Enhanced literacy intervention, reading specialists, and professional development")
            response_parts.append("• **Strategy**: Focus on phonics, comprehension strategies, and differentiated instruction")
        
        if any("math_performance" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **Math Intervention**: Targeted support, manipulatives, and conceptual understanding focus")
            response_parts.append("• **Approach**: Address foundational skills gaps and mathematical reasoning")
        
        if any("english_learner_progress" in key for key in analysis["problem_areas"].keys()):
            response_parts.append("• **EL Support**: Designated ELD time, SDAIE strategies, and bilingual resources")
            response_parts.append("• **Focus**: Academic language development and ELPAC preparation")
    
    return "\n".join(response_parts) if response_parts else f"Found {len(results)} schools. Check the detailed results below for specific performance data."
def generate_ai_analysis(user_query: str, results: List[Dict], parsed_query: Dict) -> str:
    """Use Gemini to generate intelligent analysis of the results"""
    
    # Prepare data summary for AI
    data_summary = []
    for school in results[:5]:  # Limit to avoid token limits
        school_summary = {
            "school_name": school.get("school_name", "Unknown"),
            "district_name": school.get("district_name", "Unknown"),
            "overall_performance": school.get("dashboard_indicators", {}),
            "student_groups": {}
        }
        
        # Add relevant student group data
        target_groups = parsed_query.get("student_groups", ["ALL"])
        if not target_groups:
            target_groups = ["ALL"]
            
        for group in target_groups:
            if group in school.get("student_groups", {}):
                school_summary["student_groups"][group] = school["student_groups"][group]
        
        data_summary.append(school_summary)
    
    analysis_prompt = f"""
You are an expert California School Dashboard analyst. Analyze this school performance data and provide actionable insights.

USER QUERY: {user_query}

SCHOOL DATA: {json.dumps(data_summary, indent=2)}

ANALYSIS CONTEXT:
- chronic_absenteeism: % of students absent 10%+ days (LOWER is better)
- ela_performance: Points above/below standard (HIGHER is better)  
- math_performance: Points above/below standard (HIGHER is better)
- Red = Most concerning, Orange = Below average, Yellow = Average, Green = Above average, Blue = Best

Provide a comprehensive analysis that:
1. Directly answers the user's question
2. Identifies key patterns and concerns
3. Provides specific actionable recommendations
4. Uses clear, professional language appropriate for educators
5. Includes specific data points and school names
6. Focuses on equity and student outcomes

Format your response with clear sections and bullet points. Be specific and actionable.
"""

    try:
        response = model.generate_content(analysis_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"AI analysis failed: {e}")
        return None

# Enhanced HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>CA Schools AI Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            max-width: 1200px; margin: 0 auto; padding: 20px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header { 
            text-align: center; 
            color: white; 
            padding: 30px; 
            background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
        }
        .header h1 { margin: 0 0 10px 0; font-size: 2.2em; font-weight: 300; }
        .header p { margin: 0; opacity: 0.9; font-size: 1.1em; }
        
        .chat-container { 
            height: 400px; overflow-y: auto; padding: 25px; 
            background: #fafafa; border-bottom: 1px solid #e0e0e0;
        }
        .message { margin-bottom: 20px; }
        .user-message { text-align: right; }
        .user-message span { 
            background: linear-gradient(135deg, #1976d2, #1565c0); 
            color: white; padding: 12px 16px; border-radius: 18px 18px 4px 18px; 
            display: inline-block; max-width: 70%; box-shadow: 0 2px 8px rgba(25,118,210,0.3);
        }
        .ai-message span { 
            background: white; border: 1px solid #e0e0e0; 
            padding: 12px 16px; border-radius: 18px 18px 18px 4px; 
            display: inline-block; max-width: 85%; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        
        .examples { 
            background: white; padding: 25px; border-bottom: 1px solid #e0e0e0;
        }
        .examples h3 { margin-top: 0; color: #1976d2; font-weight: 500; }
        .example-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 10px; }
        .example-query { 
            background: #f8f9fa; padding: 12px 16px; border-radius: 8px; 
            cursor: pointer; border: 1px solid #e9ecef; transition: all 0.2s;
            font-size: 14px;
        }
        .example-query:hover { 
            background: #e3f2fd; border-color: #1976d2; transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(25,118,210,0.15);
        }
        
        .input-section { padding: 25px; background: white; }
        .input-container { display: flex; gap: 12px; margin-bottom: 20px; }
        .input-container input { 
            flex: 1; padding: 16px; border: 2px solid #e0e0e0; border-radius: 12px; 
            font-size: 16px; transition: border-color 0.2s;
        }
        .input-container input:focus { 
            outline: none; border-color: #1976d2; box-shadow: 0 0 0 3px rgba(25,118,210,0.1);
        }
        .input-container button { 
            padding: 16px 32px; background: linear-gradient(135deg, #1976d2, #1565c0); 
            color: white; border: none; border-radius: 12px; cursor: pointer; 
            font-size: 16px; font-weight: 500; transition: all 0.2s;
        }
        .input-container button:hover { 
            transform: translateY(-1px); box-shadow: 0 8px 20px rgba(25,118,210,0.3);
        }
        
        .results { margin-top: 20px; background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .results h3 { 
            padding: 20px 25px; margin: 0; background: #1976d2; color: white; 
            border-radius: 12px 12px 0 0; font-weight: 500;
        }
        .school-card { 
            border-bottom: 1px solid #e9ecef; padding: 20px 25px; transition: background 0.2s;
        }
        .school-card:hover { background: #f8f9fa; }
        .school-card:last-child { border-bottom: none; border-radius: 0 0 12px 12px; }
        .school-name { font-weight: 600; color: #1976d2; font-size: 18px; margin-bottom: 5px; }
        .district-name { color: #666; margin-bottom: 15px; font-size: 14px; }
        
        .status-badge { 
            padding: 4px 10px; border-radius: 6px; color: white; font-size: 12px; 
            margin: 3px; display: inline-block; font-weight: 500;
        }
        .Red { background: linear-gradient(135deg, #d32f2f, #c62828); }
        .Orange { background: linear-gradient(135deg, #f57c00, #ef6c00); }
        .Yellow { background: linear-gradient(135deg, #fbc02d, #f9a825); color: #333; }
        .Green { background: linear-gradient(135deg, #388e3c, #2e7d32); }
        .Blue { background: linear-gradient(135deg, #1976d2, #1565c0); }
        
        .student-group { 
            margin-top: 15px; padding: 12px; background: #f8f9fa; 
            border-radius: 8px; border-left: 4px solid #1976d2;
        }
        .student-group-name { font-weight: 600; color: #1976d2; margin-bottom: 8px; font-size: 14px; }
        
        .performance-section { margin-top: 10px; }
        .performance-label { font-weight: 600; font-size: 14px; margin-bottom: 8px; color: #333; }
        
        @media (max-width: 768px) {
            body { padding: 10px; }
            .header h1 { font-size: 1.8em; }
            .input-container { flex-direction: column; }
            .example-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏫 California Schools AI Dashboard</h1>
            <p>Technical analysis of CA Dashboard data with student group breakdowns</p>
        </div>
        
        <div class="examples">
            <h3>💡 Try These Example Queries:</h3>
            <div class="example-grid">
                <div class="example-query" onclick="setQuery(this.textContent)">What are the red and orange areas for Sunnyvale School District?</div>
                <div class="example-query" onclick="setQuery(this.textContent)">Which student groups are struggling with math in San Miguel Elementary?</div>
                <div class="example-query" onclick="setQuery(this.textContent)">Show me chronic absenteeism issues for Hispanic students</div>
                <div class="example-query" onclick="setQuery(this.textContent)">Long-term English learners needing support in Fresno</div>
<div class="example-query" onclick="setQuery(this.textContent)">Which schools are preparing students for post-secondary success?</div>
<div class="example-query" onclick="setQuery(this.textContent)">Suspension rates for students with disabilities</div>
            </div>
        </div>
        
        <div class="chat-container" id="chatContainer">
            <div class="message ai-message">
                <span>👋 Hi! I can help you explore California school dashboard data with detailed student group breakdowns. I understand Distance from Standard (DFS), chronic absenteeism rates, English learner progress, and all the technical nuances of CA Dashboard indicators. Ask me anything!</span>
            </div>
        </div>
        
        <div class="input-section">
            <div class="input-container">
                <input type="text" id="queryInput" placeholder="Ask about CA school performance by student groups..." onkeypress="if(event.key==='Enter') sendQuery()">
              <button onclick="sendQuery()">Ask</button>
           </div>
       </div>
   </div>
   
   <div class="results" id="results"></div>

   <script>
       function setQuery(text) {
           document.getElementById('queryInput').value = text;
       }
       
       async function sendQuery() {
           const input = document.getElementById('queryInput');
           const query = input.value.trim();
           if (!query) return;
           
           // Add user message
           addMessage(query, 'user');
           input.value = '';
           
           // Add loading message
           addMessage('🤔 Analyzing your question with CA Dashboard technical knowledge...', 'ai');
           
           try {
               const response = await fetch('/query', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({query: query})
               });
               
               const data = await response.json();
               
               // Remove loading message
               document.querySelector('#chatContainer .message:last-child').remove();
               
               // Add AI response
               addMessage(data.response, 'ai');
               
               // Show detailed results
               showResults(data.schools);
               
           } catch (error) {
               document.querySelector('#chatContainer .message:last-child').remove();
               addMessage('❌ Sorry, something went wrong. Please try again.', 'ai');
           }
       }
       
       function addMessage(text, sender) {
           const container = document.getElementById('chatContainer');
           const message = document.createElement('div');
           message.className = `message ${sender}-message`;
           message.innerHTML = `<span>${text}</span>`;
           container.appendChild(message);
           container.scrollTop = container.scrollHeight;
       }
       
       function showResults(schools) {
           const resultsDiv = document.getElementById('results');
           if (!schools || schools.length === 0) {
               resultsDiv.innerHTML = '';
               return;
           }
           
           let html = `<h3>📊 Detailed Results (${schools.length} schools)</h3>`;
           
           schools.slice(0, 15).forEach(school => {
               const overallIndicators = school.dashboard_indicators || {};
               const studentGroups = school.student_groups || {};
               
               // Overall performance badges
               let overallBadges = '';
               Object.keys(overallIndicators).forEach(indicator => {
                   const data = overallIndicators[indicator];
                   if (data && data.status && data.status !== 'Unknown') {
                       const label = formatIndicatorLabel(indicator);
                       const value = data.rate || data.points_below_standard || 0;
                       const tooltip = formatTooltip(indicator, data.status, value);
                       overallBadges += `<span class="status-badge ${data.status}" title="${tooltip}">${label}: ${data.status}</span>`;
                   }
               });
               
               // Student groups with issues
               let studentGroupsHtml = '';
               Object.keys(studentGroups).forEach(groupCode => {
                   if (groupCode !== 'ALL') {
                       const groupData = studentGroups[groupCode];
                       const groupName = getGroupName(groupCode, groupData);
                       
                       let groupBadges = '';
                       let hasIssues = false;
                       
                       Object.keys(groupData).forEach(indicator => {
                           const data = groupData[indicator];
                           if (data && data.status && ['Red', 'Orange'].includes(data.status)) {
                               const label = formatIndicatorLabel(indicator);
                               const value = data.rate || data.points_below_standard || 0;
                               const tooltip = formatTooltip(indicator, data.status, value);
                               groupBadges += `<span class="status-badge ${data.status}" title="${tooltip}">${label}: ${data.status}</span>`;
                               hasIssues = true;
                           }
                       });
                       
                       if (hasIssues) {
                           studentGroupsHtml += `
                               <div class="student-group">
                                   <div class="student-group-name">${groupName}</div>
                                   ${groupBadges}
                               </div>
                           `;
                       }
                   }
               });
               
               html += `
                   <div class="school-card">
                       <div class="school-name">${school.school_name}</div>
                       <div class="district-name">${school.district_name}</div>
                       <div class="performance-section">
                           <div class="performance-label">Overall Performance:</div>
                           ${overallBadges || '<span style="color: #666; font-style: italic;">No data available</span>'}
                       </div>
                       ${studentGroupsHtml}
                   </div>
               `;
           });
           
           if (schools.length > 15) {
               html += `
                   <div class="school-card" style="text-align: center; color: #666; font-style: italic;">
                       ... and ${schools.length - 15} more schools. Refine your search for more specific results.
                   </div>
               `;
           }
           
           resultsDiv.innerHTML = html;
       }
       
       function formatIndicatorLabel(indicator) {
    const labels = {
        'chronic_absenteeism': 'Chronic Absences',
        'ela_performance': 'ELA',
        'math_performance': 'Math',
        'english_learner_progress': 'EL Progress',
        'suspension_rate': 'Suspensions',
        'college_career': 'College/Career'  // NEW
    };
    return labels[indicator] || indicator.replace('_', ' ').toUpperCase();
}

function formatTooltip(indicator, status, value) {
    if (indicator === 'chronic_absenteeism') {
        return `${value.toFixed(1)}% of students chronically absent (≥10% days missed)`;
    } else if (indicator === 'suspension_rate') {
        return `${value.toFixed(1)}% of students suspended (≥1 full day aggregate)`;
    } else if (indicator === 'college_career') {  // NEW
        return `${value.toFixed(1)}% of graduates college/career prepared`;
    } else if (indicator.includes('performance')) {
        const subject = indicator.includes('ela') ? 'ELA' : 'Math';
        if (value >= 0) {
            return `${value.toFixed(1)} points above ${subject} standard`;
        } else {
            return `${Math.abs(value).toFixed(1)} points below ${subject} standard`;
        }
    } else if (indicator === 'english_learner_progress') {
        return `${value.toFixed(1)}% of English learners making progress toward proficiency`;
    }
    return `${status} performance level`;
}
       
       function getGroupName(groupCode, groupData) {
           // Try to get name from data first
           for (let indicator in groupData) {
               if (groupData[indicator] && groupData[indicator].student_group_name) {
                   return groupData[indicator].student_group_name;
               }
           }
           
           // Fallback to code mapping
           const groupNames = {
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
               'SED': 'Socioeconomically Disadvantaged',
               'SWD': 'Students with Disabilities',
               'HOM': 'Homeless',
               'FOS': 'Foster Youth'
           };
           return groupNames[groupCode] || groupCode;
       }
   </script>
</body>
</html>
'''

@app.route('/')
def index():
   return render_template_string(HTML_TEMPLATE)

@app.route('/query', methods=['POST'])
def handle_query():
    try:
        user_query = request.json['query']
        
        # Use AI-powered parsing
        parsed_query = parse_query_with_real_ai(user_query)
        
        # Build MongoDB query (keep your existing function)
        mongo_query = build_mongodb_query(parsed_query)
        
        # Execute query
        results = list(schools_collection.find(mongo_query, {"_id": 0}).limit(50))
        
        # Generate intelligent response
        ai_response = generate_intelligent_response(user_query, results, parsed_query)
        
        return jsonify({
            'response': ai_response,
            'schools': results,
            'parsed_query': parsed_query,
            'query_used': str(mongo_query)
        })
        
    except Exception as e:
        print(f"Error details: {e}")
        return jsonify({
            'response': f'Sorry, I encountered an error: {str(e)}',
            'schools': [],
            'query_used': {}
        }), 500

@app.route('/test-ai')
def test_ai():
    """Test if Vertex AI is working"""
    if not AI_ENABLED:
        return jsonify({"error": "AI is not enabled", "ai_enabled": AI_ENABLED})
    
    try:
        # Simple test prompt
        test_prompt = "Respond with exactly: 'AI is working correctly'"
        response = model.generate_content(test_prompt)
        return jsonify({
            "ai_enabled": AI_ENABLED,
            "test_response": response.text.strip(),
            "status": "AI is working" if response else "AI failed"
        })
    except Exception as e:
        return jsonify({
            "ai_enabled": AI_ENABLED,
            "error": str(e),
            "status": "AI failed"
        })


    """Debug the query parsing process step by step"""
    try:
        user_query = request.json['query']
        
        # Test AI parsing first
        ai_result = None
        ai_error = None
        
        if AI_ENABLED:
            try:
                ai_result = analyze_query_with_gemini(user_query)
            except Exception as e:
                ai_error = str(e)
        
        # Test pattern parsing
        pattern_result = parse_query_with_patterns(user_query)
        
        # Test MongoDB query building
        mongo_query = build_mongodb_query(pattern_result)
        
        # Test MongoDB results
        results = list(schools_collection.find(mongo_query, {"_id": 0}).limit(5))
        
        return jsonify({
            "user_query": user_query,
            "ai_enabled": AI_ENABLED,
            "ai_parsing": {
                "result": ai_result,
                "error": ai_error,
                "used": ai_result is not None
            },
            "pattern_parsing": pattern_result,
            "mongo_query": str(mongo_query),
            "results_count": len(results),
            "sample_results": results[:2] if results else [],
            "debug_info": {
                "district_search": pattern_result.get("district_name"),
                "colors_requested": pattern_result.get("colors"),
                "indicators_requested": pattern_result.get("indicators")
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})
    """Debug the query parsing process step by step"""
    try:
        user_query = request.json['query']
        
        # Test AI parsing first
        ai_result = None
        ai_error = None
        
        if AI_ENABLED:
            try:
                ai_result = analyze_query_with_gemini(user_query)
            except Exception as e:
                ai_error = str(e)
        
        # Test pattern parsing
        pattern_result = parse_query_with_patterns(user_query)
        
        # Test MongoDB query building
        mongo_query = build_mongodb_query(pattern_result)
        
        # Test MongoDB results
        results = list(schools_collection.find(mongo_query, {"_id": 0}).limit(5))
        
        return jsonify({
            "user_query": user_query,
            "ai_enabled": AI_ENABLED,
            "ai_parsing": {
                "result": ai_result,
                "error": ai_error,
                "used": ai_result is not None
            },
            "pattern_parsing": pattern_result,
            "mongo_query": str(mongo_query),
            "results_count": len(results),
            "sample_results": results[:2] if results else [],
            "debug_info": {
                "district_search": pattern_result.get("district_name"),
                "colors_requested": pattern_result.get("colors"),
                "indicators_requested": pattern_result.get("indicators")
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/check-sunnyvale-data')
def check_sunnyvale_data():
    """Check what Sunnyvale data actually exists"""
    try:
        # Find all Sunnyvale schools
        all_sunnyvale = list(schools_collection.find(
            {"district_name": {"$regex": "sunnyvale", "$options": "i"}},
            {"school_name": 1, "district_name": 1, "dashboard_indicators": 1, "_id": 0}
        ))
        
        # Find schools with Red indicators
        red_chronic = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.chronic_absenteeism.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.chronic_absenteeism": 1, "_id": 0}
        ))
        
        red_ela = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.ela_performance.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.ela_performance": 1, "_id": 0}
        ))
        
        red_math = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.math_performance.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.math_performance": 1, "_id": 0}
        ))
        
        # Check student groups with Red status
        red_student_groups = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "$or": [
                    {"student_groups.HI.chronic_absenteeism.status": "Red"},
                    {"student_groups.HI.ela_performance.status": "Red"},
                    {"student_groups.HI.math_performance.status": "Red"},
                    {"student_groups.EL.chronic_absenteeism.status": "Red"},
                    {"student_groups.EL.ela_performance.status": "Red"},
                    {"student_groups.EL.math_performance.status": "Red"},
                    {"student_groups.SWD.chronic_absenteeism.status": "Red"},
                    {"student_groups.SWD.ela_performance.status": "Red"},
                    {"student_groups.SWD.math_performance.status": "Red"}
                ]
            },
            {"school_name": 1, "student_groups": 1, "_id": 0}
        ))
        
        return jsonify({
            "total_sunnyvale_schools": len(all_sunnyvale),
            "sunnyvale_schools": [s["school_name"] for s in all_sunnyvale],
            "red_overall_indicators": {
                "chronic_absenteeism": len(red_chronic),
                "ela_performance": len(red_ela),
                "math_performance": len(red_math)
            },
            "red_overall_details": {
                "chronic_schools": [s["school_name"] for s in red_chronic],
                "ela_schools": [s["school_name"] for s in red_ela],
                "math_schools": [s["school_name"] for s in red_math]
            },
            "red_student_groups_count": len(red_student_groups),
            "sample_red_student_data": red_student_groups[:2] if red_student_groups else []
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})



@app.route('/debug-data')
def debug_data():
    try:
        # Find Sunnyvale schools
        sunnyvale_schools = list(schools_collection.find(
            {"district_name": {"$regex": "sunnyvale", "$options": "i"}},
            {"school_name": 1, "district_name": 1, "student_groups": 1, "_id": 0}
        ).limit(5))
        
        # Check what indicators exist
        sample_school = schools_collection.find_one(
            {"student_groups": {"$exists": True}},
            {"student_groups": 1, "dashboard_indicators": 1, "_id": 0}
        )
        
        return jsonify({
            "sunnyvale_schools": sunnyvale_schools,
            "sample_indicators": list(sample_school.get("dashboard_indicators", {}).keys()) if sample_school else [],
            "sample_student_groups": list(sample_school.get("student_groups", {}).keys()) if sample_school else []
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# Debug and utility routes
@app.route('/test-new-structure')
def test_new_structure():
   try:
       sample_school = schools_collection.find_one(
           {"student_groups": {"$exists": True}},
           {"_id": 0}
       )
       
       if sample_school:
           return jsonify({
               "school_name": sample_school.get("school_name"),
               "district_name": sample_school.get("district_name"),
               "student_groups_available": list(sample_school.get("student_groups", {}).keys()),
               "sample_data": sample_school
           })
       else:
           return jsonify({"error": "No schools with student groups found"})
           
   except Exception as e:
       return jsonify({"error": str(e)})

@app.route('/db-stats')
def db_stats():
   try:
       total_count = schools_collection.count_documents({})
       
       districts_sample = list(schools_collection.find({}, {"district_name": 1, "_id": 0}).limit(20))
       
       pipeline = [
           {"$group": {"_id": "$district_name", "count": {"$sum": 1}}},
           {"$sort": {"count": -1}},
           {"$limit": 10}
       ]
       top_districts = list(schools_collection.aggregate(pipeline))
       
       # Sample indicators analysis
       indicators_sample = list(schools_collection.aggregate([
           {"$limit": 1000},
           {"$group": {
               "_id": None,
               "chronic_red": {"$sum": {"$cond": [{"$eq": ["$dashboard_indicators.chronic_absenteeism.status", "Red"]}, 1, 0]}},
               "ela_red": {"$sum": {"$cond": [{"$eq": ["$dashboard_indicators.ela_performance.status", "Red"]}, 1, 0]}},
               "math_red": {"$sum": {"$cond": [{"$eq": ["$dashboard_indicators.math_performance.status", "Red"]}, 1, 0]}}
           }}
       ]))
       
       return jsonify({
           "total_schools": total_count,
           "districts_sample": [d.get("district_name") for d in districts_sample],
           "top_districts": top_districts,
           "red_indicators_sample": indicators_sample[0] if indicators_sample else {},
           "system_status": "✅ CA Dashboard Technical Knowledge Integrated"
       })
   except Exception as e:
       return jsonify({"error": str(e)})

@app.route('/health')
def health_check():
   return jsonify({
       "status": "healthy",
       "mongodb_connected": True,
       "ai_enabled": AI_ENABLED,
       "version": "2.0 - CA Dashboard Expert"
   })

# REPLACE your check-red-data-sunnyvale route with this fixed version:

@app.route('/check-red-data-sunnyvale')
def check_red_data_sunnyvale():
    """Check what Red data actually exists in Sunnyvale"""
    try:
        # Find all Sunnyvale schools (exclude _id to avoid ObjectId issues)
        all_sunnyvale = list(schools_collection.find(
            {"district_name": {"$regex": "sunnyvale", "$options": "i"}},
            {"school_name": 1, "district_name": 1, "dashboard_indicators": 1, "_id": 0}
        ))
        
        # Find schools with Red indicators at overall level
        red_chronic = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.chronic_absenteeism.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.chronic_absenteeism": 1, "_id": 0}
        ))
        
        red_ela = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.ela_performance.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.ela_performance": 1, "_id": 0}
        ))
        
        red_math = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.math_performance.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.math_performance": 1, "_id": 0}
        ))
        
        # Check student groups with Red status - simplified query
        red_student_groups_query = {
            "district_name": {"$regex": "sunnyvale", "$options": "i"},
            "$or": [
                {"student_groups.HI.chronic_absenteeism.status": "Red"},
                {"student_groups.HI.ela_performance.status": "Red"},
                {"student_groups.HI.math_performance.status": "Red"},
                {"student_groups.EL.chronic_absenteeism.status": "Red"},
                {"student_groups.EL.ela_performance.status": "Red"},
                {"student_groups.EL.math_performance.status": "Red"},
                {"student_groups.SWD.chronic_absenteeism.status": "Red"},
                {"student_groups.SWD.ela_performance.status": "Red"},
                {"student_groups.SWD.math_performance.status": "Red"},
                {"student_groups.LTEL.chronic_absenteeism.status": "Red"},
                {"student_groups.LTEL.ela_performance.status": "Red"},
                {"student_groups.LTEL.math_performance.status": "Red"}
            ]
        }
        
        red_student_groups_count = schools_collection.count_documents(red_student_groups_query)
        
        # Get sample of schools with student group Red indicators
        red_student_groups_sample = list(schools_collection.find(
            red_student_groups_query,
            {"school_name": 1, "district_name": 1, "_id": 0}
        ).limit(3))
        
        # Get performance level distribution
        performance_distribution = {}
        for school in all_sunnyvale:
            indicators = school.get("dashboard_indicators", {})
            for indicator_name, indicator_data in indicators.items():
                if isinstance(indicator_data, dict):
                    status = indicator_data.get("status", "Unknown")
                    if indicator_name not in performance_distribution:
                        performance_distribution[indicator_name] = {}
                    if status not in performance_distribution[indicator_name]:
                        performance_distribution[indicator_name][status] = 0
                    performance_distribution[indicator_name][status] += 1
        
        return jsonify({
            "total_sunnyvale_schools": len(all_sunnyvale),
            "school_names": [s.get("school_name", "Unknown") for s in all_sunnyvale],
            "red_overall_indicators": {
                "chronic_absenteeism_red_count": len(red_chronic),
                "ela_performance_red_count": len(red_ela),
                "math_performance_red_count": len(red_math),
                "total_red_overall": len(red_chronic) + len(red_ela) + len(red_math)
            },
            "red_student_groups": {
                "schools_with_red_student_groups": red_student_groups_count,
                "sample_schools": red_student_groups_sample
            },
            "performance_distribution": performance_distribution,
            "analysis": {
                "has_red_overall": (len(red_chronic) + len(red_ela) + len(red_math)) > 0,
                "has_red_student_groups": red_student_groups_count > 0,
                "conclusion": "Red indicators found in student groups" if red_student_groups_count > 0 else "No Red indicators found anywhere"
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e), "error_type": type(e).__name__})

@app.route('/debug-query-step-by-step', methods=['POST'])
def debug_query_step_by_step():
    """Debug the query parsing process step by step"""
    try:
        user_query = request.json['query']
        
        # Test AI parsing first
        ai_result = None
        ai_error = None
        
        if AI_ENABLED:
            try:
                ai_result = analyze_query_with_gemini(user_query)
            except Exception as e:
                ai_error = str(e)
        
        # Test pattern parsing
        pattern_result = parse_query_with_patterns(user_query)
        
        # Determine which parsing was used
        final_parsed = ai_result if ai_result else pattern_result
        
        # Test MongoDB query building
        mongo_query = build_mongodb_query(final_parsed)
        
        # Test MongoDB results
        results = list(schools_collection.find(mongo_query, {"_id": 0}).limit(5))
        
        return jsonify({
            "user_query": user_query,
            "ai_enabled": AI_ENABLED,
            "parsing_used": "AI" if ai_result else "Pattern Matching",
            "ai_parsing": {
                "result": ai_result,
                "error": ai_error,
                "worked": ai_result is not None
            },
            "pattern_parsing": pattern_result,
            "final_parsed_query": final_parsed,
            "mongo_query": str(mongo_query),
            "results_count": len(results),
            "sample_results": results[:2] if results else [],
            "debug_info": {
                "district_search": final_parsed.get("district_name"),
                "colors_requested": final_parsed.get("colors"),
                "indicators_requested": final_parsed.get("indicators"),
                "student_groups": final_parsed.get("student_groups"),
                "data_availability": final_parsed.get("data_availability")
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})


    """Check what Red data actually exists in Sunnyvale"""
    try:
        # Find all Sunnyvale schools
        all_sunnyvale = list(schools_collection.find(
            {"district_name": {"$regex": "sunnyvale", "$options": "i"}},
            {"school_name": 1, "district_name": 1, "dashboard_indicators": 1, "_id": 0}
        ))
        
        # Find schools with Red indicators at overall level
        red_chronic = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.chronic_absenteeism.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.chronic_absenteeism": 1, "_id": 0}
        ))
        
        red_ela = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.ela_performance.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.ela_performance": 1, "_id": 0}
        ))
        
        red_math = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "dashboard_indicators.math_performance.status": "Red"
            },
            {"school_name": 1, "dashboard_indicators.math_performance": 1, "_id": 0}
        ))
        
        # Check student groups with Red status (this is where Red might actually be)
        red_student_groups = list(schools_collection.find(
            {
                "district_name": {"$regex": "sunnyvale", "$options": "i"},
                "$or": [
                    {"student_groups.HI.chronic_absenteeism.status": "Red"},
                    {"student_groups.HI.ela_performance.status": "Red"},
                    {"student_groups.HI.math_performance.status": "Red"},
                    {"student_groups.EL.chronic_absenteeism.status": "Red"},
                    {"student_groups.EL.ela_performance.status": "Red"},
                    {"student_groups.EL.math_performance.status": "Red"},
                    {"student_groups.SWD.chronic_absenteeism.status": "Red"},
                    {"student_groups.SWD.ela_performance.status": "Red"},
                    {"student_groups.SWD.math_performance.status": "Red"},
                    {"student_groups.LTEL.chronic_absenteeism.status": "Red"},
                    {"student_groups.LTEL.ela_performance.status": "Red"},
                    {"student_groups.LTEL.math_performance.status": "Red"}
                ]
            },
            {"school_name": 1, "student_groups": 1, "_id": 0}
        ))
        
        # Get a sample of all performance levels to see what exists
        all_performance_levels = list(schools_collection.aggregate([
            {"$match": {"district_name": {"$regex": "sunnyvale", "$options": "i"}}},
            {"$project": {
                "school_name": 1,
                "chronic_status": "$dashboard_indicators.chronic_absenteeism.status",
                "ela_status": "$dashboard_indicators.ela_performance.status", 
                "math_status": "$dashboard_indicators.math_performance.status"
            }}
        ]))
        
        return jsonify({
            "total_sunnyvale_schools": len(all_sunnyvale),
            "sunnyvale_schools": [s["school_name"] for s in all_sunnyvale],
            "red_overall_indicators": {
                "chronic_absenteeism_red_count": len(red_chronic),
                "ela_performance_red_count": len(red_ela),
                "math_performance_red_count": len(red_math)
            },
            "red_overall_details": {
                "chronic_schools": [s["school_name"] for s in red_chronic],
                "ela_schools": [s["school_name"] for s in red_ela],
                "math_schools": [s["school_name"] for s in red_math]
            },
            "red_student_groups_count": len(red_student_groups),
            "sample_red_student_data": red_student_groups[:2] if red_student_groups else [],
            "all_performance_levels_sample": all_performance_levels[:5],
            "conclusion": "Red indicators exist in student groups" if red_student_groups else "No Red indicators found at any level"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})
@app.route('/test-query-simple')
def test_query_simple():
    """Simple form to test queries in browser"""
    return '''
    <html>
    <body>
        <h2>Test Query Debug</h2>
        <form>
            <input type="text" id="query" placeholder="Enter your query..." style="width: 500px; padding: 10px;">
            <button type="button" onclick="testQuery()" style="padding: 10px;">Test Query</button>
        </form>
        <pre id="result" style="background: #f5f5f5; padding: 20px; margin-top: 20px;"></pre>
        
        <script>
        async function testQuery() {
            const query = document.getElementById('query').value;
            const response = await fetch('/debug-query-step-by-step', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({query: query})
            });
            const data = await response.json();
            document.getElementById('result').textContent = JSON.stringify(data, null, 2);
        }
        </script>
    </body>
    </html>
    '''


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)