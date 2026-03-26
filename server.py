from flask import Flask, request, jsonify
import pickle
import re
from urllib.request import urlopen, Request
from urllib.parse import quote_plus
from urllib.error import URLError
import json

app = Flask(__name__)
model = pickle.load(open("models/NLP_large_model.pkl", "rb"))


# ─────────────────────────────────────────────────────────────
# TEXT UTILITIES
# ─────────────────────────────────────────────────────────────

def split_sentences(text):
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw if len(s.strip()) > 10]


def truncate_words(s, max_chars=130):
    """
    Truncate at a word boundary so we never cut mid-word.
    Also strips any trailing partial word caused by max_chars.
    """
    s = s.strip()
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    # Walk back to last whitespace
    last_space = cut.rfind(' ')
    if last_space > max_chars // 2:
        cut = cut[:last_space]
    return cut.rstrip(',:;( ') + "…"


def clean_sentence_for_summary(s, max_chars=200):
    """
    Return a complete sentence — never cut mid-word or mid-sentence.
    If s is longer than max_chars, truncate at the last full stop within range.
    """
    s = s.strip()
    if len(s) <= max_chars:
        return s
    # Try to end at a sentence boundary within the limit
    window = s[:max_chars]
    last_period = max(window.rfind('.'), window.rfind('!'), window.rfind('?'))
    if last_period > max_chars // 2:
        return s[:last_period + 1]
    # Fall back to word boundary
    last_space = window.rfind(' ')
    if last_space > max_chars // 2:
        return window[:last_space].rstrip(',:;( ') + "…"
    return window + "…"


# ─────────────────────────────────────────────────────────────
# SNIPPET DEDUPLICATION
# ─────────────────────────────────────────────────────────────

class SnippetTracker:
    """
    Ensures no two signals share the same snippet sentence.
    Call .pick(candidates) with an ordered list of candidate strings;
    returns the first one not already used, or "" if all are used.
    """
    def __init__(self):
        self._used = set()

    def pick(self, candidates):
        for c in candidates:
            c = c.strip()
            if not c:
                continue
            # Normalise for comparison (strip punctuation/case)
            key = re.sub(r'\W+', ' ', c).strip().lower()[:80]
            if key not in self._used:
                self._used.add(key)
                return c
        return ""

    def add(self, s):
        if s:
            key = re.sub(r'\W+', ' ', s).strip().lower()[:80]
            self._used.add(key)


# ─────────────────────────────────────────────────────────────
# EMOTIONAL LANGUAGE
# ─────────────────────────────────────────────────────────────

EMOTIONAL_WORDS = {
    "shocking", "unbelievable", "bombshell", "explosive", "outrage", "outrageous",
    "disgusting", "terrifying", "horrifying", "scandalous", "devastating", "exposed",
    "breaking", "urgent", "alert", "panic", "chaos", "catastrophe", "disaster",
    "miracle", "stunning", "incredible", "insane", "insanity", "radical", "extreme",
    "evil", "criminal", "corrupt", "traitor", "treasonous", "wicked", "vile",
    "must see", "censored", "banned", "suppressed", "destroy", "obliterate",
    "annihilate", "savage", "brutal", "slam", "blast", "eviscerates", "exposes",
}

CLICKBAIT_PATTERNS = [
    r"you won't believe",
    r"what happens next",
    r"this one (?:weird|simple|crazy|secret)",
    r"doctors hate",
    r"they don't want you to",
    r"share before (?:it'?s? )?deleted",
    r"(?:the )?truth (?:about|behind|they)",
    r"(?:\d+) (?:reasons|things|ways|secrets|facts)",
    r"is this the end of",
    r"nobody is talking about",
    r"mainstream media (?:won't|refuses to|is hiding)",
]


def emotional_language_score(text):
    lower = text.lower()
    words = re.findall(r"\b\w+\b", lower)
    word_set = set(words)
    hit_words = EMOTIONAL_WORDS & word_set
    hit_count = sum(lower.count(w) for w in hit_words)
    clickbait_hits = sum(1 for p in CLICKBAIT_PATTERNS if re.search(p, lower))
    word_count = len(words) or 1
    normalised = min(1.0, (hit_count / word_count) * 20 + clickbait_hits * 0.15)
    return normalised, sorted(hit_words)[:5], clickbait_hits


