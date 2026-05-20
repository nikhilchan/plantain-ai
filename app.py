import json
import logging
import os
import pymysql
from openai import OpenAI

logger = logging.getLogger()
logger.setLevel(logging.INFO)

openai_api_key = os.environ.get("OPENAI_API_KEY")
db_host = os.environ.get("DB_HOST")
db_user = os.environ.get("DB_USER")
db_password = os.environ.get("DB_PASSWORD")
db_name = os.environ.get("DB_NAME")

openai_client = None
try:
    openai_client = OpenAI(api_key=openai_api_key)
except Exception as e:
    logger.error(f"FATAL: Failed to initialize OpenAI client: {e}", exc_info=True)

def get_db_connection():
    try:
        return pymysql.connect(
            host=db_host, user=db_user, password=db_password,
            database=db_name, connect_timeout=5
        )
    except pymysql.MySQLError as e:
        logger.error("FATAL: Could not connect to MySQL instance.", exc_info=True)
        raise e

def edit_pantry(user_id, ingredients):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pantry_text, id FROM ingredients WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            pantry_list = json.loads(result[0]) if result and result[0] else []
            pantry_id = result[1] if result else None
            
            for item in ingredients:
                name = item['name'].lower()
                quantity = item['quantity']
                unit = item['unit']
                action = item['action']
                category = item.get('category', 'Other')

                found = False
                for pantry_item in pantry_list:
                    if pantry_item.get('name') == name and pantry_item.get('unit') == unit:
                        if action == 'add':
                            if pantry_item.get('quantity') != 'infinite':
                                pantry_item['quantity'] = pantry_item.get('quantity', 0) + quantity
                        elif action == 'remove':
                            if pantry_item.get('quantity') != 'infinite':
                                pantry_item['quantity'] = max(0, pantry_item.get('quantity', 0) - quantity)
                            else:
                                pantry_item['quantity'] = 0 # Force remove infinite items
                        found = True
                        break
                
                if not found and action == 'add':
                    pantry_list.append({"name": name, "quantity": quantity, "unit": unit, "category": category})

            updated_pantry = [p for p in pantry_list if str(p.get('quantity')) == 'infinite' or p.get('quantity', 0) > 0]
            new_pantry_json = json.dumps(updated_pantry)
            
            if pantry_id:
                cursor.execute("UPDATE ingredients SET pantry_text = %s WHERE id = %s", (new_pantry_json, pantry_id))
            else:
                cursor.execute("INSERT INTO ingredients (user_id, pantry_text) VALUES (%s, %s)", (user_id, new_pantry_json))
            
            conn.commit()
            return "Pantry successfully updated."
    finally:
        conn.close()

