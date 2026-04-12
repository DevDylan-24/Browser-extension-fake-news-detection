# FactGuard AI — Fake News Detection Browser Extension

A Google Chrome browser extension that analyses the credibility of web pages in real time using a machine learning model, rule-based NLP heuristics, and AI-generated image detection.

Link to Github repository: https://github.com/DevDylan-24/Browser-extension-fake-news-detection

---

## Project Structure

```
factguard-ai/
│
├── popup/
│   ├── popup.html          # Extension sidebar UI
│   ├── popup.css           # Styles (dark theme, inline SVG icons)
│   └── popup.js            # Frontend logic and API communication
│
├── models/
│   │── NLP_large_model.pkl # Pre-trained fake news detection model
│   ├── __init__.py         # Empty file — marks directory as a Python package
│   ├── user.py             # User class (registration, login, password hashing)
│   └── history.py          # HistoryManager class (scan persistence)
│
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
│
├── background.js           # Chrome service worker (MV3)
├── content.js              # DOM content and image extractor
├── manifest.json           # Chrome extension manifest (v3)
│
├── server.py               # Flask backend server
├── config.py               # Configuration loader (reads from .env)
├── .env                    # Credentials — DO NOT commit to git (see setup below)
├── .env.example            # Template showing required environment variables
└── requirements.txt        # Python dependencies

    
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | 3.12 recommended |
| Google Chrome | Any recent | Extension uses Manifest V3 |
| MongoDB Atlas account | Free tier (M0) | Cloud database |
| SightEngine account | Free tier | AI image detection API credentials|

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/factguard-ai.git
cd factguard-ai
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Then open `.env` and set the following values:

```env
# MongoDB Atlas connection string
# Get this from: Atlas Dashboard → Connect → Drivers → Python
MONGO_URI=mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/

# Secret key for signing JWT tokens — use a long random string
# Generate one with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-secret-key-here

# SightEngine API credentials
# Get these from: https://dashboard.sightengine.com/api-credentials
SIGHTENGINE_API_USER=your_api_user_number
SIGHTENGINE_API_SECRET=your_api_secret_key
```


### 4. Set up MongoDB Atlas

1. Go to [https://cloud.mongodb.com](https://cloud.mongodb.com) and sign up or log in.
2. Create a free **M0** cluster (any cloud provider and region).
3. Under **Database Access**, create a database user with a username and password.
4. Under **Network Access**, add your IP address (or `0.0.0.0/0` during development).
5. Under **Database → Connect → Drivers**, copy the connection string and paste it as `MONGO_URI` in your `.env` file (replacing `<username>` and `<password>`).

The two required collections (`users` and `scan_history`) are created **automatically** on first use — no manual setup needed.

### 5. Place the ML model

Put your trained model file in the following location:

```
factguard-ai/models/NLP_large_model.pkl
```

This is the scikit-learn pipeline model used for fake news classification. The server loads it at startup via `pickle.load()`.

### 6. Create the models package init file

```bash
touch models/__init__.py
```

This empty file tells Python to treat the `models/` directory as a package, allowing `from models.user import User` to work.

---

## Running the Backend Server

From the project root directory, start the Flask server:

```bash
python -B server.py
```

You should see:

```
Server is running on http://localhost:5000
 * Running on http://127.0.0.1:5000
```

The server must be running before you use the extension. It exposes the following endpoints:

| Method | Endpoint | Auth required | Description |
|---|---|---|---|
| `POST` | `/register` | No | Create a new user account |
| `POST` | `/login` | No | Authenticate and receive a JWT token |
| `POST` | `/predict` | Optional | Analyse page text and images |
| `GET` | `/history` | Yes | Retrieve 5 most recent scans |
| `POST` | `/analyse-image` | Yes | Check an uploaded image for AI generation |

---

## Loading the Extension in Chrome

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** using the toggle in the top-right corner.
3. Click **Load unpacked**.
4. Select the root folder of this project (the folder containing `manifest.json`).
5. The FactGuard AI extension will appear in your extensions list.
6. Pin it to the toolbar by clicking the puzzle piece icon and pressing the pin next to FactGuard AI.

> **Note:** Any time you edit the extension files (HTML, CSS, JS), click the **refresh icon** on the extension card at `chrome://extensions/` to reload the changes.

---

## Using the Extension

### Guest (not logged in)

- Click the extension icon in the toolbar to open the sidebar.
- Click **Analyse This Page** to scan the current page's credibility.
- A score between 0–100% is shown along with signals explaining the result.
- Scans are not saved without an account.

### Registered user

1. Click **Sign Up** to create an account (name, email, password).
2. Password must be at least 8 characters, contain one uppercase letter and one number.
3. After logging in, click **Analyse This Page** to scan and automatically save results.
4. Click **Dashboard** to view:
   - Your most recent scan with score, signals and article summary.
   - History of your 5 most recent scans — click any item to view full details.
   - AI Media Detector — toggle on and upload an image to check if it is AI-generated.

### Image analysis during page scans

- In the Dashboard, toggle **Image Analysis** to **On** before scanning a page.
- The extension will automatically check up to 2 article images using the SightEngine API.
- This uses API credits — keep the toggle **Off** during testing to conserve them.

---

## API Credentials

### SightEngine (AI image detection)

1. Sign up at [https://sightengine.com](https://sightengine.com).
2. The free tier provides 2,000 operations per month.
3. Find your `API User` and `API Secret` at [https://dashboard.sightengine.com/api-credentials](https://dashboard.sightengine.com/api-credentials).
4. Add both values to your `.env` file.

---

## Security Notes

- Passwords are hashed with SHA-256 + an application-level salt. For production, replace with `bcrypt`.
- JWT tokens expire after 24 hours.
- All credentials are loaded from `.env` and never hardcoded.
- Add `.env` to your `.gitignore` to prevent accidental credential exposure.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Extension shows "Server unreachable" | Make sure `python server.py` is running and accessible on port 5000 |
| "Could not extract page content" | Some pages block content scripts (e.g. Chrome Web Store pages, PDF viewer). Try a regular news article |
| Icons not appearing in the extension | Clear the extension cache: go to `chrome://extensions/`, click the refresh icon on FactGuard AI |
| MongoDB connection error | Check your `MONGO_URI` in `.env`, verify IP whitelist in Atlas Network Access, and confirm your database user credentials |
| `ModuleNotFoundError: models` | Ensure `models/__init__.py` exists. Run `touch models/__init__.py` from the project root |
| SightEngine returns errors | Verify `SIGHTENGINE_API_USER` and `SIGHTENGINE_API_SECRET` are correct in `.env` and you have remaining credits |
| Very high credibility scores on fake news | Ensure you are using `model.predict_proba([text])[0][1]` (index 1 = fake class) in `server.py` |