def find_emotional_candidates(text, hit_words, clickbait_hits):
    """Return ordered list of candidate snippets for emotional signal."""
    candidates = []
    lower_text = text.lower()
    sentences = split_sentences(text)

    # 1. Clickbait match in context
    for pattern in CLICKBAIT_PATTERNS:
        m = re.search(pattern, lower_text)
        if m:
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 90)
            candidates.append(truncate_words(text[start:end]))
            break

    # 2. Sentences containing emotional words
    for word in hit_words:
        for s in sentences:
            if word in s.lower():
                candidates.append(truncate_words(s))
                break

    # 3. Fallback to first sentence that is NOT purely factual
    for s in sentences:
        if not re.search(r'\b\d+\b', s):
            candidates.append(truncate_words(s))
            break

    return candidates


def find_neutral_candidates(text):
    """Return calm, factual sentences as evidence of neutral tone."""
    sentences = split_sentences(text)
    lower = text.lower()
    candidates = []
    for s in sentences:
        ls = s.lower()
        # No emotional words, has attribution or numbers
        has_emotional = any(w in ls for w in EMOTIONAL_WORDS)
        has_factual = any(p in ls for p in ATTRIBUTION_PHRASES) or bool(re.search(r'\b\d+', s))
        if not has_emotional and has_factual and 10 <= len(s.split()) <= 35:
            candidates.append(truncate_words(s))
    # Also add first sentence as general fallback
    if sentences:
        candidates.append(truncate_words(sentences[0]))
    return candidates


# ─────────────────────────────────────────────────────────────
# UPPERCASE / PUNCTUATION
# ─────────────────────────────────────────────────────────────