def inquire_pantry(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pantry_text, food_preferences FROM ingredients WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            pantry_contents = result[0] if result and result[0] else "[]"
            food_preferences = result[1] if result and result[1] else "none"
            return json.dumps({"pantry": pantry_contents, "preferences": food_preferences})
    finally:
        conn.close()

def update_food_preferences(user_id, new_preferences):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE ingredients SET food_preferences = %s WHERE user_id = %s", (new_preferences, user_id))
            conn.commit()
            return "Preferences successfully updated."
    finally:
        conn.close()

def lambda_handler(event, context):
    cors_headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type,Authorization', 'Access-Control-Allow-Methods': 'OPTIONS,POST'}
    if event['httpMethod'] == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps({'message': 'CORS preflight successful'})}

    try:
        user_claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        user_email = user_claims.get('email')
        if not user_email:
            return {'statusCode': 403, 'headers': cors_headers, 'body': json.dumps({'error': 'User identity not found.'})}

        body = json.loads(event.get('body', '{}'))
        action = body.get('action', 'chat')

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users WHERE email = %s", (user_email,))
                user_record = cursor.fetchone()
                if not user_record:
                    cursor.execute("INSERT INTO users (email) VALUES (%s)", (user_email,))
                    conn.commit()
                    user_id = cursor.lastrowid
                else:
                    user_id = user_record[0]
        finally:
            conn.close()

        if action == 'update_pantry':
            item_name = body.get('name')
            change = body.get('change')
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT pantry_text, id FROM ingredients WHERE user_id = %s", (user_id,))
                    res = cursor.fetchone()
                    if res and res[0]:
                        pantry_list = json.loads(res[0])
                        for item in pantry_list:
                            if item.get('name') == item_name:
                                if change == 'remove':
                                    item['quantity'] = 0
                                elif str(item.get('quantity')) != 'infinite':
                                    item['quantity'] = max(0, item.get('quantity', 0) + int(change))
                                break
                        pantry_list = [p for p in pantry_list if str(p.get('quantity')) == 'infinite' or p.get('quantity', 0) > 0]
                        cursor.execute("UPDATE ingredients SET pantry_text = %s WHERE id = %s", (json.dumps(pantry_list), res[1]))
                        conn.commit()
            finally:
                conn.close()
            return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps({'status': 'success'})}

        if action == 'rate_recipe':
            recipe = body.get('recipe', '')
            summary = body.get('summary', 'Rated Recipe')
            rating = body.get('rating', 0)
            feedback = body.get('feedback', '')
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    sql = "INSERT INTO ratings (user_id, recipe, recipe_summary, user_rating, user_feedback) VALUES (%s, %s, %s, %s, %s)"
                    cursor.execute(sql, (user_id, recipe, summary, rating, feedback))
                    
                    cursor.execute("SELECT pantry_text, id FROM ingredients WHERE user_id = %s", (user_id,))
                    res = cursor.fetchone()
                    
                    if res and res[0] and recipe:
                        current_pantry_text = res[0]
                        pantry_id = res[1]
                        
                        deduction_prompt = f"""You are a hyper-accurate kitchen inventory calculator.
The user just cooked this recipe:
{recipe}

Their current pantry JSON is:
{current_pantry_text}

Calculate EXACTLY what to subtract from the pantry based on the recipe.
RULES:
1. Match the exact 'name' from the current pantry JSON.
2. Convert recipe measurements to match the exact 'unit' in the pantry (e.g., if recipe uses '1 cup milk' and pantry has 'ml', estimate and output 240).
3. If the recipe uses something like "1 medium onion" and the pantry tracks onions by "count", deduct 1.
4. DO NOT deduct items with quantity "infinite" or unit "staple" (like oils, salt, pepper).
5. Output ONLY valid JSON in this exact format: {{"deductions": [{{"name": "exact pantry item name", "quantity_to_subtract": 100}}]}}"""

                        ai_response = openai_client.chat.completions.create(
                            model="gpt-4.1-nano", 
                            response_format={ "type": "json_object" },
                            messages=[{"role": "system", "content": deduction_prompt}]
                        )
                        
                        deductions_data = json.loads(ai_response.choices[0].message.content)
                        deductions = deductions_data.get('deductions', [])
                        
                        pantry_list = json.loads(current_pantry_text)
                        for deduction in deductions:
                            d_name = deduction.get('name')
                            d_qty = deduction.get('quantity_to_subtract', 0)
                            
                            for item in pantry_list:
                                if item.get('name') == d_name and str(item.get('quantity')) != 'infinite':
                                    item['quantity'] = max(0, item.get('quantity', 0) - d_qty)
                                    break
                        
                        pantry_list = [p for p in pantry_list if str(p.get('quantity')) == 'infinite' or p.get('quantity', 0) > 0]
                        
                        cursor.execute("UPDATE ingredients SET pantry_text = %s WHERE id = %s", (json.dumps(pantry_list), pantry_id))

                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to deduct pantry items during rating: {e}", exc_info=True)
            finally:
                conn.close()
            return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps({'status': 'success'})}

        user_prompt = body.get('message')
        if not user_prompt:
             return {'statusCode': 400, 'headers': cors_headers, 'body': json.dumps({'error': "Message is required."})}

        chat_history = []
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT user_message, ai_response FROM chat_history WHERE user_id = %s AND created_at >= now() - interval 20 minute ORDER BY created_at DESC LIMIT 5"
                cursor.execute(sql, (user_id,))
                for record in reversed(cursor.fetchall()):
                    if record[0]: chat_history.append({"role": "user", "content": record[0]})
                    if record[1]: chat_history.append({"role": "assistant", "content": record[1]})
        finally:
            conn.close()
        
        system_prompt = """You are Plantain AI, an expert kitchen assistant. Your job is to act as an intelligent router and helpful assistant.

**UI WIDGET FORMATTING RULES (CRITICAL - ABSOLUTELY DO NOT IGNORE):**
Our interface automatically generates beautiful UI widgets ONLY if you format your text correctly. YOU MUST follow these rules strictly:

1. **SHOWING THE PANTRY:** If the user asks what is in their pantry, you MUST output the data as a raw JSON block wrapped in standard markdown triple backticks with the word `pantry` immediately after the backticks. 
   - YOU MUST NOT use a bulleted list (e.g., "- item").
   - DO NOT add conversational text before or after the JSON block (e.g. Do not say "Here is your pantry:"). Just output the JSON block.
   - Assign ONE of these categories to every item: "Produce", "Proteins", "Grains", "Dairy", "Spices/Oils", "Other".
   - For staples (like oils, salt, pepper, condiments), set `quantity` to the exact string `"infinite"` and `unit` to `"staple"`.
   Example EXACT output:
   ```pantry
   [
     {"name": "chicken breast", "quantity": 2, "unit": "count", "category": "Proteins"},
     {"name": "olive oil", "quantity": "infinite", "unit": "staple", "category": "Spices/Oils"}
   ]
   ```

2. **GENERATING RECIPES:** If you generate a recipe, you MUST wrap the ENTIRE recipe text (title, ingredients, instructions) inside `<recipe>` and `</recipe>` tags. 
   - Format the recipe beautifully using standard Markdown inside the tags.
   - DO NOT ask the user for a rating or feedback; our UI automatically attaches an interactive rating widget.
   Example EXACT output:
   <recipe>
   # Lemon Herb Chicken
   **Ingredients:**
   * 2 chicken breasts
   * 1 tbsp olive oil
   
   **Instructions:**
   1. Heat oil in a pan.
   2. Cook chicken until golden.
   </recipe>

**General Guidelines:**
- Update preferences first if asked.
- Inquire pantry to check ingredients before suggesting recipes.
- Only suggest recipes using ingredients they actually have + common household staples. Convert imperial to metric.
"""
        
        messages = [{"role": "system", "content": system_prompt}] + chat_history + [{"role": "user", "content": user_prompt}]
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "edit_pantry",
                    "description": """Updates the user's pantry inventory. 

**CRITICAL RULE: CLARIFY VAGUE QUANTITIES FIRST.**
Before calling this tool, you must ensure every ingredient has a specific numerical quantity and a standard unit ('count', 'g', or 'ml'). 

1. If the user uses vague terms (e.g., "some," "a few," "a can," "a bag," "a bunch"), **DO NOT call this tool.** 2. Instead, ask the user to clarify those specific items (e.g., "How many grams are in that can?").
3. Only invoke this tool once you have precise data for every item requested.

**Staples:** For common oils and seasonings, use quantity `0` and unit `staple` to mark them as infinite.
**Metric Conversion:** Convert all non-metric weight/volume (lbs, oz, cups) to 'g' or 'ml' before calling.""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ingredients": {
                                "type": "array",
                                "description": "List of ingredient modifications.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "The name of the ingredient (e.g., 'onion')."},
                                        "quantity": {"type": "number", "description": "The numerical amount. Use 0 for infinite staples."},
                                        "unit": {"type": "string", "enum": ["count", "g", "ml", "staple"], "description": "The unit of measurement."},
                                        "action": {"type": "string", "enum": ["add", "remove"], "description": "Whether to add to or subtract from the pantry."},
                                        "category": {"type": "string", "enum": ["Produce", "Proteins", "Grains", "Dairy", "Spices/Oils", "Other"], "description": "The food category."}
                                    },
                                    "required": ["name", "quantity", "unit", "action", "category"]
                                }
                            }
                        },
                        "required": ["ingredients"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "inquire_pantry",
                    "description": "Fetches the raw JSON of the user's pantry and food preferences. Call this first if you need to know what they have.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_food_preferences",
                    "description": "Updates the user's long-term food preferences or allergies based on their statement.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "new_preferences": {"type": "string", "description": "The complete, updated, comma-separated list of the user's preferences."}
                        },
                        "required": ["new_preferences"]
                    }
                }
            }
        ]
        available_tools = {"edit_pantry": edit_pantry, "inquire_pantry": inquire_pantry, "update_food_preferences": update_food_preferences}

        for _ in range(5):
            response = openai_client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if not tool_calls:
                break

            messages.append(response_message.model_dump())

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_to_call = available_tools.get(function_name)
                function_args = json.loads(tool_call.function.arguments)
                function_response = function_to_call(user_id=user_id, **function_args)
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                })
        
        final_response = response.choices[0].message.content

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO chat_history (user_id, user_message, ai_response) VALUES (%s, %s, %s)"
                cursor.execute(sql, (user_id, user_prompt, final_response))
                conn.commit()
        finally:
            conn.close()

        return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps({'response': final_response})}

    except Exception as e:
        logger.error(f"An unexpected error occurred in the main handler: {e}", exc_info=True)
        return {'statusCode': 500, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': json.dumps({'error': 'An internal server error occurred.'})}