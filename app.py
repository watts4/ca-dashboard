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

# Enhanced HTML Template with improved response formatting
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
            padding: 16px 20px; border-radius: 18px 18px 18px 4px; 
            display: inline-block; max-width: 85%; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            line-height: 1.5;
        }
        
        /* Improved AI response formatting */
        .ai-message span h3 {
            margin: 0 0 12px 0;
            color: #1976d2;
            font-size: 16px;
            font-weight: 600;
        }
        
        .ai-message span h4 {
            margin: 16px 0 8px 0;
            color: #333;
            font-size: 14px;
            font-weight: 600;
        }
        
        .ai-message span ul {
            margin: 8px 0;
            padding-left: 20px;
        }
        
        .ai-message span li {
            margin: 6px 0;
            line-height: 1.4;
        }
        
        .ai-message span strong {
            color: #1976d2;
        }
        
        .ai-message span p {
            margin: 8px 0;
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
        .input-container button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
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
                <div class="example-query" onclick="setQuery(this.textContent)">Which schools have red performance indicators?</div>
                <div class="example-query" onclick="setQuery(this.textContent)">ELA performance problems in Oakland schools</div>
            </div>
        </div>
        
        <div class="chat-container" id="chatContainer">
            <div class="message ai-message">
                <span>👋 Hello! I can help you explore California school dashboard data with detailed student group breakdowns. I understand Distance from Standard (DFS), chronic absenteeism rates, and all the technical nuances of CA Dashboard indicators. Ask me anything!</span>
            </div>
        </div>
        
        <div class="input-section">
            <div class="input-container">
                <input type="text" id="queryInput" placeholder="Ask about CA school performance by student groups..." onkeypress="if(event.key==='Enter') sendQuery()">
                <button id="askButton" onclick="sendQuery()">Ask</button>
            </div>
        </div>
    </div>
    
    <div class="results" id="results"></div>

    <script>
        function setQuery(text) {
            document.getElementById('queryInput').value = text;
        }
        
        function convertMarkdownToHtml(text) {
            // Convert markdown formatting to HTML for better display
            return text
                // Headers
                .replace(/^### (.*$)/gim, '<h4>$1</h4>')
                .replace(/^## (.*$)/gim, '<h3>$1</h3>')
                .replace(/^\*\*(.*?):\*\*/gim, '<h4>$1:</h4>')
                
                // Bold text
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                
                // Bullet points
                .replace(/^• (.*$)/gim, '<li>$1</li>')
                .replace(/^- (.*$)/gim, '<li>$1</li>')
                
                // Wrap lists
                .replace(/(<li>.*<\/li>)/gs, function(match) {
                    return '<ul>' + match + '</ul>';
                })
                
                // Line breaks
                .replace(/\n\n/g, '</p><p>')
                .replace(/\n/g, '<br>')
                
                // Wrap in paragraphs
                .replace(/^(?!<[hul])/gm, '<p>')
                .replace(/(?<!>)$/gm, '</p>')
                
                // Clean up extra tags
                .replace(/<p><\/p>/g, '')
                .replace(/<p>(<[hul])/g, '$1')
                .replace(/(<\/[hul][^>]*>)<\/p>/g, '$1');
        }
        
        async function sendQuery() {
            const input = document.getElementById('queryInput');
            const button = document.getElementById('askButton');
            const query = input.value.trim();
            if (!query) return;
            
            // Disable button and show loading state
            button.disabled = true;
            button.textContent = 'Analyzing...';
            
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
                
                // Add AI response with improved formatting
                const formattedResponse = convertMarkdownToHtml(data.response);
                addMessage(formattedResponse, 'ai');
                
                // Show detailed results
                showResults(data.schools);
                
            } catch (error) {
                document.querySelector('#chatContainer .message:last-child').remove();
                addMessage('❌ Sorry, something went wrong. Please try again.', 'ai');
            } finally {
                // Re-enable button
                button.disabled = false;
                button.textContent = 'Ask';
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
                'college_career': 'College/Career'
            };
            return labels[indicator] || indicator.replace('_', ' ').toUpperCase();
        }

        function formatTooltip(indicator, status, value) {
            if (indicator === 'chronic_absenteeism') {
                return `${value.toFixed(1)}% of students chronically absent (≥10% days missed)`;
            } else if (indicator === 'suspension_rate') {
                return `${value.toFixed(1)}% of students suspended (≥1 full day aggregate)`;
            } else if (indicator === 'college_career') {
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