def uppercase_ratio(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def find_uppercase_candidates(text):
    sentences = split_sentences(text)
    scored = []
    for s in sentences:
        letters = [c for c in s if c.isalpha()]
        if letters:
            ratio = sum(1 for c in letters if c.isupper()) / len(letters)
            scored.append((ratio, s))
    scored.sort(reverse=True)
    return [truncate_words(s) for _, s in scored[:3]]


def punctuation_density(text):
    words = len(text.split()) or 1
    return (text.count("!") + text.count("?")) / words


def find_punctuation_candidates(text):
    sentences = split_sentences(text)
    scored = [(s.count("!") + s.count("?"), s) for s in sentences]
    scored.sort(reverse=True)
    return [truncate_words(s) for cnt, s in scored[:3] if cnt > 0]


# ─────────────────────────────────────────────────────────────
# FACTUAL CONSISTENCY
# ─────────────────────────────────────────────────────────────

ATTRIBUTION_PHRASES = [
    "according to", "said", "stated", "confirmed", "reported",
    "announced", "told", "wrote", "published", "cited", "study",
    "research", "survey", "data", "evidence", "source", "official",
]


def factual_consistency_score(text):
    lower = text.lower()
    words = re.findall(r"\b\w+\b", lower)
    word_count = len(words) or 1
    numbers = re.findall(
        r"\b\d+(?:[.,]\d+)?(?:\s?(?:percent|%|million|billion|thousand))?\b", text
    )
    number_density = min(1.0, len(numbers) / (word_count / 50))
    attribution_count = sum(lower.count(p) for p in ATTRIBUTION_PHRASES)
    attribution_density = min(1.0, attribution_count / (word_count / 30))
    quotes = re.findall(r'["\u201c\u201d].{10,200}?["\u201c\u201d]', text)
    quote_score = min(1.0, len(quotes) / 3)
    proper_nouns = re.findall(r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b', text)
    proper_density = min(1.0, len(proper_nouns) / (word_count / 20))
    return (
        number_density * 0.25
        + attribution_density * 0.40
        + quote_score * 0.20
        + proper_density * 0.15
    )


def find_factual_candidates(text, good=True):
    sentences = split_sentences(text)
    candidates = []
    if good:
        for s in sentences:
            ls = s.lower()
            if any(p in ls for p in ATTRIBUTION_PHRASES) or re.search(r'\b\d+', s):
                candidates.append(truncate_words(s))
    else:
        for s in sentences:
            ls = s.lower()
            if (not any(p in ls for p in ATTRIBUTION_PHRASES)
                    and not re.search(r'\b\d+', s)
                    and len(s.split()) > 8):
                candidates.append(truncate_words(s))
    if not candidates and sentences:
        candidates.append(truncate_words(sentences[0]))
    return candidates


# ─────────────────────────────────────────────────────────────
# WRITING FORMALITY
# ─────────────────────────────────────────────────────────────

CONTRACTION_RE = re.compile(
    r"\b\w+n't\b|\b(?:i'm|you're|they're|we're|it's|don't|can't|won't|isn't|aren't)\b"
)
FIRST_PERSON_RE = re.compile(r"\b(?:i|me|my|we|our|us)\b")


def formality_score(text):
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    if not sentences:
        return 0.5
    avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
    sent_score = 1.0 - min(1.0, abs(avg_len - 20) / 20)
    lower = text.lower()
    words = re.findall(r"\b\w+\b", lower)
    word_count = len(words) or 1
    fp = sum(1 for w in words if w in {"i", "me", "my", "we", "our", "us"})
    contr = len(CONTRACTION_RE.findall(lower))
    return max(
        0.0,
        min(
            1.0,
            sent_score * 0.40
            + (1 - fp / word_count * 10) * 0.30
            + (1 - contr / word_count * 15) * 0.30,
        ),
    )


def find_informal_candidates(text):
    sentences = split_sentences(text)
    candidates = []
    for s in sentences:
        ls = s.lower()
        if CONTRACTION_RE.search(ls) or FIRST_PERSON_RE.search(ls):
            candidates.append(truncate_words(s))
    if not candidates and sentences:
        candidates.append(truncate_words(min(sentences, key=lambda x: len(x.split()))))
    return candidates


def find_formal_candidates(text):
    sentences = split_sentences(text)
    candidates = []
    for s in sentences:
        if 15 <= len(s.split()) <= 40:
            candidates.append(truncate_words(s))
    if not candidates and sentences:
        candidates.append(truncate_words(sentences[0]))
    return candidates


# ─────────────────────────────────────────────────────────────
# URLS & CLAIMS
# ─────────────────────────────────────────────────────────────

def extract_urls(text):
    return re.findall(r'https?://[^\s\)\]>,\"\']+', text)


def extract_claims(text, max_claims=3):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    claims = []
    for s in sentences:
        s = s.strip()
        if 8 <= len(s.split()) <= 30 and not s.endswith("?"):
            if re.search(r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)*\b', s):
                claims.append(s)
        if len(claims) >= max_claims:
            break
    return claims


# ─────────────────────────────────────────────────────────────
# CLAIM VERIFICATION  (DuckDuckGo — improved matching)
# ─────────────────────────────────────────────────────────────

def _ddg_query(query, timeout=4):
    """
    Query DuckDuckGo Instant Answer API.
    Returns (found: bool, snippet: str).
    Checks Abstract, Answer, RelatedTopics, and Results.
    """
    encoded = quote_plus(query[:100])
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1&no_html=1&skip_disambig=1"
    try:
        req = Request(url, headers={"User-Agent": "FactGuardExtension/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Priority 1: direct answer or abstract
        for key in ("Answer", "Abstract"):
            val = data.get(key, "").strip()
            if val:
                return True, val[:180]

        # Priority 2: related topics
        for item in data.get("RelatedTopics", [])[:3]:
            if isinstance(item, dict):
                txt = item.get("Text", "").strip()
                if txt and len(txt) > 20:
                    return True, txt[:180]

        # Priority 3: results list (DDG sometimes returns these)
        for item in data.get("Results", [])[:2]:
            if isinstance(item, dict):
                txt = item.get("Text", "").strip()
                if txt and len(txt) > 20:
                    return True, txt[:180]

    except (URLError, Exception):
        pass
    return False, ""


def verify_claims_online(claims):
    """
    Try the full claim first, then fall back to a shorter keyword query
    if the first attempt returns nothing — improves recall significantly.
    """
    results = []
    for claim in claims:
        found, snippet = _ddg_query(claim)

        if not found:
            # Extract key noun phrase (first 5 words) as fallback query
            keywords = " ".join(claim.split()[:6])
            found, snippet = _ddg_query(keywords)

        results.append({"claim": truncate_words(claim, 120), "found": found, "snippet": snippet})
    return results


# ─────────────────────────────────────────────────────────────
# SIGNAL TYPE CALIBRATION
# ─────────────────────────────────────────────────────────────

def calibrate_signals(signals, credibility):
    """
    After generating signals independently, re-balance their types so that
    the overall colour distribution matches the model's credibility score.

    Rules:
    - credibility >= 0.70: at most 1 signal can be "bad"; bias toward "ok"/"warn"
    - credibility >= 0.40: balanced; no change by default
    - credibility <  0.40: at most 1 signal can be "ok"; bias toward "warn"/"bad"

    We only soften/harden signals that are borderline — signals with a strong
    individual reason (e.g. uppercase_ratio very high) are left unchanged.
    The model probability is the ground truth; signals explain it.
    """
    if credibility >= 0.70:
        # Downgrade "bad" → "warn" if more than 1 bad signal
        bad_count = sum(1 for s in signals if s["type"] == "bad")
        for s in signals:
            if bad_count > 1 and s["type"] == "bad":
                s["type"] = "warn"
                bad_count -= 1

    elif credibility < 0.40:
        # Downgrade "ok" → "warn" if more than 1 ok signal
        ok_count = sum(1 for s in signals if s["type"] == "ok")
        for s in signals:
            if ok_count > 1 and s["type"] == "ok":
                s["type"] = "warn"
                ok_count -= 1

    return signals


# ─────────────────────────────────────────────────────────────
# EXTRACTIVE CONTENT SUMMARY  (word-boundary safe)
# ─────────────────────────────────────────────────────────────

def build_content_summary(text, max_sentences=3):
    sentences = split_sentences(text)
    if not sentences:
        return ""
    if len(sentences) <= max_sentences:
        return " ".join(clean_sentence_for_summary(s) for s in sentences)

    total = len(sentences)
    scored = []
    for i, s in enumerate(sentences):
        ls = s.lower()
        wc = len(s.split())
        score = (
            (1.0 if 12 <= wc <= 35 else max(0.0, 1.0 - abs(wc - 20) / 20)) * 0.25
            + (1.0 if re.search(r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b', s) else 0.0) * 0.25
            + (1.0 if any(p in ls for p in ATTRIBUTION_PHRASES) else 0.0) * 0.20
            + (1.0 if re.search(r'\b\d+', s) else 0.0) * 0.15
            + (1.0 if i / total < 0.30 else 0.5) * 0.15
        )
        scored.append((score, i, s))

    top = sorted(scored, reverse=True)[:max_sentences]
    top.sort(key=lambda x: x[1])
    return " ".join(clean_sentence_for_summary(s) for _, _, s in top)


# ─────────────────────────────────────────────────────────────
# BUILD SIGNALS
# ─────────────────────────────────────────────────────────────

def build_signals(text, probability_fake, credibility):
    signals = []
    tracker = SnippetTracker()

    emotion_score, emotion_words, clickbait_count = emotional_language_score(text)
    fact_score = factual_consistency_score(text)
    formality  = formality_score(text)

    # 1. Emotional language
    if emotion_score > 0.5:
        detail = f"Matched words: {', '.join(emotion_words)}." if emotion_words else ""
        snippet = tracker.pick(find_emotional_candidates(text, emotion_words, clickbait_count))
        signals.append({
            "type": "bad", "label": "High Emotional Language",
            "detail": f"Strong sensationalist or emotionally charged wording detected. {detail}".strip(),
            "snippet": snippet,
        })
    elif emotion_score > 0.2:
        snippet = tracker.pick(find_emotional_candidates(text, emotion_words, clickbait_count))
        signals.append({
            "type": "warn", "label": "Some Emotional Language",
            "detail": "Moderate use of emotionally charged vocabulary — common in opinion or tabloid content.",
            "snippet": snippet,
        })
    else:
        # Neutral tone — show an example of calm writing from the text
        snippet = tracker.pick(find_neutral_candidates(text))
        signals.append({
            "type": "ok", "label": "Neutral Language Tone",
            "detail": "Writing tone is measured and largely free of sensationalist language.",
            "snippet": snippet,
        })

    # 2. Clickbait
    if clickbait_count > 0:
        lower = text.lower()
        cb_candidates = []
        for p in CLICKBAIT_PATTERNS:
            m = re.search(p, lower)
            if m:
                start = max(0, m.start() - 20)
                cb_candidates.append(truncate_words(text[start:min(len(text), m.end() + 80)]))
        snippet = tracker.pick(cb_candidates)
        signals.append({
            "type": "bad", "label": "Clickbait Patterns Detected",
            "detail": f"{clickbait_count} clickbait phrase(s) found — a common trait of misleading content.",
            "snippet": snippet,
        })

    # 3. Uppercase ratio
    up_ratio = uppercase_ratio(text)
    if up_ratio > 0.15:
        snippet = tracker.pick(find_uppercase_candidates(text))
        signals.append({
            "type": "bad", "label": "Excessive Capitalisation",
            "detail": f"{round(up_ratio * 100)}% of letters are uppercase — often used for emphasis or alarm.",
            "snippet": snippet,
        })

    # 4. Punctuation density
    punct = punctuation_density(text)
    if punct > 0.05:
        snippet = tracker.pick(find_punctuation_candidates(text))
        signals.append({
            "type": "warn", "label": "Heavy Use of ! / ?",
            "detail": "Frequent exclamation or question marks suggest an emotionally driven writing style.",
            "snippet": snippet,
        })

    # 5. Factual consistency
    if fact_score > 0.55:
        snippet = tracker.pick(find_factual_candidates(text, good=True))
        signals.append({
            "type": "ok", "label": "Good Factual Consistency",
            "detail": "Text contains statistics, attribution phrases and proper noun references consistent with factual reporting.",
            "snippet": snippet,
        })
    elif fact_score > 0.25:
        snippet = tracker.pick(find_factual_candidates(text, good=False))
        signals.append({
            "type": "warn", "label": "Low Factual Consistency",
            "detail": "Limited use of statistics, attributions or named sources — harder to independently verify.",
            "snippet": snippet,
        })
    else:
        snippet = tracker.pick(find_factual_candidates(text, good=False))
        signals.append({
            "type": "bad", "label": "Very Low Factual Consistency",
            "detail": "Virtually no statistics, citations or attributed sources found in the text.",
            "snippet": snippet,
        })

    # 6. Writing formality
    if formality > 0.6:
        snippet = tracker.pick(find_formal_candidates(text))
        signals.append({
            "type": "ok", "label": "Formal Writing Style",
            "detail": "Sentence structure and vocabulary align with professional journalistic standards.",
            "snippet": snippet,
        })
    elif formality > 0.35:
        snippet = tracker.pick(find_informal_candidates(text))
        signals.append({
            "type": "warn", "label": "Informal Writing Style",
            "detail": "Writing uses colloquial language, contractions or short sentences more typical of opinion content.",
            "snippet": snippet,
        })
    else:
        snippet = tracker.pick(find_informal_candidates(text))
        signals.append({
            "type": "bad", "label": "Very Informal / Unprofessional Style",
            "detail": "Heavy use of first-person, contractions and short choppy sentences — atypical of fact-based journalism.",
            "snippet": snippet,
        })

    # 7. Source links
    urls = extract_urls(text)
    url_snippet = truncate_words(urls[0], 100) if urls else ""
    if url_snippet:
        tracker.add(url_snippet)
    signals.append({
        "type": "ok" if urls else "warn",
        "label": f"{len(urls)} Source Link(s) Present" if urls else "No Source Links Found",
        "detail": "Article contains hyperlinks which may reference supporting sources." if urls
                  else "No hyperlinks detected in the article body — claims cannot be traced to external sources.",
        "snippet": url_snippet,
    })

    # 8. Claim verification
    claims = extract_claims(text, max_claims=3)
    if claims:
        verification   = verify_claims_online(claims)
        verified_count = sum(1 for v in verification if v["found"])
        unverified     = len(verification) - verified_count

        # Use each claim as a candidate; pick one not yet used
        claim_candidates = [truncate_words(c, 120) for c in claims]
        snippet = tracker.pick(claim_candidates)

        if verified_count == len(verification):
            sig = ("ok",   "Key Claims Corroborated Online",
                   f"All {verified_count} extracted claim(s) returned matching results from independent sources.")
        elif verified_count > 0:
            sig = ("warn", "Some Claims Unverified",
                   f"{verified_count} of {len(verification)} claim(s) found online; {unverified} could not be corroborated.")
        else:
            sig = ("warn", "Claims Could Not Be Verified",
                   f"None of the {len(verification)} claim(s) could be matched via DuckDuckGo. "
                   "This may reflect limited DDG coverage, not necessarily false claims.")
        signals.append({"type": sig[0], "label": sig[1], "detail": sig[2], "snippet": snippet})
    else:
        signals.append({
            "type": "warn", "label": "No Clear Claims Extracted",
            "detail": "Could not identify clear factual claims to verify — text may be too vague or opinion-based.",
            "snippet": "",
        })

    # Re-balance signal colours to align with model credibility score
    signals = calibrate_signals(signals, credibility)
    return signals


# ─────────────────────────────────────────────────────────────
# CREDIBILITY ASSESSMENT
# ─────────────────────────────────────────────────────────────

def build_assessment(credibility, emotion_score, fact_score, formality, verified, total_claims):
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
    if total_claims > 0 and verified == 0:
        parts.append("None of the key claims could be independently corroborated.")
    elif total_claims > 0 and verified < total_claims:
        parts.append(f"Only {verified} of {total_claims} key claim(s) were corroborated online.")
    if score >= 70:
        parts.append("Always verify with additional sources before sharing.")
    elif score >= 40:
        parts.append("Cross-check key claims with established news outlets before sharing.")
    else:
        parts.append("Do not share without thorough independent verification.")
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────
# ROUTE
# ─────────────────────────────────────────────────────────────

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.json
        text = data["text"]

        prediction       = model.predict([text])[0]
        probability_fake = float(model.predict_proba([text])[0][0])
        credibility      = 1.0 - probability_fake

        emotion_score, emotion_words, clickbait_count = emotional_language_score(text)
        fact_score   = factual_consistency_score(text)
        formality    = formality_score(text)
        claims       = extract_claims(text, max_claims=3)
        verification = verify_claims_online(claims)
        verified_count = sum(1 for v in verification if v["found"])

        signals         = build_signals(text, probability_fake, credibility)
        assessment      = build_assessment(credibility, emotion_score, fact_score,
                                           formality, verified_count, len(claims))
        content_summary = build_content_summary(text, max_sentences=3)

        return jsonify({
            "prediction":      int(prediction),
            "probability":     probability_fake,
            "signals":         signals,
            "summary":         assessment,
            "content_summary": content_summary,
            "verified_claims": verification,
            "analysis": {
                "emotion_score":   round(emotion_score, 3),
                "fact_score":      round(fact_score, 3),
                "formality":       round(formality, 3),
                "uppercase_ratio": round(uppercase_ratio(text), 3),
                "punct_density":   round(punctuation_density(text), 3),
                "url_count":       len(extract_urls(text)),
                "clickbait_hits":  clickbait_count,
            },
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Server is running on http://localhost:5000")
    app.run(port=5000)
