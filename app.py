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
        school_name = school.get("school_name", "Unknown School")
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
            response_parts.extend(problem_schools[:8])  # Limit to 8 schools
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
# ===                           HTML TEMPLATE                                ===
# ==============================================================================
# The script section below has been fully restored to parse the JSON data
# and render it as proper HTML tables and cards.
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
        
        .main-content {
            display: flex;
            flex-direction: column;
            flex-grow: 1;
            overflow: hidden;
        }

        .chat-area {
            flex-grow: 1;
            overflow-y: auto;
            padding: 25px;
        }
        .chat-container { 
            background: #fff;
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
            background: #fafafa; padding: 20px 25px; border-top: 1px solid #e8e8e8;
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
        
        .input-section { 
            padding: 15px 25px; background: white; border-top: 1px solid #e8e8e8;
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
        
        .results { 
            background: #f8f9fa;
            border-top: 1px solid #e8e8e8;
            padding: 20px;
            overflow-y: auto;
            flex-shrink: 0; /* Let it take space but not grow */
            max-height: 50vh; /* Don't let it take over the whole screen */
        }
        .results h3 { 
            padding-bottom: 15px; margin: 0 0 15px 0; font-weight: 500;
            border-bottom: 1px solid #ddd; color: #333;
        }
        .performance-table table { width: 100%; border-collapse: collapse; font-size: 14px; }
        .performance-table th, .performance-table td { padding: 10px 12px; border: 1px solid #ddd; text-align: left; }
        .performance-table th { background-color: #f0f2f5; font-weight: 500; }
        .school-name-cell { font-weight: 500; }
        .color-cell { text-align: center; font-weight: 500; border-radius: 4px; padding: 6px; color: white; }
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
        .student-group-selector { margin-bottom: 15px; font-size: 14px; }
        .student-group-selector label { margin-right: 15px; }
        .results-footer { text-align: center; margin-top: 15px; color: #666; font-style: italic; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏫 California Schools AI Dashboard</h1>
            <p>Explore school performance data using natural language</p>
        </div>
        
        <div class="main-content">
            <div class="chat-area">
                <div class="chat-container" id="chatContainer">
                    <div class="message ai-message">
                        <span>👋 Hi! I can help you explore California school dashboard data. Ask me anything about school performance, student groups, or specific districts!</span>
                    </div>
                </div>
            </div>
            <div class="results" id="results" style="display:none;"></div>
            <div class="examples" id="examplesContainer">
                <h3>💡 Try an example:</h3>
                <div class="example-grid">
                    <div class="example-query" data-query="Which schools in Sunnyvale have red or orange math performance for Hispanic students?">Schools in Sunnyvale with math issues for Hispanic students</div>
                    <div class="example-query" data-query="Show me chronic absenteeism issues for English Learners in Oakland">Absenteeism for English Learners in Oakland</div>
                    <div class="example-query" data-query="Find schools in San Francisco with Blue or Green ELA performance">High-performing ELA schools in SF</div>
                </div>
            </div>
            <div class="input-section">
                <div class="input-container">
                    <input id="queryInput" type="text" placeholder="Ask about California schools...">
                    <button id="sendQueryBtn">Ask</button>
                </div>
            </div>
        </div>
    </div>

    <script>
    // ==============================================================================
    // ===                           JAVASCRIPT CORE                            ===
    // ==============================================================================
    document.addEventListener('DOMContentLoaded', function() {
        console.log("DOM fully loaded. Setting up event listeners.");

        const queryInput = document.getElementById('queryInput');
        const sendQueryBtn = document.getElementById('sendQueryBtn');
        const examplesContainer = document.getElementById('examplesContainer');
        const resultsDiv = document.getElementById('results');

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

        if (examplesContainer) {
            examplesContainer.addEventListener('click', function(event) {
                if (event.target && event.target.matches('.example-query')) {
                    const queryText = event.target.dataset.query;
                    if (queryText) {
                        setQuery(queryText);
                        sendQuery(); // Optionally send the query right away
                    }
                }
            });
        }

        // Event delegation for dynamically created results content
        if(resultsDiv) {
            resultsDiv.addEventListener('click', function(event) {
                const target = event.target;
                if (target.matches('.view-toggle button')) {
                    const viewType = target.dataset.view;
                    if(viewType) toggleView(viewType, target);
                }
            });
            resultsDiv.addEventListener('change', function(event) {
                const target = event.target;
                if(target.matches('input[name="studentGroup"]')) {
                    updateTableView();
                }
            });
        }
    });

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
        document.getElementById('results').style.display = 'none'; // Hide old results

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
            const messages = document.querySelectorAll('#chatContainer .message');
            const lastMessage = messages[messages.length - 1];
            if (lastMessage && lastMessage.textContent.includes('Analyzing')) {
                lastMessage.remove();
            }
            addMessage(data.response, 'ai');
            
            // *** THIS IS THE FIX: Call showResults instead of displaying raw JSON ***
            if (data.schools && data.schools.length > 0) {
                showResults(data.schools);
            }
        })
        .catch(error => {
            const messages = document.querySelectorAll('#chatContainer .message');
            const lastMessage = messages[messages.length - 1];
            if (lastMessage && lastMessage.textContent.includes('Analyzing')) {
                lastMessage.remove();
            }
            addMessage('❌ An error occurred: ' + error.message, 'ai');
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
        document.querySelector('.chat-area').scrollTop = document.querySelector('.chat-area').scrollHeight;
    }

    // --- Functions to Render Results ---
    function showResults(schools) {
        const resultsDiv = document.getElementById('results');
        resultsDiv.style.display = 'block';

        const allIndicators = new Set();
        const allStudentGroups = new Set(['ALL']);
        schools.forEach(school => {
            Object.keys(school.dashboard_indicators || {}).forEach(ind => allIndicators.add(ind));
            Object.keys(school.student_groups || {}).forEach(grp => allStudentGroups.add(grp));
        });
        const indicators = Array.from(allIndicators);
        const studentGroups = Array.from(allStudentGroups);
        
        let html = `<h3>📊 Detailed Results (${schools.length} schools)</h3>`;
        html += `<div class="view-toggle">
                    <button class="active" data-view="table">Table View</button>
                 </div>`;

        if (studentGroups.length > 1) {
            html += '<div class="student-group-selector"><strong>View Performance For: </strong>';
            studentGroups.forEach(group => {
                const checked = group === 'ALL' ? 'checked' : '';
                html += `<label><input type="radio" name="studentGroup" value="${group}" ${checked}> ${getStudentGroupName(group)}</label>`;
            });
            html += '</div>';
        }

        html += `<div id="tableView" class="performance-table">${generateTableView(schools, indicators, 'ALL')}</div>`;
        resultsDiv.innerHTML = html;
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
                const value = data?.rate ?? data?.points_below_standard;
                const displayStatus = status.replace(/\\s/g, '-');
                const tooltip = data ? formatTooltip(indicator, status, value || 0) : 'No data available';
                tableHtml += `<td><div class="color-cell ${displayStatus}" title="${tooltip}">${status}</div></td>`;
            });
            tableHtml += '</tr>';
        });

        tableHtml += '</tbody></table>';
        if (schools.length > 50) {
            tableHtml += `<p class="results-footer">Showing first 50 of ${schools.length} total results.</p>`;
        }
        return tableHtml;
    }

    // --- Formatting Helpers ---
    function formatIndicatorLabel(indicator) {
        const labels = {'chronic_absenteeism': 'Attendance', 'ela_performance': 'ELA', 'math_performance': 'Math', 'suspension_rate': 'Suspension'};
        return labels[indicator] || indicator.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase());
    }

    function getStudentGroupName(short_code) {
        const map = {'ALL':'All Students','AA':'Black/African American','AI':'American Indian','AS':'Asian','FI':'Filipino','HI':'Hispanic/Latino','PI':'Pacific Islander','WH':'White','MR':'Two or More Races','EL':'English Learners','SED':'Socioeconomically Disadvantaged','SWD':'Students with Disabilities','HOM':'Homeless','FOS':'Foster Youth'};
        return map[short_code] || short_code;
    }

    function formatTooltip(indicator, status, value) {
        if (indicator.includes('performance')) {
            const direction = value >= 0 ? 'above' : 'below';
            return `${status}: ${Math.abs(value).toFixed(1)} points ${direction} standard`;
        }
        return `${status}: ${value.toFixed(1)}%`;
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

    # Generate the final response
    response_text = generate_intelligent_response(user_query, results, parsed_query)
    
    return jsonify({"response": response_text, "schools": results})

if __name__ == '__main__':
    # Use environment variable for port, default to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
