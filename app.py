from flask import Flask, request, jsonify, render_template_string
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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
# Rate limiting to prevent abuse  
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"]
)
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
    # This model name might need to be adjusted based on availability
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

AVAILABLE DATA INDICATORS (all 7 indicators in the database):
1. chronic_absenteeism - Percentage of students absent 10%+ of school days
2. ela_performance - ELA test scores (Distance from Standard - negative = below, positive = above)  
3. math_performance - Math test scores (Distance from Standard - negative = below, positive = above)
4. suspension_rate - Percentage of students suspended
5. college_career - College/Career Indicator (CCI) - percentage prepared for college/career
6. graduation_rate - Percentage of students graduating
7. english_learner_progress - English Learner Progress Indicator (ELPI) - progress of English learners

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
        
        # Add these lines after the existing math_performance check:
    if any(word in query_lower for word in ["suspension", "discipline", "suspended"]):
        parsed["indicators"].append("suspension_rate")

    if any(word in query_lower for word in ["college", "career", "cci", "prepared"]):
        parsed["indicators"].append("college_career")

    if any(word in query_lower for word in ["graduation", "graduate", "graduating"]):
        parsed["indicators"].append("graduation_rate")

    if any(word in query_lower for word in ["english learner progress", "elpi", "elpac", "el progress"]):
        parsed["indicators"].append("english_learner_progress")
    
    
    # Context-based color inference
    problem_phrases = ["lowest", "worst", "struggling", "red", "problem", "concerning"]
    if any(phrase in query_lower for phrase in problem_phrases):
        if not parsed["colors"]:
            parsed["colors"] = ["Red", "Orange"]
    
    return parsed

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
                    for indicator in ["chronic_absenteeism", "ela_performance", "math_performance", "suspension_rate", "college_career", "graduation_rate", "english_learner_progress"]:
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
                for indicator in ["chronic_absenteeism", "ela_performance", "math_performance", "suspension_rate", "college_career", "graduation_rate", "english_learner_progress"]:
                    condition = {f"dashboard_indicators.{indicator}.status": {"$in": colors}}
                    color_conditions.append(condition)
                    print(f"DEBUG - Added overall condition: {condition}")
        
        if color_conditions:
            query_filter["$or"] = color_conditions
            print(f"DEBUG - Final $or conditions: {len(color_conditions)} conditions")

    elif parsed_query.get("indicators"):
        # NEW: Handle case where indicators are specified but no colors
        print("DEBUG - No colors specified, but indicators found - showing all schools with these indicators")
        indicator_conditions = []
        
        if parsed_query.get("student_groups"):
            # Look for indicators in specific student groups
            for student_group in parsed_query["student_groups"]:
                for indicator in parsed_query["indicators"]:
                    condition = {f"student_groups.{student_group}.{indicator}": {"$exists": True}}
                    indicator_conditions.append(condition)
                    print(f"DEBUG - Added student group existence condition: {condition}")
        else:
            # Look for indicators in overall dashboard
            for indicator in parsed_query["indicators"]:
                if indicator == "english_learner_progress":
                    # ELPI data is only in the EL student group, not dashboard_indicators
                    condition = {f"student_groups.EL.{indicator}": {"$exists": True}}
                    indicator_conditions.append(condition)
                    print(f"DEBUG - Added EL group existence condition: {condition}")
                else:
                    condition = {f"dashboard_indicators.{indicator}": {"$exists": True}}
                    indicator_conditions.append(condition)
                    print(f"DEBUG - Added dashboard existence condition: {condition}")

        
        if indicator_conditions:
            if len(indicator_conditions) == 1:
                query_filter.update(indicator_conditions[0])
            else:
                query_filter["$or"] = indicator_conditions
            print(f"DEBUG - Added indicator existence filters: {len(indicator_conditions)} conditions")

    print(f"DEBUG - Final MongoDB query: {query_filter}")
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

def generate_ai_analysis(user_query: str, results: List[Dict], parsed_query: Dict) -> str:
    """Use Gemini to generate concise, fact-focused analysis"""
    
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
You are a California School Dashboard data analyst. Provide a CONCISE, FACT-BASED analysis with NO implementation suggestions.

USER QUERY: {user_query}
SCHOOL DATA: {json.dumps(data_summary, indent=2)}

DATA CONTEXT:
- chronic_absenteeism: % of students absent 10%+ days (lower is better)
- ela_performance: Points above/below standard (higher is better)  
- math_performance: Points above/below standard (higher is better)
- Performance levels: Red (worst) → Orange → Yellow → Green → Blue (best)

RESPONSE REQUIREMENTS:
1. Start with a clear summary sentence
2. Present key findings as concise bullet points
3. Include specific data values and school names
4. Focus ONLY on data analysis and patterns
5. NO suggestions for actions or interventions
6. NO recommendations for implementation
7. Keep total response under 200 words
8. Use clear formatting with headers and bullets

