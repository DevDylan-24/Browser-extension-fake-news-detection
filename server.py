from flask import Flask, request, jsonify
import pickle
import re
import math
from collections import Counter
from urllib.request import urlopen
from urllib.parse import quote_plus
from urllib.error import URLError
import json

app = Flask(__name__)

# Load trained model
model = pickle.load(open("models/NLP_large_model.pkl", "rb"))

# ---------------------------------------------------------------------------
# EMOTIONAL / SENSATIONALIST LANGUAGE
# ---------------------------------------------------------------------------
EMOTIONAL_WORDS = {
    "shocking", "unbelievable", "bombshell", "explosive", "outrage", "outrageous",
    "disgusting", "terrifying", "horrifying", "scandalous", "devastating", "exposed",
    "breaking", "urgent", "alert", "panic", "chaos", "catastrophe", "disaster",
    "miracle", "stunning", "incredible", "insane", "insanity", "radical", "extreme",
    "evil", "criminal", "corrupt", "traitor", "treasonous", "wicked", "vile",
    "they don't want you to know", "wake up", "the truth about", "what they're hiding",
    "must see", "share before deleted", "censored", "banned", "suppressed",
    "destroy", "obliterate", "annihilate", "savage", "brutal", "slam", "blast",
    "eviscerates", "rips apart", "demolishes", "exposes", "reveals the truth",
}

CLICKBAIT_PATTERNS = [
    r"you won't believe",
    r"what happens next",
    r"this one (weird|simple|crazy|secret)",
    r"doctors hate",
    r"they don't want you to",
    r"share before (?:it'?s? )?deleted",
    r"(?:the )?truth (?:about|behind|they)",
    r"(?:\d+) (?:reasons|things|ways|secrets|facts)",
    r"is this the end of",
    r"nobody is talking about",
    r"mainstream media (?:won't|refuses to|is hiding)",
]

