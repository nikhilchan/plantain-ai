# 🍌 Plantain: Your Smart AI Kitchen Assistant

Plantain is an intelligent, AI-powered kitchen assistant that takes the mental load out of cooking and grocery tracking. Instead of just chatting with a bot, Plantain features a highly interactive UI that automatically parses AI responses into beautiful, manageable widgets. It tracks your pantry, remembers your dietary preferences, generates recipes based *only* on what you have, and automatically updates your inventory when you cook!

This project was built in Visual Studio Code. I used AI assistance solely for coding purposes.

## ✨ Key Features

* **Interactive Pantry Management:** Tell Plantain what you bought ("I got 1 lb of chicken breast") and it updates your pantry. Ask to see it, and you get a categorized, interactive pantry widget.
  * Easily adjust quantities with `+` and `-` buttons that instantly sync with the backend.
  * **Original Units:** Items are stored in the units you give them (1 lb stays 1 lb). Spelling variants like "lbs" and "pounds" are merged.
  * **Assumed Staples:** Salt, pepper, cooking oils, and water are always assumed to be on hand, so they're never tracked or shown in the pantry.

* **Smart Recipe Generation:** Ask for a meal, and Plantain will generate a recipe formatted beautifully in Markdown, complete with a one-click "Copy" button.

* **Favorite Recipes:** Tap the heart on any recipe to save it. Open **My Favorites** from the sidebar to browse saved recipes, fully formatted.

* **Hyper-Accurate Pantry Deduction:** When you finish a recipe and leave a star rating, Plantain performs a "stealth calculation." It cross-references the recipe ingredients with your current pantry JSON, calculates the exact mathematical deductions (handling unit conversions automatically), and removes the used ingredients from your database.

* **User Preferences:** Remembers your allergies, diets, and dislikes across sessions.

* **In-App Feedback:** A "Give Feedback" button sends ideas and bug reports straight to the database.

* **Secure Authentication:** Fully integrated with AWS Cognito for secure sign-up, login, and email verification.

## 🛠️ Tech Stack

**Frontend:**
* HTML5, Vanilla JavaScript, Tailwind CSS
* `marked.js` (for parsing AI-generated Markdown into beautiful UI)
* AWS Cognito SDK (for User Authentication)
* Hosted on AWS S3 & CloudFront

**Backend:**
* **Serverless Functions:** AWS Lambda (Python), deployed with AWS SAM
* **API Routing:** AWS API Gateway with a Cognito authorizer
* **Database:** Amazon RDS (MySQL)
* **AI Integration:** OpenAI API (`gpt-4.1-nano`) using Function Calling & JSON mode.

## 📁 Project Structure

| File | What it is |
| --- | --- |
| `app.py` | The whole backend: one Lambda handler that routes on the request's `action` field. |
| `index.html` | The whole frontend: auth, chat, and the pantry / recipe / favorites widgets. |
| `template.yaml` | AWS SAM template: Cognito user pool, API Gateway, and the Lambda function. |
| `samconfig.toml` | SAM deploy settings (stack name, region). |
| `requirements.txt` | Python dependencies for the Lambda. |

## 🏗️ Architecture & How It Works

1. **The Router AI:** When a user sends a message, the backend passes the prompt to the OpenAI API with a strict set of available "Tools" (functions).
2. **Function Calling:** The AI acts as a router. If the user says "I bought 3 apples", the AI calls the `edit_pantry` database function. If the user asks for a recipe, it calls `inquire_pantry` first to check inventory, then generates the recipe.
3. **Smart UI Parsing:** The frontend doesn't just display raw text. It intercepts the AI's response, looks for specific markdown tags (like ```pantry or <recipe>), and dynamically builds interactive HTML widgets on the screen.

Every request is a `POST` to `/chat` with a JSON body. The `action` field decides what happens:

| `action` | Purpose |
| --- | --- |
| `chat` (default) | Send `message` to the AI router. |
| `update_pantry` | Pantry widget `+` / `-` buttons. |
| `rate_recipe` | Save a star rating and deduct the recipe's ingredients from the pantry. |
| `set_favorite` / `list_favorites` | Save or remove a favorite recipe / list favorites. |
| `feedback` | Save in-app feedback. |

## 🚀 Setup & Deployment

Because this project relies heavily on AWS infrastructure, local setup requires configuring several cloud services:

1. **AWS RDS (MySQL):** Set up a database with these tables (columns listed are the ones the code uses):
   * `users`: `user_id` (auto-increment primary key), `email`
   * `ingredients`: `id`, `user_id`, `pantry_text` (pantry JSON), `food_preferences`
   * `ratings`: `user_id`, `recipe`, `recipe_summary`, `user_rating`, `user_feedback`
   * `chat_history`: `user_id`, `user_message`, `ai_response`, `created_at`
   * `feedback`: `user_id`, `feedback_text`
   * `favorites`:
     ```sql
     CREATE TABLE favorites (
       id INT AUTO_INCREMENT PRIMARY KEY,
       user_id INT NOT NULL,  -- must match the exact type of users.user_id
       title VARCHAR(255),
       recipe_text MEDIUMTEXT NOT NULL,
       recipe_hash CHAR(64) NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       UNIQUE KEY uniq_user_recipe (user_id, recipe_hash),
       FOREIGN KEY (user_id) REFERENCES users(user_id)
     );
     ```
2. **Deploy the backend with AWS SAM:** run `sam build && sam deploy`. This creates the Cognito User Pool, the API Gateway, and the Lambda function, and prints the `UserPoolId`, `UserPoolClientId`, and `ApiEndpoint`.
3. **Lambda Environment Variables:** In the Lambda console, add:
   * `OPENAI_API_KEY`
   * `DB_HOST`
   * `DB_USER`
   * `DB_PASSWORD`
   * `DB_NAME`

   The Lambda must also be able to reach your RDS instance over the network.
4. **Frontend Configuration:**
   * In `index.html`, update `poolData` with your Cognito `UserPoolId` and `ClientId`.
   * Update the `API_ENDPOINT` variable with your `ApiEndpoint`.
5. **Hosting:** Upload `index.html` to a public-facing AWS S3 Bucket (optionally behind CloudFront)!