Format your response with proper markdown formatting but be concise and factual only.
"""

    try:
        response = model.generate_content(analysis_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"AI analysis failed: {e}")
        return None

def generate_template_response(user_query: str, results: List[Dict], parsed_query: Dict) -> str:
    """Generate concise template-based response (fallback)"""
    
    if len(results) == 1:
        # Single school analysis
        school = results[0]
        school_name = school.get("school_name", "District Overall")
        district_name = school.get("district_name", "Unknown District")
        
        response_parts = [f"**{school_name}** ({district_name})"]
        
        # Show overall performance
        overall_indicators = school.get("dashboard_indicators", {})
        if overall_indicators:
            performance_items = []
            for indicator, data in overall_indicators.items():
                if isinstance(data, dict) and data.get("status") != "No Data":
                    status = data.get("status", "Unknown")
                    value = data.get("rate", data.get("points_below_standard", 0))
                    
                    if indicator == "chronic_absenteeism":
                        performance_items.append(f"Chronic Absenteeism: **{status}** ({value:.1f}%)")
                    elif indicator == "ela_performance":
                        direction = "above" if value >= 0 else "below"
                        performance_items.append(f"ELA: **{status}** ({abs(value):.1f} pts {direction} standard)")
                    elif indicator == "math_performance":
                        direction = "above" if value >= 0 else "below"
                        performance_items.append(f"Math: **{status}** ({abs(value):.1f} pts {direction} standard)")
                    elif indicator == "english_learner_progress":
                        performance_items.append(f"English Learner Progress: **{status}** ({value:.1f}%)")
                    elif indicator == "suspension_rate":
                        performance_items.append(f"Suspension Rate: **{status}** ({value:.1f}%)")
                    elif indicator == "college_career":
                        performance_items.append(f"College/Career Ready: **{status}** ({value:.1f}%)")
                    elif indicator == "graduation_rate":
                        performance_items.append(f"Graduation Rate: **{status}** ({value:.1f}%)")
            if performance_items:
                response_parts.append("\n**Overall Performance:**")
                for item in performance_items:
                    response_parts.append(f"• {item}")
        
        return "\n".join(response_parts)
    else:
        # Multiple schools summary
        problem_schools = []
        for school in results[:10]:
            school_name = school.get("school_name", "Unknown")
            indicators = school.get("dashboard_indicators", {})
            
            red_orange_indicators = []
            for indicator, data in indicators.items():
                if isinstance(data, dict) and data.get("status") in ["Red", "Orange"]:
                    red_orange_indicators.append(f"{data.get('status')} {indicator.replace('_', ' ').title()}")
            
            if red_orange_indicators:
                problem_schools.append(f"**{school_name}**: {', '.join(red_orange_indicators)}")
        
        response_parts = [f"**Found {len(results)} schools** with performance concerns:"]
        
        if problem_schools:
            response_parts.extend(problem_schools[:11])  # Limit to 8 schools
            if len(results) > 8:
                response_parts.append(f"*...and {len(results) - 8} more schools*")
        
        return "\n".join(response_parts)

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

# ==============================================================================
# ===                           HTML TEMPLATE - TABBED VERSION              ===
# ==============================================================================

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
            background: #f0f2f5;
            min-height: 100vh;
        }
        .container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.08);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: calc(100vh - 40px);
        }
        .header { 
            text-align: center; 
            color: white; 
            padding: 20px; 
            background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
            flex-shrink: 0;
        }
        .header h1 { margin: 0 0 5px 0; font-size: 1.8em; font-weight: 500; }
        .header p { margin: 0; opacity: 0.9; font-size: 1em; }
        
        /* Tab Navigation */
        .tab-navigation {
            background: #f8f9fa;
            border-bottom: 1px solid #e8e8e8;
            padding: 0;
            flex-shrink: 0;
        }
        .tab-buttons {
            display: flex;
            margin: 0;
            padding: 0;
        }
        .tab-button {
            background: none;
            border: none;
            padding: 15px 20px;
            cursor: pointer;
            font-size: 15px;
            font-weight: 500;
            color: #666;
            border-bottom: 3px solid transparent;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .tab-button:hover {
            background: #e9ecef;
            color: #333;
        }
        .tab-button.active {
            color: #1976d2;
            border-bottom-color: #1976d2;
            background: white;
        }
        .tab-badge {
            background: #1976d2;
            color: white;
            border-radius: 12px;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: 600;
            min-width: 20px;
            text-align: center;
        }
        .tab-button:not(.active) .tab-badge {
            background: #6c757d;
        }

        /* Tab Content Area */
        .tab-content-area {
            flex-grow: 1;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .tab-content {
            flex-grow: 1;
            overflow-y: auto;
            padding: 25px;
            display: none;
        }
        .tab-content.active {
            display: flex;
            flex-direction: column;
        }

        /* Chat Tab Styles */
        .chat-container { 
            flex-grow: 1;
            overflow-y: auto;
        }
        .message { margin-bottom: 20px; display: flex; }
        .user-message { justify-content: flex-end; }
        .user-message span { 
            background: linear-gradient(135deg, #1976d2, #1565c0); 
            color: white; padding: 12px 16px; border-radius: 18px 18px 4px 18px; 
            max-width: 75%; box-shadow: 0 2px 8px rgba(25,118,210,0.3);
        }
        .ai-message { justify-content: flex-start; }
        .ai-message span { 
            background: #f0f2f5; border: 1px solid #e8e8e8; 
            padding: 12px 16px; border-radius: 18px 18px 18px 4px; 
            max-width: 85%;
            line-height: 1.5;
        }
        
        .examples { 
            background: #fafafa; padding: 20px; border-top: 1px solid #e8e8e8;
            margin-top: auto;
            flex-shrink: 0;
        }
        .examples h3 { margin: 0 0 10px 0; color: #333; font-weight: 500; font-size: 1em; }
        .example-grid { display: flex; flex-wrap: wrap; gap: 8px; }
        .example-query { 
            background: #e9ecef; color: #495057; padding: 8px 12px; border-radius: 16px; 
            cursor: pointer; border: 1px solid transparent; transition: all 0.2s;
            font-size: 13px;
        }
        .example-query:hover { 
            background: #e3f2fd; border-color: #1976d2; color: #1976d2;
        }

        /* Results Tab Styles */
        .results-content {
            flex-grow: 1;
            overflow-y: auto;
        }
        .results-header { 
            margin-bottom: 20px; 
            padding-bottom: 15px; 
            border-bottom: 1px solid #ddd;
        }
        .results-header h3 { 
            margin: 0; 
            font-weight: 500; 
            color: #333;
        }
        .performance-table table { width: 100%; border-collapse: collapse; font-size: 14px; }
        .performance-table th, .performance-table td { padding: 10px 12px; border: 1px solid #ddd; text-align: left; }
        .performance-table th { background-color: #f0f2f5; font-weight: 500; }
        .school-name-cell { font-weight: 500; }
        .color-cell { text-align: center; font-weight: 500; border-radius: 4px; padding: 6px; color: white; }
        .performance-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
}

.color-cell {
    text-align: center; 
    font-weight: 500; 
    border-radius: 4px; 
    padding: 6px 8px; 
    color: white;
    min-width: 70px;
    font-size: 13px;
}

.performance-value {
    font-size: 11px;
    font-weight: 500;
    text-align: center;
    min-height: 14px;
    line-height: 1.2;
}

.performance-above {
    color: #2e7d32; /* Green for above standard */
}

.performance-below {
    color: #d32f2f; /* Red for below standard */
}

.performance-rate {
    color: #1976d2; /* Blue for percentage rates */
}

.performance-na {
    color: #757575; /* Gray for no data */
}

.trend-info {
    font-size: 11px;
    font-weight: 500;
    text-align: center;
    min-height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* Fixed arrow colors */
.trend-good {
    color: #2e7d32 !important; /* Dark green for good changes */
}

.trend-bad {
    color: #c62828 !important; /* Dark red for bad changes */
}

.trend-stable {
    color: #757575 !important; /* Gray for no change */
}

/* Adjust table cell padding to accommodate three-line content */
.performance-table td {
    padding: 8px 6px;
    vertical-align: middle;
    min-width: 95px;
}

/* Make school name column wider since other columns are now wider */
.school-name-cell {
    font-weight: 500;
    min-width: 180px;
    max-width: 220px;
    word-wrap: break-word;
}

/* ADD these - they're completely new */
.filter-system {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    margin-bottom: 20px;
    overflow: hidden;
}

.filter-section {
    border-bottom: 1px solid #e9ecef;
}

.filter-section:last-child {
    border-bottom: none;
}

.filter-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: #ffffff;
    cursor: pointer;
    transition: background-color 0.2s;
    user-select: none;
}

.filter-header:hover {
    background: #f1f3f4;
}

.filter-title {
    font-weight: 600;
    color: #333;
    font-size: 14px;
}

.filter-arrow {
    color: #666;
    font-size: 12px;
    transition: transform 0.2s;
}

/* Color Filter Grid */
.color-filter-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
}

.color-filter-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    background: #fafafa;
}

.color-filter-item:hover {
    border-color: #1976d2;
    background: #f3f8ff;
}

.color-filter-item input[type="checkbox"] {
    margin: 0;
}

.color-sample {
    font-size: 16px;
    font-weight: 600;
    min-width: 60px;
}

.color-description {
    font-size: 12px;
    color: #666;
    flex-grow: 1;
}

/* Color sample styles */
.blue-sample { color: #1e88e5; }
.green-sample { color: #43a047; }
.yellow-sample { color: #fdd835; }
.orange-sample { color: #fb8c00; }
.red-sample { color: #e53935; }

/* Filter Action Buttons */
.color-filter-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    padding-top: 12px;
    border-top: 1px solid #f0f0f0;
}

.filter-action-btn {
    padding: 6px 12px;
    border: 1px solid #ddd;
    background: #fff;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    transition: all 0.2s;
}

.filter-action-btn:hover {
    background: #f0f2f5;
    border-color: #1976d2;
}

.problems-btn {
    background: #fff3e0;
    border-color: #fb8c00;
    color: #ef6c00;
}

.problems-btn:hover {
    background: #ffe0b2;
    border-color: #f57c00;
}

/* Responsive adjustments */
@media (max-width: 768px) {
    .color-filter-grid {
        grid-template-columns: 1fr;
    }
    
    .student-group-grid {
        grid-template-columns: 1fr;
    }
    
    .color-filter-actions {
        flex-direction: column;
    }
    
    .filter-action-btn {
        width: 100%;
        text-align: center;
    }
}
        /* Color styles */
        .color-cell.Blue { background-color: #1e88e5; }
        .color-cell.Green { background-color: #43a047; }
        .color-cell.Yellow { background-color: #fdd835; color: #333; }
        .color-cell.Orange { background-color: #fb8c00; }
        .color-cell.Red { background-color: #e53935; }
        .color-cell.No-Data { background-color: #bdbdbd; }
        .view-toggle { margin-bottom: 15px; }
        .view-toggle button { padding: 8px 12px; border: 1px solid #ccc; background: #fff; border-radius: 6px; cursor: pointer; }
        .view-toggle button.active { background: #1976d2; color: white; border-color: #1976d2; }
        .filter-content {
    padding: 16px;
    background: #ffffff;
    border-top: 1px solid #f0f0f0;
    display: block;
}

.filter-content.collapsed {
    display: none;
}

.student-group-selector { 
    margin-bottom: 15px; 
    font-size: 14px;
}
.student-group-selector > strong {
    display: block;
    margin-bottom: 8px;
    font-weight: 600;
}
.student-group-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 8px 15px;
    align-items: center;
}
.student-group-grid label {
    margin: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
}
        .results-footer { text-align: center; margin-top: 15px; color: #666; font-style: italic; font-size: 13px; }

        /* Empty States */
        .empty-state {
            text-align: center;
            color: #666;
            padding: 60px 20px;
            background: #fafafa;
            border-radius: 8px;
            margin: 20px 0;
        }
        .empty-state h3 {
            margin: 0 0 10px 0;
            color: #333;
        }
        .empty-state p {
            margin: 0;
            font-size: 14px;
        }
        
        /* Input Section - Always visible */
        .input-section { 
            padding: 15px 25px; 
            background: white; 
            border-top: 1px solid #e8e8e8;
            flex-shrink: 0;
        }
        .input-container { display: flex; gap: 12px; }
        .input-container input { 
            flex: 1; padding: 14px; border: 1px solid #ddd; border-radius: 8px; 
            font-size: 15px; transition: border-color 0.2s, box-shadow 0.2s;
        }
        .input-container input:focus { 
            outline: none; border-color: #1976d2; box-shadow: 0 0 0 3px rgba(25,118,210,0.2);
        }
        .input-container button { 
            padding: 14px 28px; background: #1976d2; 
            color: white; border: none; border-radius: 8px; cursor: pointer; 
            font-size: 15px; font-weight: 500; transition: background-color 0.2s;
        }
        .input-container button:hover { background-color: #1565c0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏫 California Schools AI Dashboard</h1>
            <p>Explore CA Dashboard data using natural language. Powered by MongoDB and Gemini</p>
        </div>
        
        <!-- Tab Navigation -->
        <div class="tab-navigation">
            <div class="tab-buttons">
                <button class="tab-button active" data-tab="chat">
                    💬 Chat
                    <span class="tab-badge" id="chatBadge">1</span>
                </button>
                <button class="tab-button" data-tab="results" id="resultsButton">
    📊 Results
    <span class="tab-badge" id="resultsBadge" style="display: none;">0</span>
</button>
            </div>
        </div>

        <!-- Tab Content Area -->
        <div class="tab-content-area">
            <!-- Chat Tab -->
            <div class="tab-content active" id="chatTab">
                <div class="chat-container" id="chatContainer">
                    <div class="message ai-message">
                        <span>👋 Hi! I can help you explore California school dashboard data. Ask me about school performance, student groups, or specific districts!</span>
                    </div>
                </div>
                
                <div class="examples">
                    <h3>💡 Try an example:</h3>
                    <div class="example-grid">
                        <div class="example-query" data-query="Which schools in Sunnyvale have red or orange math performance for English Learner students?">Schools in Sunnyvale with red or orange performance for English Learners</div>
                        <div class="example-query" data-query="Show me chronic absenteeism data for English Learners in Oakland">Absenteeism for English Learners in Oakland</div>
                        <div class="example-query" data-query="Find schools in San Francisco with Blue or Green ELA performance">High-performing ELA schools in San Francisco</div>
                    </div>
                </div>
            </div>

            <!-- Results Tab -->
            <div class="tab-content" id="resultsTab">
                <div class="empty-state" id="emptyResults">
                    <h3>📊 No Results Yet</h3>
                    <p>Ask a question or type a school or district to see dashboard indicator data</p>
                </div>
                <div class="results-content" id="resultsContent" style="display: none;"></div>
            </div>
        </div>

        <!-- Input Section - Always Visible -->
        <div class="input-section">
            <div class="input-container">
                <input id="queryInput" type="text" placeholder="What California school or district do you want to learn about...">
                <button id="sendQueryBtn">Ask</button>
            </div>
        </div>
    </div>

    <script>
    // ==============================================================================
    // ===                           JAVASCRIPT - TABBED VERSION                ===
    // ==============================================================================
    
    let messageCount = 1;
    let currentSchoolCount = 0;

    document.addEventListener('DOMContentLoaded', function() {
        console.log("DOM fully loaded. Setting up event listeners.");

        const queryInput = document.getElementById('queryInput');
        const sendQueryBtn = document.getElementById('sendQueryBtn');
        const chatTab = document.getElementById('chatTab');
        const resultsTab = document.getElementById('resultsTab');

        // Tab switching
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', function() {
                const targetTab = this.dataset.tab;
                switchTab(targetTab);
            });
        });

        // Send query functionality
        if (sendQueryBtn) {
            sendQueryBtn.addEventListener('click', sendQuery);
        }

        if (queryInput) {
            queryInput.addEventListener('keypress', function(event) {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    sendQuery();
                }
            });
        }

        // Example query clicks
        chatTab.addEventListener('click', function(event) {
            if (event.target && event.target.matches('.example-query')) {
                const queryText = event.target.dataset.query;
                if (queryText) {
                    setQuery(queryText);
                    sendQuery();
                }
            }
        });

        // Event delegation for dynamically created results content
        const resultsContent = document.getElementById('resultsContent');
        if(resultsContent) {
            resultsContent.addEventListener('click', function(event) {
                const target = event.target;
                if (target.matches('.view-toggle button')) {
                    const viewType = target.dataset.view;
                    if(viewType) toggleView(viewType, target);
                }
            });
            resultsContent.addEventListener('change', function(event) {
                const target = event.target;
                if(target.matches('input[name="studentGroup"]')) {
                    updateTableView();
                }
            });
        }
    });

    function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update tab content - use correct mapping
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    if (tabName === 'chat') {
        document.getElementById('chatTab').classList.add('active');
    } else if (tabName === 'results') {
        document.getElementById('resultsTab').classList.add('active');
    }
}

    function updateTabBadges() {
        // Update chat badge with message count
        const chatBadge = document.getElementById('chatBadge');
        chatBadge.textContent = Math.floor(messageCount / 2); // Divide by 2 since we count both user and AI messages

        // Update results badge
        const resultsBadge = document.getElementById('resultsBadge');
        if (currentSchoolCount > 0) {
            resultsBadge.textContent = currentSchoolCount;
            resultsBadge.style.display = 'inline';
        } else {
            resultsBadge.style.display = 'none';
        }
    }

    function setQuery(text) {
        document.getElementById('queryInput').value = text;
    }

    function sendQuery() {
        const input = document.getElementById('queryInput');
        const query = input.value.trim();
        if (!query) return;

        addMessage(query, 'user');
        input.value = '';
        addMessage('🤔 Analyzing...', 'ai');

        fetch('/query', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({query: query})
        })
        .then(response => {
            if (!response.ok) throw new Error(`Network response error: ${response.statusText}`);
            return response.json();
        })
        .then(data => {
            // Remove the "Analyzing..." message
            const messages = document.querySelectorAll('#chatContainer .message');
            const lastMessage = messages[messages.length - 1];
            if (lastMessage && lastMessage.textContent.includes('Analyzing')) {
                lastMessage.remove();
                messageCount--; // Adjust count since we're removing a message
            }
            
            addMessage(data.response, 'ai');
            
            // Handle results
            if (data.schools && data.schools.length > 0) {
                showResults(data.schools);
                // Auto-switch to results tab when we get data
                switchTab('results');
            } else {
                // Clear results if no schools found
                showEmptyResults();
            }
            
            updateTabBadges();
        })
        .catch(error => {
            // Remove the "Analyzing..." message
            const messages = document.querySelectorAll('#chatContainer .message');
            const lastMessage = messages[messages.length - 1];
            if (lastMessage && lastMessage.textContent.includes('Analyzing')) {
                lastMessage.remove();
                messageCount--;
            }
            addMessage('❌ An error occurred: ' + error.message, 'ai');
            updateTabBadges();
            console.error('Error fetching data:', error);
        });
    }

    function addMessage(text, sender) {
        const container = document.getElementById('chatContainer');
        const message = document.createElement('div');
        message.className = `message ${sender}-message`;
        let formattedText = text;
        if (sender === 'ai') {
            formattedText = formattedText
                .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                .replace(/\\n/g, '<br>');
        }
        message.innerHTML = `<span>${formattedText}</span>`;
        container.appendChild(message);
        
        // Scroll to the new message
        container.scrollTop = container.scrollHeight;
        
        messageCount++;
        updateTabBadges();
    }

    function showEmptyResults() {
        document.getElementById('emptyResults').style.display = 'block';
        document.getElementById('resultsContent').style.display = 'none';
        currentSchoolCount = 0;
        updateTabBadges();
    }

    function showResults(schools) {
    console.log('DEBUG - showResults called with', schools.length, 'schools');
    currentSchoolCount = schools.length;
    
    const emptyResults = document.getElementById('emptyResults');
    const resultsContent = document.getElementById('resultsContent');
    
    if (emptyResults) {
        emptyResults.style.display = 'none';
        console.log('DEBUG - Hidden empty results');
    }
    
    if (resultsContent) {
        resultsContent.style.setProperty('display', 'block', 'important');
        console.log('DEBUG - Showing results content with !important');
    } else {
        console.error('ERROR - resultsContent element not found!');
        return;
    }

    const allIndicators = new Set();
    const allStudentGroups = new Set(['ALL']);
    schools.forEach(school => {
        Object.keys(school.dashboard_indicators || {}).forEach(ind => allIndicators.add(ind));
        Object.keys(school.student_groups || {}).forEach(grp => allStudentGroups.add(grp));
        Object.values(school.student_groups || {}).forEach(groupData => {
            Object.keys(groupData || {}).forEach(ind => allIndicators.add(ind));
        });
    });
    
    const indicators = Array.from(allIndicators);
    const studentGroups = Array.from(allStudentGroups);
    
    let html = `<div class="results-header">
                  <h3>📊 School Performance Results (${schools.length} schools)</h3>
                </div>`;
    
    html += `<div class="view-toggle">
                <button class="active" data-view="table">Table View</button>
             </div>`;

    // New Collapsible Filter System
    html += '<div class="filter-system">';
    
    // Student Groups Filter (Collapsible)
    if (studentGroups.length > 1) {
        html += `
        <div class="filter-section">
            <div class="filter-header" onclick="toggleFilterSection('studentGroups')">
                <span class="filter-title">👥 Student Groups</span>
                <span class="filter-arrow" id="studentGroupsArrow">▼</span>
            </div>
            <div class="filter-content" id="studentGroupsContent">
                <div class="student-group-grid">`;
        
        studentGroups.forEach(group => {
            const checked = group === 'ALL' ? 'checked' : '';
            html += `<label><input type="radio" name="studentGroup" value="${group}" ${checked}> ${getStudentGroupName(group)}</label>`;
        });
        
        html += `    </div>
            </div>
        </div>`;
    }
    
    // Performance Colors Filter (Collapsible)
    html += `
    <div class="filter-section">
        <div class="filter-header" onclick="toggleFilterSection('performanceColors')">
            <span class="filter-title">🎨 Performance Colors</span>
            <span class="filter-arrow" id="performanceColorsArrow">▼</span>
        </div>
        <div class="filter-content collapsed" id="performanceColorsContent">
            <div class="color-filter-grid">
                <label class="color-filter-item">
                    <input type="checkbox" name="colorFilter" value="Blue" onchange="updateColorFilter()">
                    <span class="color-sample blue-sample">🔵 Blue</span>
                    <span class="color-description">Highest Performance</span>
                </label>
                <label class="color-filter-item">
                    <input type="checkbox" name="colorFilter" value="Green" onchange="updateColorFilter()">
                    <span class="color-sample green-sample">🟢 Green</span>
                    <span class="color-description">Above Average</span>
                </label>
                <label class="color-filter-item">
                    <input type="checkbox" name="colorFilter" value="Yellow" onchange="updateColorFilter()">
                    <span class="color-sample yellow-sample">🟡 Yellow</span>
                    <span class="color-description">Average Performance</span>
                </label>
                <label class="color-filter-item">
                    <input type="checkbox" name="colorFilter" value="Orange" onchange="updateColorFilter()">
                    <span class="color-sample orange-sample">🟠 Orange</span>
                    <span class="color-description">Below Average</span>
                </label>
                <label class="color-filter-item">
                    <input type="checkbox" name="colorFilter" value="Red" onchange="updateColorFilter()">
                    <span class="color-sample red-sample">🔴 Red</span>
                    <span class="color-description">Lowest Performance</span>
                </label>
            </div>
            <div class="color-filter-actions">
                <button onclick="selectAllColors()" class="filter-action-btn">Select All</button>
                <button onclick="clearAllColors()" class="filter-action-btn">Clear All</button>
                <button onclick="selectProblemsOnly()" class="filter-action-btn problems-btn">Problems Only (Red + Orange)</button>
            </div>
        </div>
    </div>`;
    
    html += '</div>'; // End filter-system
    
    html += `<div id="tableView" class="performance-table">${generateTableView(schools, indicators, 'ALL')}</div>`;
    
    resultsContent.innerHTML = html;
    console.log('DEBUG - HTML injected successfully');
    
    updateTabBadges();
}
// Toggle filter section open/closed
function toggleFilterSection(sectionId) {
    const content = document.getElementById(sectionId + 'Content');
    const arrow = document.getElementById(sectionId + 'Arrow');
    
    if (content.classList.contains('collapsed')) {
        content.classList.remove('collapsed');
        arrow.textContent = '▲';
    } else {
        content.classList.add('collapsed');
        arrow.textContent = '▼';
    }
}

// Color filtering functions
function updateColorFilter() {
    const selectedColors = Array.from(document.querySelectorAll('input[name="colorFilter"]:checked'))
                               .map(cb => cb.value);
    
    const tableRows = document.querySelectorAll('.performance-table tbody tr');
    
    if (selectedColors.length === 0) {
        // No colors selected = show all rows
        tableRows.forEach(row => row.style.display = '');
        return;
    }
    
    tableRows.forEach(row => {
        const colorCells = row.querySelectorAll('.color-cell');
        let shouldShow = false;
        
        // Check if any cell in this row matches selected colors
        colorCells.forEach(cell => {
            const cellClasses = cell.className;
            selectedColors.forEach(color => {
                if (cellClasses.includes(color)) {
                    shouldShow = true;
                }
            });
        });
        
        row.style.display = shouldShow ? '' : 'none';
    });
    
    updateVisibleRowCount();
}

function selectAllColors() {
    document.querySelectorAll('input[name="colorFilter"]').forEach(cb => {
        cb.checked = true;
    });
    updateColorFilter();
}

function clearAllColors() {
    document.querySelectorAll('input[name="colorFilter"]').forEach(cb => {
        cb.checked = false;
    });
    updateColorFilter();
}

function selectProblemsOnly() {
    // Clear all first
    clearAllColors();
    // Select only Red and Orange
    document.querySelector('input[name="colorFilter"][value="Red"]').checked = true;
    document.querySelector('input[name="colorFilter"][value="Orange"]').checked = true;
    updateColorFilter();
}

function updateVisibleRowCount() {
    const visibleRows = document.querySelectorAll('.performance-table tbody tr[style=""], .performance-table tbody tr:not([style*="none"])').length;
    const totalRows = document.querySelectorAll('.performance-table tbody tr').length;
    
    // Update results header to show filtered count
    const resultsHeader = document.querySelector('.results-header h3');
    if (resultsHeader) {
        const originalText = resultsHeader.textContent;
        const baseText = originalText.split('(')[0].trim();
        resultsHeader.textContent = `${baseText} (${visibleRows} of ${totalRows} schools shown)`;
    }
}
    function toggleView(viewType, buttonElement) {
        document.querySelectorAll('.view-toggle button').forEach(btn => btn.classList.remove('active'));
        buttonElement.classList.add('active');
        // Future: add card view logic here
    }

    function updateTableView() {
    const selectedGroup = document.querySelector('input[name="studentGroup"]:checked').value;
    const schools = window.currentSchools;
    const indicators = window.currentIndicators;
    if (schools && indicators) {
        document.getElementById('tableView').innerHTML = generateTableView(schools, indicators, selectedGroup);
        // Reapply color filters after table regeneration
        updateColorFilter();
    }
}


    function generateTableView(schools, indicators, selectedGroup) {
    window.currentSchools = schools; // Cache for updates
    window.currentIndicators = indicators;

    let tableHtml = '<table><thead><tr><th>School</th>';
    indicators.forEach(indicator => tableHtml += `<th>${formatIndicatorLabel(indicator)}</th>`);
    tableHtml += '</tr></thead><tbody>';

    schools.slice(0, 50).forEach(school => {
        tableHtml += `<tr><td class="school-name-cell">${school.school_name}</td>`;
        indicators.forEach(indicator => {
            let data = (selectedGroup === 'ALL')
                ? (school.dashboard_indicators || {})[indicator]
                : ((school.student_groups || {})[selectedGroup] || {})[indicator];

            const status = data?.status || 'No Data';
            const value = data?.rate ?? data?.points_below_standard ?? 0;
            const change = data?.change || 0;
            
            const displayStatus = status.replace(/\s/g, '-');
            const tooltip = data ? formatTooltip(indicator, status, value, change) : 'No data available';
            
            // Generate trend arrow and change text
            const trendInfo = formatTrendInfo(indicator, change);
            
            // Generate performance value display (like "3 points above standard")
            const performanceValue = formatPerformanceValue(indicator, value);
            
            tableHtml += `<td>
                <div class="performance-cell">
                    <div class="color-cell ${displayStatus}" title="${tooltip}">${status}</div>
                    <div class="performance-value">${performanceValue}</div>
                    <div class="trend-info">${trendInfo}</div>
                </div>
            </td>`;
        });
        tableHtml += '</tr>';
    });

    tableHtml += '</tbody></table>';
    if (schools.length > 50) {
        tableHtml += `<p class="results-footer">Showing first 50 of ${schools.length} total results.</p>`;
    }
    return tableHtml;
}

function formatPerformanceValue(indicator, value) {
    if (!value && value !== 0) {
        return '<span class="performance-na">--</span>';
    }
    
    if (indicator.includes('performance')) {
        // For ELA/Math: Show distance from standard
        const absValue = Math.abs(value);
        const direction = value >= 0 ? 'above' : 'below';
        const colorClass = value >= 0 ? 'performance-above' : 'performance-below';
        
        return `<span class="${colorClass}">${absValue.toFixed(1)} pts ${direction}</span>`;
    } else {
        // For percentage indicators: Show the rate
        return `<span class="performance-rate">${value.toFixed(1)}%</span>`;
    }
}

function formatTrendInfo(indicator, change) {
    if (!change || change === 0) {
        return '<span class="trend-stable">➡️ --</span>';
    }
    
    const absChange = Math.abs(change);
    let arrow, changeText, cssClass;
    
    // Arrow direction is always based on actual change direction
    if (change > 0) {
        arrow = '↗️';
        changeText = `+${absChange.toFixed(1)}`;
    } else {
        arrow = '↘️';
        changeText = `-${absChange.toFixed(1)}`;
    }
    
    // Add units based on indicator type
    if (indicator.includes('performance')) {
        changeText += 'pts';
    } else {
        changeText += '%';
    }
    
    // Color is based on whether the change is GOOD or BAD for that indicator
    if (indicator === 'chronic_absenteeism' || indicator === 'suspension_rate') {
        // For these indicators: decrease = good, increase = bad
        cssClass = (change < 0) ? 'trend-good' : 'trend-bad';
    } else {
        // For graduation, college_career, english_learner_progress, and performance: increase = good, decrease = bad
        cssClass = (change > 0) ? 'trend-good' : 'trend-bad';
    }
    
    return `<span class="${cssClass}">${arrow} ${changeText}</span>`;
}

function formatTooltip(indicator, status, value, change) {
    let tooltip = '';
    
    if (indicator.includes('performance')) {
        const direction = value >= 0 ? 'above' : 'below';
        tooltip = `${status}: ${Math.abs(value).toFixed(1)} points ${direction} standard`;
    } else {
        tooltip = `${status}: ${value.toFixed(1)}%`;
    }
    
    // Add change information to tooltip
    if (change && change !== 0) {
        const changeDirection = change > 0 ? 'increased' : 'decreased';
        const changeAmount = Math.abs(change).toFixed(1);
        
        if (indicator.includes('performance')) {
            tooltip += ` | Change: ${changeDirection} by ${changeAmount} points`;
        } else {
            tooltip += ` | Change: ${changeDirection} by ${changeAmount}%`;
        }
    }
    
    return tooltip;
}

// Keep your existing helper functions - they're still needed!
function formatIndicatorLabel(indicator) {
    const labels = {
        'chronic_absenteeism': 'Attendance', 
        'ela_performance': 'ELA', 
        'math_performance': 'Math', 
        'suspension_rate': 'Suspension',
        'college_career': 'College/Career',
        'graduation_rate': 'Graduation',
        'english_learner_progress': 'EL Progress'
    };
    return labels[indicator] || indicator.replace(/_/g, ' ').replace(/\b\\w/g, l => l.toUpperCase());
}

function getStudentGroupName(short_code) {
    const map = {
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
    };
    return map[short_code] || short_code;
}

    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/query', methods=['POST'])
@limiter.limit("10 per minute")  # Max 10 queries per minute per IP

def handle_query():
    user_query = request.json.get('query')
    if not user_query:
        return jsonify({"error": "No query provided"}), 400

    # Use the appropriate parsing function
    parsed_query = parse_query_with_real_ai(user_query)
    
    # If AI determined data is unavailable, return early
    if parsed_query and parsed_query.get("data_availability") == "not_available":
        response_text = generate_intelligent_response(user_query, [], parsed_query)
        return jsonify({"response": response_text, "schools": []})

    # Build and execute MongoDB query
    mongo_query = build_mongodb_query(parsed_query)
    try:
        results = list(schools_collection.find(mongo_query).limit(50))
        # Convert ObjectId to string for JSON serialization
        for item in results:
            item['_id'] = str(item['_id'])
    except Exception as e:
        print(f"MongoDB query failed: {e}")
        return jsonify({"error": "Database query failed"}), 500

    # Add debug logging for results
    print(f"DEBUG - Query returned {len(results)} schools")
    if len(results) > 0:
        first_school = results[0]
        print(f"DEBUG - First school: {first_school.get('school_name', 'Unknown')} in {first_school.get('district_name', 'Unknown')}")
        print(f"DEBUG - Dashboard indicators: {list(first_school.get('dashboard_indicators', {}).keys())}")
        print(f"DEBUG - Student groups: {list(first_school.get('student_groups', {}).keys())}")
    
        # Check if ELPI data exists
        dashboard_indicators = first_school.get('dashboard_indicators', {})
        if 'english_learner_progress' in dashboard_indicators:
            print(f"DEBUG - ELPI in dashboard: {dashboard_indicators['english_learner_progress']}")
        else:
            print("DEBUG - ELPI NOT found in dashboard indicators")
        
        # Check student groups for ELPI
        student_groups = first_school.get('student_groups', {})
        for group_name, group_data in student_groups.items():
            if 'english_learner_progress' in group_data:
                print(f"DEBUG - ELPI found in group {group_name}: {group_data['english_learner_progress']}")
    else:
        print("DEBUG - No schools found matching criteria")

    # Generate the final response
    response_text = generate_intelligent_response(user_query, results, parsed_query)
    
    return jsonify({"response": response_text, "schools": results})

if __name__ == '__main__':
    # Use environment variable for port, default to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host='0.0.0.0', port=port)