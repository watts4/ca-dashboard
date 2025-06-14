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
# The primary changes are in the HTML and JavaScript below.
# 1. `onclick="..."` has been removed from the example queries.
# 2. They now use `data-query="..."` to store the query text.
# 3. The JavaScript now adds event listeners instead of relying on onclick.
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
            line-height: 1.5;
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
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏫 California Schools AI Dashboard</h1>
            <p>Technical analysis of CA Dashboard data with student group breakdowns</p>
        </div>
        
        <div class="examples" id="examplesContainer">
            <h3>💡 Try These Example Queries:</h3>
            <div class="example-grid">
                <!-- *** HTML CHANGE: Removed 'onclick' and added 'data-query' *** -->
                <div class="example-query" data-query="What are the red and orange areas for Sunnyvale School District?">What are the red and orange areas for Sunnyvale School District?</div>
                <div class="example-query" data-query="Which student groups are struggling with math in San Miguel Elementary?">Which student groups are struggling with math in San Miguel Elementary?</div>
                <div class="example-query" data-query="Show me chronic absenteeism issues for Hispanic students">Show me chronic absenteeism issues for Hispanic students</div>
                <div class="example-query" data-query="Which school in Sunnyvale did the best with Hispanic students in math?">Which school in Sunnyvale did the best with Hispanic students in math?</div>
            </div>
        </div>
        
        <div class="chat-container" id="chatContainer">
            <div class="message ai-message">
                <span>👋 Hi! I can help you explore California school dashboard data. Ask me anything about school performance, student groups, or specific districts!</span>
            </div>
        </div>
        
        <div class="input-section">
            <div class="input-container">
                <input id="queryInput" type="text" placeholder="Ask about California schools...">
                <button id="sendQueryBtn">Ask</button>
            </div>
        </div>
    </div>
    
    <div class="results" id="results"></div>

    <script>
    /**
     * Main function that runs after the page is fully loaded.
     * It sets up all event listeners for the application, avoiding the
     * need for any 'onclick' attributes in the HTML. This is the correct
     * and modern way to handle user interactions.
     */
    document.addEventListener('DOMContentLoaded', function() {
        console.log("DOM fully loaded. Setting up event listeners.");

        const queryInput = document.getElementById('queryInput');
        const sendQueryBtn = document.getElementById('sendQueryBtn');
        const examplesContainer = document.getElementById('examplesContainer');

        // --- Event Listener for the "Ask" Button ---
        if (sendQueryBtn) {
            sendQueryBtn.addEventListener('click', sendQuery);
        }

        // --- Event Listener for the Enter Key in the Input Box ---
        if (queryInput) {
            queryInput.addEventListener('keypress', function(event) {
                if (event.key === 'Enter') {
                    event.preventDefault(); // Stop the default form submission
                    sendQuery();
                }
            });
        }

        // --- Event Listener for Example Queries (Event Delegation) ---
        // *** JS FIX: This now correctly listens on the '.examples' div ***
        if (examplesContainer) {
            examplesContainer.addEventListener('click', function(event) {
                // Check if the clicked element is an example query
                if (event.target && event.target.matches('.example-query')) {
                    const queryText = event.target.dataset.query;
                    if (queryText) {
                        setQuery(queryText);
                    }
                }
            });
        }
    });

    // -------------------------------------------------------------------------
    // -- Core Application Functions -------------------------------------------
    // -------------------------------------------------------------------------

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
            const messages = document.querySelectorAll('#chatContainer .message');
            const lastMessage = messages[messages.length - 1];
            if (lastMessage && lastMessage.textContent.includes('Analyzing')) {
                lastMessage.remove();
            }
            addMessage(data.response, 'ai');
            // This is a placeholder for where you would display detailed results
            // For now, we clear the results div. Your `showResults` function would go here.
            document.getElementById('results').innerHTML = JSON.stringify(data.schools, null, 2);
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
            // Basic markdown formatting
            formattedText = formattedText
                .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                .replace(/\\*/g, '')
                .replace(/\\n|\\n/g, '<br>')
                .replace(/^- /gm, '• ');
        }
        message.innerHTML = `<span>${formattedText}</span>`;
        container.appendChild(message);
        container.scrollTop = container.scrollHeight;
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
