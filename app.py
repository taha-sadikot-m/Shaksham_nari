# app.py (updated backend)
from flask import Flask, render_template, request, jsonify, session
import sqlite3 # Added
import json # Added
import uuid
from groq import Groq
import logging
from google import genai # Changed
from google.genai import types # Changed
# import pymongo # Removed

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this for production

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLite Database setup
DATABASE = 'database.db' # Define database file

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row # Access columns by name
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Users table: id is the user_id, data stores all user profile info as JSON string
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Initialize the database if it doesn't exist
init_db()

# Groq setup
GROQ_API_KEY = "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" # User should replace with env var
client = Groq(api_key=GROQ_API_KEY)

# Gemini setup
GEMINI_API_KEY = "AIzaSyAT01e62IH8PNrE6LqtsJRLhd5Cb0h2Bv0" # User should replace with env var
# Initialize the Gemini client

google_client =  genai.Client(api_key=GEMINI_API_KEY)

GEMINI_MODEL_TEXT = 'gemini-1.5-flash-latest' # Using a common model name, adjust if needed. Original: 'gemini-2.5-flash-preview-04-17'
#gemini_model = genai.GenerativeModel(model_name=GEMINI_MODEL_TEXT) # Added

# For dynamic retrieval configuration
def create_dynamic_search_tool(threshold=0.3):
    return types.Tool(
        google_search=types.GoogleSearchRetrieval(
            dynamic_retrieval_config=types.DynamicRetrievalConfig(
                dynamic_threshold=threshold
            )
        )
    )


# Define the Google Search tool (can be reused)
def create_google_search_tool():
    return types.Tool(
        google_search=types.GoogleSearch()
    )

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT data FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row['data']:
        return json.loads(row['data'])
    return None

