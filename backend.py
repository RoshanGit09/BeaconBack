from flask import Flask, jsonify, render_template, request
from flask_cors import CORS, cross_origin
import asyncio
from bleak import BleakScanner
from threading import Thread, Lock
from pymongo import MongoClient
from groq import Groq
import json

app = Flask(__name__)
CORS(app)

# MongoDB Connection
uri = "mongodb+srv://twinnroshan:Roseshopping@cluster0.zf5b3.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(uri)
db = client['ShoppingSys']  
collection = db['UserData']
medical_collection = db['CustomerForms']  # Collection for medical records

# Initialize Groq client
groq_client = Groq(api_key="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")

TARGET_DEVICE_NAME = "MyBLEBeacon"
current_data = None
current_user_id = None  # Store the current user ID
data_lock = Lock()  # Lock for thread-safe access to current_data and current_user_id

def fetch_product_from_db(message):
    product = collection.find_one({"RACK": message})
    if product:
        return {key: value for key, value in product.items() if key != "_id"}
    return {"error": "Product not found"}

def fetch_user_medical_record(user_id):
    medical_record = medical_collection.find_one({"email": user_id})
    if medical_record:
        return {key: value for key, value in medical_record.items() if key != "_id"}
    return {"health_conditions": []}

def analyze_products_with_llm(products, medical_record):
    product_items = []
    for key, value in products.items():
        if key.startswith('Item-'):
            product_items.append(value)
    user_details = medical_record
    print(medical_record)

    prompt = f"""
Given a user with the following personal details:  
- Name: {user_details['name']}  
- Age: {user_details['age']}  
- Gender: {user_details['gender']}  
- Favorite Foods: {', '.join(user_details['favorite_foods'])}  
- Allergic Foods: {', '.join(user_details['allergic_foods'])}  
- Medical Conditions: {', '.join(user_details['medical_conditions'])}  
- Married: {user_details['married']}  
- Number of Children: {user_details['children']}  

Analyze the given products based on the user's profile and provide personalized recommendations. Consider factors such as:  
1. Age-related dietary needs  
2. Medical conditions and dietary restrictions  
3. Allergies and potential risks  
4. Parental responsibilities (if they have children, suggest suitable products for them)  
5. Favorite foods and potential preferences  

Here are the products for analysis:  
{product_items}

Sort these products from most recommended to least recommended based on the user's health and lifestyle.  
For each product, provide:  
- A recommendation status based on the user's profile it is not like only one product is being given highly recommended it is based on the user's profile, it can be given to multiple products.:  
  - "highly recommended"  
  - "recommended"  
  - "consume with caution"  
  - "not recommended"  
- A reason for the recommendation  
- A warning if the product is unsuitable  

Return the result as a JSON with the following structure:  

{{
    "sorted_products": [
        {{
            "name": "product name",
            "recommendation": "highly recommended" or "recommended" or "consume with caution" or "not recommended",
            "reason": "explanation",
            "warning": "warning message if applicable"
        }}
    ]
}}
"""

    try:
        messages = [
            {"role": "system", "content": "You are a health-conscious shopping assistant that helps users make informed decisions based on their medical conditions."},
            {"role": "user", "content": prompt}
        ]
        
        groq_response = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=messages
        )
        
        response_text = groq_response.choices[0].message.content
        
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            return json.loads(json_str)
        else:
            return {"error": "Could not extract JSON from LLM response"}
        
    except Exception as e:
        print(f"Error calling Groq LLM: {e}")
        return {"error": f"LLM analysis failed: {str(e)}"}

# Disable BLE scanning by removing the scan_ble task and setting a fixed email ID for /get_device

# Fixed email ID
FIXED_EMAIL = "finalcheck@gmail.com"

@app.route('/get_device', methods=['GET'])
@cross_origin()
def get_device():
    global current_user_id
    with data_lock:
        # Use the fixed email ID
        current_user_id = FIXED_EMAIL

        # Prepare the response data
        response_data = {"user_email": current_user_id}

        if current_data:
            response_data.update(current_data)

            # Perform analysis if product_info exists
            if 'product_info' in current_data and current_data['product_info']:
                if 'analyzed_products' not in current_data or not current_data['analyzed_products']:
                    medical_record = fetch_user_medical_record(current_user_id)
                    analysis_result = analyze_products_with_llm(current_data['product_info'], medical_record)
                    response_data['analyzed_products'] = analysis_result
                    current_data['analyzed_products'] = analysis_result
                    print(f"Product analyzed for user {current_user_id} via API endpoint")
        print(response_data)
        return jsonify(response_data)

@app.route('/clear_user', methods=['POST'])
@cross_origin()
def clear_user():
    global current_user_id, current_data
    with data_lock:
        current_user_id = None
        current_data = None
    
    return jsonify({"message": "User cleared successfully"})

@app.route('/')
def index():
    return render_template("index.html", device_data=current_data)

def main():
    app.run(host="0.0.0.0", port=8080, use_reloader=False)

if __name__ == "__main__":
    main()
