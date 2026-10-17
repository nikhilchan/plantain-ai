import hashlib
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

# Always assumed on hand: never stored in, shown in, or deducted from the pantry.
STAPLES = {"salt", "pepper", "black pepper", "olive oil", "vegetable oil", "cooking oil", "water"}

def clean_pantry(pantry_list):
    # Drops staples (including legacy "infinite" entries) and used-up items; rounds away float noise.
    cleaned = [p for p in pantry_list
               if str(p.get('name', '')).lower() not in STAPLES
               and isinstance(p.get('quantity'), (int, float)) and p['quantity'] > 0]
    for p in cleaned:
        p['quantity'] = round(p['quantity'], 2)
    return cleaned

# Spelling variants collapse to one unit so "1 lb" + "2 lbs" merge. Units are never converted.
UNIT_ALIASES = {
    "lbs": "lb", "pound": "lb", "pounds": "lb",
    "ounce": "oz", "ounces": "oz",
    "gram": "g", "grams": "g",
    "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "milliliter": "ml", "milliliters": "ml",
    "liter": "l", "liters": "l",
    "cups": "cup", "tablespoon": "tbsp", "tablespoons": "tbsp", "teaspoon": "tsp", "teaspoons": "tsp",
}

def normalize_unit(unit):
    unit = str(unit).strip().lower().rstrip('.')
    return UNIT_ALIASES.get(unit, unit)

def recipe_title(recipe_text):
    # First non-empty line of the recipe Markdown, minus heading/bold markers.
    for line in recipe_text.splitlines():
        line = line.strip().lstrip('#').strip().strip('*').strip()
        if line:
            return line[:255]
    return "Untitled Recipe"

def edit_pantry(user_id, ingredients):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pantry_text, id FROM ingredients WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            pantry_list = clean_pantry(json.loads(result[0])) if result and result[0] else []
            pantry_id = result[1] if result else None

            skipped_staples = []
            for item in ingredients:
                name = item['name'].lower()
                if name in STAPLES:
                    skipped_staples.append(name)
                    continue
                quantity = item['quantity']
                unit = normalize_unit(item['unit'])
                action = item['action']
                category = item.get('category', 'Other')

                found = False
                for pantry_item in pantry_list:
                    if pantry_item.get('name') == name and pantry_item.get('unit') == unit:
                        if action == 'add':
                            pantry_item['quantity'] += quantity
                        elif action == 'remove':
                            pantry_item['quantity'] = max(0, pantry_item['quantity'] - quantity)
                        found = True
                        break

                if not found and action == 'add':
                    pantry_list.append({"name": name, "quantity": quantity, "unit": unit, "category": category})

            updated_pantry = clean_pantry(pantry_list)
            new_pantry_json = json.dumps(updated_pantry)
            
            if pantry_id:
                cursor.execute("UPDATE ingredients SET pantry_text = %s WHERE id = %s", (new_pantry_json, pantry_id))
            else:
                cursor.execute("INSERT INTO ingredients (user_id, pantry_text) VALUES (%s, %s)", (user_id, new_pantry_json))
            
            conn.commit()
            if skipped_staples:
                return f"Pantry successfully updated. Not tracked (staples are always assumed on hand): {', '.join(skipped_staples)}."
            return "Pantry successfully updated."
    finally:
        conn.close()