def save_user_data(user_id, data_to_save):  
    conn = get_db_connection()
    cursor = conn.cursor()
    # Fetch existing data
    cursor.execute("SELECT data FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    
    existing_data = {}
    if row and row['data']:
        existing_data = json.loads(row['data'])
    
    # Merge new data with existing data (mimicking $set behavior)
    existing_data.update(data_to_save)
        
    updated_data_json = json.dumps(existing_data)
    
    # Upsert: Insert if not exists, replace if exists
    cursor.execute("INSERT OR REPLACE INTO users (id, data) VALUES (?, ?)", (user_id, updated_data_json))
    conn.commit()
    conn.close()

def reset_user_data(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def call_groq_api(prompt):
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
    )
    return chat_completion.choices[0].message.content

def map_grounding_chunks(citations):
    """Map Gemini citations to our source format"""
    if not citations:
        return []
    
    sources = []
    for citation in citations:
        if citation.startswith("http"):
            sources.append({
                "uri": citation,
                "title": citation.split("//")[-1].split("/")[0]  # Extract domain
            })
    return sources

@app.route('/')
def index():
    # Generate a unique session ID if it doesn't exist
    if 'user_id' not in session:
        session['user_id'] = f"web_{uuid.uuid4().hex}"
    
    user = get_user(session['user_id'])
    return render_template('index.html', user_exists=user is not None)

@app.route('/api/start', methods=['POST'])
def start():
    user_id = session['user_id']
    user = get_user(user_id)
    
    if user:
        # Removed MongoDB _id field handling:
        # if '_id' in user:
        #     del user['_id']
        return jsonify({
            "status": "existing",
            "message": "Welcome back!",
            "user": user
        })
    else:
        return jsonify({
            "status": "new",
            "message": "Welcome! Let's get some details first.",
            "next_step": "gender"
        })

@app.route('/api/step', methods=['POST'])
def handle_step():
    data = request.json
    step = data.get('step')
    answer = data.get('answer')
    user_id = session['user_id']
    
    if step == "gender":
        save_user_data(user_id, {"gender": answer})
        return jsonify({
            "next_step": "age",
            "message": "Select your Age Group:",
            "options": ['< 18', '18-25', '26-35', '36-45', '46-60', '> 60']
        })
    
    elif step == "age":
        save_user_data(user_id, {"age_group": answer})
        return jsonify({
            "next_step": "salary",
            "message": "Select your Salary Range:",
            "options": ['< 3 lakh', '3-7 lakh', '7-10 lakh', '10-12 lakh', '> 12 lakh']
        })
    
    elif step == "salary":
        save_user_data(user_id, {"salary": answer})
        return jsonify({
            "next_step": "education",
            "message": "Select your Education Level:",
            "options": ['Primary', 'Secondary', "Bachelor's", "Master's", 'PhD']
        })
    
    elif step == "education":
        save_user_data(user_id, {"education": answer})
        return jsonify({
            "next_step": "investment",
            "message": "What type of investments are you interested in?",
            "options": ['📊 Equity', '🏦 Debt Investment', '🏠 Real Estate']
        })
    
    elif step == "investment":
        save_user_data(user_id, {"investment": answer})
        if answer == "📊 Equity":
            return jsonify({
                "next_step": "equity_risk",
                "message": "Great! What is your risk tolerance for equity investments?",
                "options": ["Low", "Medium", "High"]
            })
        elif answer == "🏦 Debt Investment":
            return jsonify({
                "next_step": "debt_type",
                "message": "What type of debt investment are you interested in?",
                "options": ["Bonds", "Fixed Deposits", "Other"]
            })
        elif answer == "🏠 Real Estate":
            return jsonify({
                "next_step": "real_estate_type",
                "message": "What type of property are you interested in?",
                "options": ["Residential", "Commercial"]
            })
    
    elif step == "equity_risk":
        save_user_data(user_id, {"equity_risk_tolerance": answer})
        return jsonify({
            "next_step": "dashboard",
            "message": "Thank you! We'll use this information to help with equity investment advice."
        })
    
    elif step == "debt_type":
        save_user_data(user_id, {"debt_investment_type": answer})
        return jsonify({
            "next_step": "dashboard",
            "message": "Thank you! We'll use this information to help with debt investment advice."
        })
    
    elif step == "real_estate_type":
        save_user_data(user_id, {"real_estate_property_type": answer})
        return jsonify({
            "next_step": "dashboard",
            "message": "Thank you! We'll use this information to help with real estate investment advice."
        })
    
    return jsonify({"error": "Invalid step"}), 400

@app.route('/api/reset', methods=['POST'])
def reset():
    user_id = session['user_id']
    reset_user_data(user_id)
    
    # Create a new session ID to start fresh
    session['user_id'] = f"web_{uuid.uuid4().hex}"
    
    return jsonify({
        "status": "reset",
        "message": "Your knowledge has been reset. Let's start over.",
        "next_step": "gender"
    })

@app.route('/api/update_field', methods=['POST'])
def update_field():
    data = request.json
    field = data.get('field')
    value = data.get('value')
    user_id = session['user_id']
    
    if not field or value is None:
        return jsonify({"error": "Missing field or value"}), 400
    
    # Special handling for investment field to show appropriate follow-up
    if field == "investment":
        save_user_data(user_id, {"investment": value})
        
        if value == "📊 Equity":
            return jsonify({
                "next_step": "equity_risk",
                "message": "Great! What is your risk tolerance for equity investments?",
                "options": ["Low", "Medium", "High"]
            })
        elif value == "🏦 Debt Investment":
            return jsonify({
                "next_step": "debt_type",
                "message": "What type of debt investment are you interested in?",
                "options": ["Bonds", "Fixed Deposits", "Other"]
            })
        elif value == "🏠 Real Estate":
            return jsonify({
                "next_step": "real_estate_type",
                "message": "What type of property are you interested in?",
                "options": ["Residential", "Commercial"]
            })
    
    # Update the field
    save_user_data(user_id, {field: value})
    
    # For other fields, just confirm the update
    return jsonify({
        "status": "updated",
        "message": f"{field.replace('_', ' ').title()} updated successfully!",
        "field": field,
        "value": value
    })

@app.route('/api/ask', methods=['POST'])
def ask_question():
    data = request.json
    question = data.get('question')
    user_id = session['user_id']
    
    user = get_user(user_id)
    if not user:
        return jsonify({"error": "User not found. Please start over."}), 400
    
    # Construct context from user data
    context = f"""
    User Profile:
    - Gender: {user.get('gender', 'Not specified')}
    - Age Group: {user.get('age_group', 'Not specified')}
    - Salary Range: {user.get('salary', 'Not specified')}
    - Education: {user.get('education', 'Not specified')}
    - Investment Interest: {user.get('investment', 'Not specified')}
    """
    
    # Add investment-specific details
    if user.get('investment') == "📊 Equity":
        context += f"- Risk Tolerance: {user.get('equity_risk_tolerance', 'Not specified')}"
    elif user.get('investment') == "🏦 Debt Investment":
        context += f"- Debt Type: {user.get('debt_investment_type', 'Not specified')}"
    elif user.get('investment') == "🏠 Real Estate":
        context += f"- Property Type: {user.get('real_estate_property_type', 'Not specified')}"
    
    # Create prompt for Groq API
    prompt = f"User Question: {question}\n\n{context}\n\nPlease provide a helpful, professional response as an investment advisor:"
    
    try:
        response = call_groq_api(prompt)
        return jsonify({"answer": response})
    except Exception as e:
        logger.error(f"Error calling Groq API: {str(e)}")
        return jsonify({"error": "Could not generate response. Please try again later."}), 500



@app.route('/api/ask_financial_question', methods=['POST'])
def ask_financial_question():
    data = request.json
    query = data.get('question')
    
    if not query:
        return jsonify({"error": "Question is required"}), 400
    
    try:
        prompt = f"""You are an AI assistant dedicated to empowering women in India with financial literacy. 
        Your user has asked the following question: "{query}". 
        
        Critically, ensure your answer is based on the LATEST information. 
        Prioritize real-time data obtained from a web search over general knowledge if there's a possibility of information being outdated.
        Please provide a clear, comprehensive, and accurate answer.
        If relevant to the query, search for and include links to helpful videos (e.g., from YouTube or other reputable sources) that can further explain the concepts. 
        Make sure the links are fully qualified URLs.
        Structure your response for easy readability. At the end of your response, list any web sources used for your answer."""
        
        response = google_client.models.generate_content( # Changed from google_client.models.generate_content
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[create_google_search_tool()]
            )
        )
        
        # Extract text and sources
        text = response.text
        # Assuming response.citations or similar attribute exists for grounding.
        # The previous summary mentioned map_grounding_chunks(response.citations)
        # For google.generativeai, grounding metadata is often in response.candidates[0].grounding_metadata.web_search_results
        # or response.candidates[0].citation_metadata.citation_sources
        # This part might need adjustment based on the actual response structure of the newer SDK.
        # For now, keeping the existing logic if map_grounding_chunks handles it.
        # If response.citations is not available, this will need to be updated.
        # A common way to get citations:
        citations = []
        if response.candidates and response.candidates[0].citation_metadata:
            citations = [source.uri for source in response.candidates[0].citation_metadata.citation_sources]
        
        sources = map_grounding_chunks(citations) # map_grounding_chunks might need to be adapted
        
        return jsonify({
            "text": text,
            "sources": sources
        })
        
    except Exception as e:
        logger.error(f"Gemini API error: {str(e)}")
        return jsonify({"error": "Failed to get financial advice. Please try again later."}), 500