# ---------------------------------------------------------------------------
# UPPERCASE RATIO  
# ---------------------------------------------------------------------------
def uppercase_ratio(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    uppers = sum(1 for c in letters if c.isupper())
    return uppers / len(letters)

# ---------------------------------------------------------------------------
# EXCLAMATION / QUESTION MARK DENSITY
# ---------------------------------------------------------------------------
def punctuation_density(text):
    words = len(text.split()) or 1
    bangs = text.count("!")
    questions = text.count("?")
    return (bangs + questions) / words

# ---------------------------------------------------------------------------
# EMOTIONAL LANGUAGE SCORE
# ---------------------------------------------------------------------------
def emotional_language_score(text):
    lower = text.lower()
    words = re.findall(r"\b\w+\b", lower)
    word_set = set(words)
    hit_words = EMOTIONAL_WORDS & word_set
    hit_count = sum(lower.count(w) for w in hit_words)

    clickbait_hits = sum(
        1 for p in CLICKBAIT_PATTERNS if re.search(p, lower)
    )

    word_count = len(words) or 1
    emotion_density = hit_count / word_count          # 0–1 
    normalised = min(1.0, emotion_density * 20 + clickbait_hits * 0.15)
    return normalised, sorted(hit_words)[:5], clickbait_hits

# ---------------------------------------------------------------------------
# FACTUAL CONSISTENCY HEURISTICS
# ---------------------------------------------------------------------------
def factual_consistency_score(text):
    """
    Heuristics that correlate with factual, well-sourced writing:
    - Presence of numbers / statistics
    - Quoted speech (indicates attribution)
    - Hedging language (according to, said, reported, confirmed)
    - Named entity density (rough proxy via capitalised multi-word phrases)
    """
    lower = text.lower()
    words = re.findall(r"\b\w+\b", lower)
    word_count = len(words) or 1

    # Statistics / numbers
    numbers = re.findall(r"\b\d+(?:[.,]\d+)?(?:\s?(?:percent|%|million|billion|thousand))?\b", text)
    number_density = min(1.0, len(numbers) / (word_count / 50))

    # Attribution phrases
    attribution_phrases = [
        "according to", "said", "stated", "confirmed", "reported",
        "announced", "told", "wrote", "published", "cited", "study",
        "research", "survey", "data", "evidence", "source", "official",
    ]
    attribution_count = sum(lower.count(p) for p in attribution_phrases)
    attribution_density = min(1.0, attribution_count / (word_count / 30))

    # Quoted speech
    quotes = re.findall(r'["\u201c\u201d].{10,200}?["\u201c\u201d]', text)
    quote_score = min(1.0, len(quotes) / 3)

    # Capitalised proper noun phrases (rough NE proxy)
    proper_nouns = re.findall(r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b', text)
    proper_density = min(1.0, len(proper_nouns) / (word_count / 20))

    composite = (
        number_density     * 0.25 +
        attribution_density * 0.40 +
        quote_score        * 0.20 +
        proper_density     * 0.15
    )
    return composite

# ---------------------------------------------------------------------------
# WRITING FORMALITY / STRUCTURE
# ---------------------------------------------------------------------------
def formality_score(text):
    """
    Formal writing tends to have:
    - Longer average sentence length (but not too long)
    - Lower ratio of first-person pronouns
    - Lower ratio of colloquial contractions
    """
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    if not sentences:
        return 0.5

    avg_sent_len = sum(len(s.split()) for s in sentences) / len(sentences)
    # Ideal formal sentence: 15–25 words
    sent_score = 1.0 - min(1.0, abs(avg_sent_len - 20) / 20)

    lower = text.lower()
    words = re.findall(r"\b\w+\b", lower)
    word_count = len(words) or 1

    first_person = sum(1 for w in words if w in {"i", "me", "my", "we", "our", "us"})
    fp_ratio = first_person / word_count

    contractions = len(re.findall(r"\b\w+n't\b|\b(?:i'm|you're|they're|we're|it's|don't|can't|won't|isn't|aren't)\b", lower))
    contraction_ratio = contractions / word_count

    formality = (
        sent_score        * 0.40 +
        (1 - fp_ratio * 10) * 0.30 +
        (1 - contraction_ratio * 15) * 0.30
    )
    return max(0.0, min(1.0, formality))

# ---------------------------------------------------------------------------
# SOURCE / URL EXTRACTION
# ---------------------------------------------------------------------------
def extract_urls(text):
    return re.findall(r'https?://[^\s\)\]>,\"\']+', text)

# ---------------------------------------------------------------------------
# CLAIM EXTRACTION  (simple heuristic: declarative sentences with named entities)
# ---------------------------------------------------------------------------
def extract_claims(text, max_claims=3):
    """
    Pull out short declarative sentences that look like factual claims:
    - Contain a capitalised proper-noun phrase
    - Are not questions
    - Are between 6 and 35 words
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    claims = []
    for s in sentences:
        s = s.strip()
        words = s.split()
        if 6 <= len(words) <= 35 and not s.endswith("?"):
            if re.search(r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)*\b', s):
                claims.append(s)
        if len(claims) >= max_claims:
            break
    return claims

# ---------------------------------------------------------------------------
# SOURCE VERIFICATION via DuckDuckGo Instant Answer API (no key needed)
# ---------------------------------------------------------------------------
def verify_claims_online(claims):
    """
    For each claim, query the DuckDuckGo Instant Answer API and check
    whether a result is returned. This is a lightweight proxy for
    'is this claim findable / corroborated online'.
    Returns list of dicts: { claim, found, snippet }
    """
    results = []
    for claim in claims:
        # Truncate claim for query (first 80 chars)
        query = claim[:80]
        encoded = quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1&no_html=1"
        found = False
        snippet = ""
        try:
            with urlopen(url, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                abstract = data.get("Abstract", "").strip()
                related  = data.get("RelatedTopics", [])
                if abstract:
                    found = True
                    snippet = abstract[:160]
                elif related:
                    first = related[0]
                    text_val = first.get("Text", "") if isinstance(first, dict) else ""
                    if text_val:
                        found = True
                        snippet = text_val[:160]
        except (URLError, Exception):
            # Network unavailable or timeout — mark as unverified, don't crash
            pass
        results.append({"claim": claim, "found": found, "snippet": snippet})
    return results

# ---------------------------------------------------------------------------
# BUILD SIGNALS LIST FOR THE EXTENSION
# ---------------------------------------------------------------------------
def build_signals(text, probability_fake):
    signals = []
    credibility = 1.0 - probability_fake

    # 1. Emotional language
    emotion_score, emotion_words, clickbait_count = emotional_language_score(text)
    if emotion_score > 0.5:
        detail = f"Words: {', '.join(emotion_words)}" if emotion_words else ""
        signals.append({
            "type": "bad",
            "label": "High Emotional Language",
            "detail": f"Strong sensationalist or emotionally charged wording detected. {detail}".strip(),
        })
    elif emotion_score > 0.2:
        signals.append({
            "type": "warn",
            "label": "Some Emotional Language",
            "detail": "Moderate use of emotionally charged vocabulary — common in opinion or tabloid content.",
        })
    else:
        signals.append({
            "type": "ok",
            "label": "Neutral Language Tone",
            "detail": "Writing tone is measured and largely free of sensationalist language.",
        })

    if clickbait_count > 0:
        signals.append({
            "type": "bad",
            "label": "Clickbait Patterns Detected",
            "detail": f"{clickbait_count} clickbait phrase(s) found — a common trait of misleading content.",
        })

    # 2. Uppercase ratio
    up_ratio = uppercase_ratio(text)
    if up_ratio > 0.15:
        signals.append({
            "type": "bad",
            "label": "Excessive Capitalisation",
            "detail": f"{round(up_ratio * 100)}% of letters are uppercase — often used for emphasis or alarm.",
        })

    # 3. Punctuation density
    punct = punctuation_density(text)
    if punct > 0.05:
        signals.append({
            "type": "warn",
            "label": "Heavy Use of ! / ?",
            "detail": "Frequent exclamation or question marks suggest an emotionally driven writing style.",
        })

    # 4. Factual consistency
    fact_score = factual_consistency_score(text)
    if fact_score > 0.55:
        signals.append({
            "type": "ok",
            "label": "Good Factual Consistency",
            "detail": "Text contains statistics, attribution phrases and proper noun references consistent with factual reporting.",
        })
    elif fact_score > 0.25:
        signals.append({
            "type": "warn",
            "label": "Low Factual Consistency",
            "detail": "Limited use of statistics, attributions or named sources — harder to independently verify.",
        })
    else:
        signals.append({
            "type": "bad",
            "label": "Very Low Factual Consistency",
            "detail": "Virtually no statistics, citations or attributed sources found in the text.",
        })

    # 5. Writing formality
    formality = formality_score(text)
    if formality > 0.6:
        signals.append({
            "type": "ok",
            "label": "Formal Writing Style",
            "detail": "Sentence structure and vocabulary align with professional journalistic standards.",
        })
    elif formality > 0.35:
        signals.append({
            "type": "warn",
            "label": "Informal Writing Style",
            "detail": "Writing uses colloquial language, contractions or short sentences more typical of opinion content.",
        })
    else:
        signals.append({
            "type": "bad",
            "label": "Very Informal / Unprofessional Style",
            "detail": "Heavy use of first-person, contractions and short choppy sentences — atypical of fact-based journalism.",
        })

    # 6. URLs in body
    urls = extract_urls(text)
    if urls:
        signals.append({
            "type": "ok",
            "label": f"{len(urls)} Source Link(s) Present",
            "detail": f"Article contains hyperlinks which may reference supporting sources.",
        })
    else:
        signals.append({
            "type": "warn",
            "label": "No Source Links Found",
            "detail": "No hyperlinks detected in the article body — claims cannot be traced to external sources.",
        })

    # 7. Claim verification
    claims = extract_claims(text, max_claims=3)
    if claims:
        verification = verify_claims_online(claims)
        verified_count   = sum(1 for v in verification if v["found"])
        unverified_count = len(verification) - verified_count

        if verified_count == len(verification):
            signals.append({
                "type": "ok",
                "label": "Key Claims Corroborated Online",
                "detail": f"All {verified_count} extracted claim(s) returned matching results from independent sources.",
            })
        elif verified_count > 0:
            signals.append({
                "type": "warn",
                "label": "Some Claims Unverified",
                "detail": f"{verified_count} of {len(verification)} claim(s) found online; {unverified_count} could not be corroborated.",
            })
        else:
            signals.append({
                "type": "bad",
                "label": "Claims Not Found Online",
                "detail": f"None of the {len(verification)} extracted claim(s) could be matched to independent online sources.",
            })
    else:
        signals.append({
            "type": "warn",
            "label": "No Clear Claims Extracted",
            "detail": "Could not identify clear factual claims to verify — the text may be too vague or opinion-based.",
        })

    return signals

# ---------------------------------------------------------------------------
# GENERATE SUMMARY
# ---------------------------------------------------------------------------
def build_summary(credibility, emotion_score, fact_score, formality, verified_claims, total_claims):
    score = round(credibility * 100)
    parts = []

    if score >= 70:
        parts.append("This article shows a low likelihood of containing fake or misleading content.")
    elif score >= 40:
        parts.append("This article contains mixed signals and warrants caution.")
    else:
        parts.append("This article shows strong indicators of fake or misleading content.")

    if emotion_score > 0.4:
        parts.append("The writing relies heavily on emotional and sensationalist language.")
    if fact_score < 0.3:
        parts.append("Very few factual anchors — statistics, citations or attributed sources — were found.")
    if formality < 0.35:
        parts.append("The writing style is informal and unprofessional.")
    if total_claims > 0 and verified_claims == 0:
        parts.append("None of the key claims could be corroborated by independent sources.")
    elif total_claims > 0 and verified_claims < total_claims:
        parts.append(f"Only {verified_claims} of {total_claims} key claim(s) were corroborated online.")

    if score >= 70:
        parts.append("Always verify with additional sources before sharing.")
    elif score >= 40:
        parts.append("Cross-check key claims with established news outlets before sharing.")
    else:
        parts.append("Do not share without thorough independent verification.")

    return " ".join(parts)

# ---------------------------------------------------------------------------
# ROUTE
# ---------------------------------------------------------------------------
@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.json
        text = data["text"]

        # Model prediction
        prediction        = model.predict([text])[0]
        probability_fake  = float(model.predict_proba([text])[0][0])
        credibility       = 1.0 - probability_fake

        # Text analysis
        emotion_score, emotion_words, clickbait_count = emotional_language_score(text)
        fact_score    = factual_consistency_score(text)
        formality     = formality_score(text)
        claims        = extract_claims(text, max_claims=3)
        verification  = verify_claims_online(claims)
        verified_count = sum(1 for v in verification if v["found"])

        signals = build_signals(text, probability_fake)
        summary = build_summary(credibility, emotion_score, fact_score, formality, verified_count, len(claims))

        return jsonify({
            "prediction":         int(prediction),
            "probability":        probability_fake,   # fake probability (0=real, 1=fake)
            "signals":            signals,
            "summary":            summary,
            "verified_claims":    verification,
            "analysis": {
                "emotion_score":  round(emotion_score, 3),
                "fact_score":     round(fact_score, 3),
                "formality":      round(formality, 3),
                "uppercase_ratio":round(uppercase_ratio(text), 3),
                "punct_density":  round(punctuation_density(text), 3),
                "url_count":      len(extract_urls(text)),
                "clickbait_hits": clickbait_count,
            },
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Server is running on http://localhost:5000")
    app.run(port=5000)