def inquire_pantry(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pantry_text, food_preferences FROM ingredients WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            pantry_contents = json.dumps(clean_pantry(json.loads(result[0]))) if result and result[0] else "[]"
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
            item_unit = body.get('unit')
            change = body.get('change')
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT pantry_text, id FROM ingredients WHERE user_id = %s", (user_id,))
                    res = cursor.fetchone()
                    if res and res[0]:
                        pantry_list = clean_pantry(json.loads(res[0]))
                        for item in pantry_list:
                            # The same ingredient can exist in more than one unit, so match on both.
                            if item.get('name') == item_name and (item_unit is None or item.get('unit') == item_unit):
                                item['quantity'] = max(0, item['quantity'] + int(change))
                                break
                        pantry_list = clean_pantry(pantry_list)
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
                        current_pantry_text = json.dumps(clean_pantry(json.loads(res[0])))
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
4. Only deduct items that appear in the pantry JSON. Ignore recipe ingredients that are not in it (e.g. salt, pepper, oil).
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
                                if item.get('name') == d_name:
                                    item['quantity'] = max(0, item['quantity'] - d_qty)
                                    break

                        pantry_list = clean_pantry(pantry_list)
                        
                        cursor.execute("UPDATE ingredients SET pantry_text = %s WHERE id = %s", (json.dumps(pantry_list), pantry_id))

                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to deduct pantry items during rating: {e}", exc_info=True)
            finally:
                conn.close()
            return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps({'status': 'success'})}

        if action == 'feedback':
            feedback_text = (body.get('feedback') or '').strip()
            if not feedback_text:
                return {'statusCode': 400, 'headers': cors_headers, 'body': json.dumps({'error': "Feedback text is required."})}
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO feedback (user_id, feedback_text) VALUES (%s, %s)", (user_id, feedback_text))
                    conn.commit()
            finally:
                conn.close()
            return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps({'status': 'success'})}

        if action == 'set_favorite':
            recipe = (body.get('recipe') or '').strip()
            if not recipe:
                return {'statusCode': 400, 'headers': cors_headers, 'body': json.dumps({'error': "Recipe is required."})}
            favorited = bool(body.get('favorited'))
            recipe_hash = hashlib.sha256(recipe.encode('utf-8')).hexdigest()
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    if favorited:
                        cursor.execute(
                            "INSERT INTO favorites (user_id, title, recipe_text, recipe_hash) VALUES (%s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE id = id",
                            (user_id, recipe_title(recipe), recipe, recipe_hash))
                    else:
                        cursor.execute("DELETE FROM favorites WHERE user_id = %s AND recipe_hash = %s", (user_id, recipe_hash))
                    conn.commit()
            finally:
                conn.close()
            return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps({'favorited': favorited})}

        if action == 'list_favorites':
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id, title, recipe_text, created_at FROM favorites WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
                    favorites = [
                        {'id': r[0], 'title': r[1], 'recipe': r[2], 'created_at': r[3].isoformat() if r[3] else None}
                        for r in cursor.fetchall()
                    ]
            finally:
                conn.close()
            return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps({'favorites': favorites})}

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
   - Only list items returned by `inquire_pantry`. Never list staples (see below).
   - Copy each item's `quantity` and `unit` exactly as stored. Never convert units (e.g. keep 1 "lb" as 1 "lb").
   Example EXACT output:
   ```pantry
   [
     {"name": "chicken breast", "quantity": 2, "unit": "count", "category": "Proteins"},
     {"name": "rice", "quantity": 500, "unit": "g", "category": "Grains"}
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
- Only suggest recipes using ingredients they actually have + the staples below. Convert imperial to metric.

**Staples:** The user always has these, and they are not tracked in the pantry: """ + ", ".join(sorted(STAPLES)) + """.
- Use them freely in recipes. Never add them with `edit_pantry` or show them in the pantry widget.
"""
        
        messages = [{"role": "system", "content": system_prompt}] + chat_history + [{"role": "user", "content": user_prompt}]
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "edit_pantry",
                    "description": """Updates the user's pantry inventory. 

**CRITICAL RULE: CLARIFY VAGUE QUANTITIES FIRST.**
Before calling this tool, you must ensure every ingredient has a specific numerical quantity and a unit.

1. If the user uses vague terms (e.g., "some," "a few," "a can," "a bag," "a bunch"), **DO NOT call this tool.** 2. Instead, ask the user to clarify those specific items (e.g., "How many grams are in that can?").
3. Only invoke this tool once you have precise data for every item requested.

**Staples:** Do not include staples (""" + ", ".join(sorted(STAPLES)) + """); they are always assumed on hand.
**Units:** Keep the user's original unit. NEVER convert (e.g. "1 lb chicken breast" is quantity 1, unit "lb", not 454 g). Use short unit names ("lb", "oz", "g", "kg", "ml", "l", "cup", "tbsp", "tsp") and "count" for whole items (e.g. "3 apples").
**Removing:** When removing an item already in the pantry, use the same unit it is stored in.""",
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
                                        "quantity": {"type": "number", "description": "The numerical amount."},
                                        "unit": {"type": "string", "description": "The unit exactly as the user gave it, unconverted (e.g. 'lb', 'oz', 'g', 'cup'), or 'count' for whole items."},
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