# New endpoint for finding schemes
@app.route('/api/find_schemes', methods=['POST'])
def find_schemes():
    data = request.json
    details = data.get('details')
    
    if not details:
        return jsonify({"error": "Details are required"}), 400
    
    try:
        prompt = f"""You are an AI assistant helping women in India find relevant government and other beneficial schemes.
        A user has provided the following information about their needs, business, or situation: "{details}".

        Based on this information, please:
        1. Identify and list suitable schemes (government or other reputable organizations). Ensure this list is based on the MOST CURRENT information available via web search.
        2. For each scheme, provide a brief, up-to-date description.
        3. Explain how each scheme might be relevant to the user's provided details, using the latest details about the scheme.
        4. If available, provide direct links to the official scheme pages or information sources. Verify these links are current.
        
        Critically, your entire response MUST be based on the most current and relevant information found through web search. 
        Do not rely on potentially outdated general knowledge.
        Structure your response clearly. At the end of your response, list any web sources used for finding this information."""
        
        response = google_client.models.generate_content( # Changed from google_client.models.generate_content
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[create_google_search_tool()]
            )
        )
        
        # Extract text and sources
        text = response.text
        # Similar to ask_financial_question, citation handling might need review
        citations = []
        if response.candidates and response.candidates[0].citation_metadata:
            citations = [source.uri for source in response.candidates[0].citation_metadata.citation_sources]

        sources = map_grounding_chunks(citations) # map_grounding_chunks might need to be adapted
        
        return jsonify({
            "text": text,
            "sources": sources
        })
        
    except Exception as e:
        logger.error(f"Gemini API error: {str(e)}")
        return jsonify({"error": "Failed to find schemes. Please try again later."}), 500
    

if __name__ == '__main__':
    app.run(host='0.0.0.0')
