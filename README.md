# 🍌 Plantain: Your Smart AI Kitchen Assistant

Plantain is an intelligent, AI-powered kitchen assistant that takes the mental load out of cooking and grocery tracking. Instead of just chatting with a bot, Plantain features a highly interactive UI that automatically parses AI responses into beautiful, manageable widgets. It tracks your pantry, remembers your dietary preferences, generates recipes based *only* on what you have, and automatically updates your inventory when you cook!

## 💡 Why I Built This

My two cousins were having trouble figuring out what to cook in college. I've always loved cooking for my family, so I built Plantain to see if it could help them.

## 📋 User Survey

I surveyed friends and family across different demographics to decide which features to build:

* **Older respondents:** struggled with food waste and a lack of time.
* **Young adults / college students:** weren't confident in their skills and didn't know what to cook.

Resulting priorities:

* Use ingredients already in the user's pantry.
* Ease of use.
* User customization: if a user wants easier recipes or has a dietary preference, Plantain remembers that and tailors future recipes to them.

## 🤖 Why Not Just Use a Chatbot?

The question I kept coming back to: *what can this do that a normal AI chatbot can't?*

* **Running pantry state:** Chatbots don't reliably keep track of your ingredients. Plantain stores your pantry in a database, updates it as you shop, and deducts ingredients when you cook.
* **Persistent preferences:** Allergies, diets, and dislikes are saved across sessions.
* **Saved recipes that stay the same:** Favorites are stored exactly as generated, so they don't change when you pull them up later.
* **Built-in convenience:** Pantry `+`/`-` buttons and one-click favorite, copy, and rate, so you don't have to type everything out.

## AI Disclosure

This app was built in Visual Studio Code with the assistance of Claude. AI was used exclusively to write code; the concept, features, and UI/UX direction are my own.

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
* **AI Integration:** OpenAI API (`gpt-6-luna`) using Function Calling & JSON mode.

## 📁 Project Structure

| File | What it is |
| --- | --- |
| `app.py` | The whole backend: one Lambda handler that routes on the request's `action` field. |
| `index.html` | The whole frontend: auth, chat, and the pantry / recipe / favorites widgets. |
| `template.yaml` | AWS SAM template: Cognito user pool, API Gateway, and the Lambda function. |
| `samconfig.toml` | SAM deploy settings (stack name, region). |
| `requirements.txt` | Python dependencies for the Lambda. |

## 🏗️ Architecture

1. **AI router:** Each chat message goes to the OpenAI API along with a set of tools. The model decides whether to check or update the pantry, or save preferences, before it replies.
2. **Widget parsing:** The frontend scans the reply for `` ```pantry `` blocks and `<recipe>` tags and renders them as interactive widgets.
3. **Single endpoint:** Every request is a `POST` to one Lambda, and an `action` field routes it (chat, pantry buttons, ratings, favorites, feedback).
