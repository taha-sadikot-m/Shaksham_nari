# app.py (updated backend)
from flask import Flask, render_template, request, jsonify, session
import pymongo
import uuid
from groq import Groq
import logging
import os
from google import genai
from google.genai import types



import json

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this for production

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB setup
MONGO_URI = "mongodb://localhost:27017/"
db_client = pymongo.MongoClient(MONGO_URI)
db = db_client["investment_bot"]
users_collection = db["users"]

# Groq setup
GROQ_API_KEY = "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"
client = Groq(api_key=GROQ_API_KEY)

# Gemini setup
GEMINI_API_KEY = "AIzaSyAT01e62IH8PNrE6LqtsJRLhd5Cb0h2Bv0" 
# Initialize the Gemini client
google_client = client = genai.Client(api_key=GEMINI_API_KEY)

GEMINI_MODEL_TEXT = 'gemini-2.5-flash-preview-04-17'




# Define the Google Search tool (can be reused)
def create_google_search_tool():
    return types.Tool(
        google_search=types.GoogleSearch()
    )

# For dynamic retrieval configuration
def create_dynamic_search_tool(threshold=0.3):
    return types.Tool(
        google_search=types.GoogleSearchRetrieval(
            dynamic_retrieval_config=types.DynamicRetrievalConfig(
                dynamic_threshold=threshold
            )
        )
    )



def get_user(user_id):
    return users_collection.find_one({"_id": user_id})

def save_user_data(user_id, data):
    users_collection.update_one({"_id": user_id}, {"$set": data}, upsert=True)

def reset_user_data(user_id):
    users_collection.delete_one({"_id": user_id})

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
        # Remove MongoDB _id field for JSON serialization
        if '_id' in user:
            del user['_id']
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



def map_gemini_grounding_to_frontend(candidate):
    """
    Extracts web grounding sources from the Gemini API response candidate
    and formats them for the frontend.
    Frontend expects: [{ "web": { "uri": "...", "title": "..." } }, ...]
    """
    frontend_sources = []
    if candidate and hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
        # In Python SDK, grounding information is in `grounding_attributions`.
        web_sources_dict = {} # To store unique URIs and their titles

        if hasattr(candidate.grounding_metadata, 'grounding_attributions'):
            for attribution in candidate.grounding_metadata.grounding_attributions:
                if hasattr(attribution, 'web') and attribution.web and hasattr(attribution.web, 'uri'):
                    uri = attribution.web.uri
                    # Use provided title, fallback to URI if title is missing/empty
                    title = attribution.web.title if hasattr(attribution.web, 'title') and attribution.web.title else uri
                    if uri not in web_sources_dict: # Store unique sources
                        web_sources_dict[uri] = {"uri": uri, "title": title}
                    # If title was generic (URI) and a better one is found for the same URI
                    elif web_sources_dict[uri]["title"] == uri and title != uri:
                         web_sources_dict[uri]["title"] = title
        
        for uri_key in web_sources_dict:
            frontend_sources.append({"web": web_sources_dict[uri_key]})
            
    return frontend_sources




# Financial questions endpoint (using Gemini)
@app.route('/api/ask_financial_question', methods=['POST'])
def ask_financial_question_endpoint():
    

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
        
        

        response = google_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[create_google_search_tool()]
            )
        )
        
        text_response = response.text
        
        sources = []
        if response.candidates and len(response.candidates) > 0:
            sources = map_gemini_grounding_to_frontend(response.candidates[0])
        
        print(text_response )

        
        

        # Ensure the response key is "text" for the main answer
        return jsonify({
            "text": text_response,
            "sources": sources
        })
        
    except Exception as e:
        logger.error(f"Gemini API error in ask_financial_question: {str(e)}")
        logger.exception("Full traceback for ask_financial_question:")
        return jsonify({"error": "Failed to get an answer from the AI. Please try again."}), 500


# Scheme finder endpoint (using Gemini)
@app.route('/api/find_schemes', methods=['POST'])
def find_schemes_endpoint():
    

    data = request.json
    details = data.get('details') # Changed from 'question' to 'details' as per your frontend
    
    if not details:
        return jsonify({"error": "Details for scheme search are required"}), 400
    
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
        
        

        response = google_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[create_google_search_tool()],
            )
        )
        
        text_response = response.text
        
        sources = []
        if response.candidates and len(response.candidates) > 0:
            sources = map_gemini_grounding_to_frontend(response.candidates[0])
        
        print(text_response )
        # Ensure the response key is "text"

        

        return jsonify({
            "text": text_response,
            "sources": sources
        })
        
    except Exception as e:
        logger.error(f"Gemini API error in find_schemes: {str(e)}")
        logger.exception("Full traceback for find_schemes:")
        return jsonify({"error": "Failed to find schemes from the AI. Please try again."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0')
