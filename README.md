# 🍌 Plantain: Your Smart AI Kitchen Assistant

Plantain is an intelligent, AI-powered kitchen assistant that takes the mental load out of cooking and grocery tracking. Instead of just chatting with a bot, Plantain features a highly interactive UI that automatically parses AI responses into beautiful, manageable widgets. It tracks your pantry, remembers your dietary preferences, generates recipes based *only* on what you have, and automatically updates your inventory when you cook!

## ✨ Key Features

* **Interactive Pantry Management:** The AI analyzes your chat and generates a categorized, interactive pantry widget.
  * Easily adjust quantities with `+` and `-` buttons that instantly sync with the backend.
  * **Infinite Staples:** Items like salt, pepper, and olive oil are tracked as "infinite" so the AI knows you always have them on hand.

* **Smart Recipe Generation:** Ask for a meal, and Plantain will generate a recipe formatted beautifully in Markdown, complete with a one-click "Copy" button.

* **Hyper-Accurate Pantry Deduction:** When you finish a recipe and leave a star rating, Plantain performs a "stealth calculation." It cross-references the recipe ingredients with your current pantry JSON, calculates the exact mathematical deductions (handling unit conversions automatically), and removes the used ingredients from your database.

* **User Preferences:** Remembers your allergies, diets, and dislikes across sessions.

* **Secure Authentication:** Fully integrated with AWS Cognito for secure sign-up, login, and email verification.

## 🛠️ Tech Stack

**Frontend:**
* HTML5, Vanilla JavaScript, Tailwind CSS
* `marked.js` (for parsing AI-generated Markdown into beautiful UI)
* AWS Cognito SDK (for User Authentication)
* Hosted on AWS S3 & CloudFront

**Backend:**
* **Serverless Functions:** AWS Lambda (Python)
* **API Routing:** AWS API Gateway
* **Database:** Amazon RDS (MySQL)
* **AI Integration:** OpenAI API (`gpt-4.1-nano`) using Function Calling & JSON mode.

## 🏗️ Architecture & How It Works

1. **The Router AI:** When a user sends a message, the backend passes the prompt to the OpenAI API with a strict set of available "Tools" (functions).
2. **Function Calling:** The AI acts as a router. If the user says "I bought 3 apples", the AI calls the `edit_pantry` database function. If the user asks for a recipe, it calls `inquire_pantry` first to check inventory, then generates the recipe.
3. **Smart UI Parsing:** The frontend doesn't just display raw text. It intercepts the AI's response, looks for specific markdown tags (like ```pantry or <recipe>), and dynamically builds interactive HTML widgets on the screen.

## 🚀 Setup & Deployment

Because this project relies heavily on AWS infrastructure, local setup requires configuring several cloud services:

1. **AWS RDS (MySQL):** Set up a database with `users`, `ingredients` (stores pantry JSON and preferences), `ratings`, and `chat_history` tables.
2. **AWS Cognito:** Create a User Pool for authentication and grab your `UserPoolId` and `ClientId`.
3. **AWS Lambda & API Gateway:** Deploy `backend.py` to AWS Lambda.
   * Add the following Environment Variables to your Lambda function:
     * `OPENAI_API_KEY`
     * `DB_HOST`
     * `DB_USER`
     * `DB_PASSWORD`
     * `DB_NAME`
   * Route an API Gateway POST method to this Lambda function and enable CORS.
4. **Frontend Configuration:**
   * In `index.html`, update the `poolData` with your Cognito credentials.
   * Update the `API_ENDPOINT` variable with your API Gateway URL.
5. **Hosting:** Upload `index.html` to a public-facing AWS S3 Bucket!