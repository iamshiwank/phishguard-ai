# ============================================================
# PhishGuard AI — Streamlit Dashboard
# app.py — Main entry point
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import joblib
import scipy.sparse as sp
import re
import string
import warnings
warnings.filterwarnings('ignore')

# NLP tools (same ones used in preprocessing)
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import tldextract
from urllib.parse import urlparse

# Download NLTK data silently if not already present
nltk.download('stopwords', quiet=True)
nltk.download('wordnet', quiet=True)
nltk.download('omw-1.4', quiet=True)

# ============================================================
# PAGE CONFIGURATION — Must be the very first Streamlit call
# ============================================================

st.set_page_config(
    page_title="PhishGuard AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# SECTION 2: Custom CSS for professional appearance
# ============================================================

st.markdown("""
<style>
    /* Main background */
    .main { background-color: #0f1117; }

    /* Risk result boxes */
    .safe-box {
        background: linear-gradient(135deg, #1a472a, #2ecc71);
        border-radius: 15px; padding: 25px;
        text-align: center; color: white;
        font-size: 28px; font-weight: bold;
        box-shadow: 0 4px 20px rgba(46,204,113,0.4);
        margin: 15px 0;
    }
    .suspicious-box {
        background: linear-gradient(135deg, #7d6608, #f39c12);
        border-radius: 15px; padding: 25px;
        text-align: center; color: white;
        font-size: 28px; font-weight: bold;
        box-shadow: 0 4px 20px rgba(243,156,18,0.4);
        margin: 15px 0;
    }
    .phishing-box {
        background: linear-gradient(135deg, #641e16, #e74c3c);
        border-radius: 15px; padding: 25px;
        text-align: center; color: white;
        font-size: 28px; font-weight: bold;
        box-shadow: 0 4px 20px rgba(231,76,60,0.4);
        margin: 15px 0;
    }

    /* Metric cards */
    .metric-card {
        background: #1e2130;
        border-radius: 10px; padding: 15px;
        text-align: center; margin: 5px;
        border: 1px solid #2d3250;
    }

    /* Section headers */
    .section-header {
        font-size: 20px; font-weight: bold;
        color: #a0aec0; margin: 20px 0 10px 0;
        border-bottom: 2px solid #2d3250;
        padding-bottom: 8px;
    }

    /* Advice box */
    .advice-box {
        background: #1e2130;
        border-radius: 10px; padding: 20px;
        border-left: 5px solid #3498db;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# SECTION 3: Load all saved models and tools
# ============================================================

@st.cache_resource
def load_all_models():
    """
    Load all saved models exactly once and cache them.
    @st.cache_resource means this function only runs once —
    every time someone uses the app it reuses the loaded models
    instead of reloading from disk each time.
    """
    models = {}

    try:
        models['xgb']       = joblib.load('models/xgboost_model.pkl')
        models['tfidf']     = joblib.load('models/tfidf_vectorizer.pkl')
        models['scaler']    = joblib.load('models/feature_scaler.pkl')
        models['feat_names']= joblib.load('models/feature_names.pkl')
        models['threshold'] = joblib.load('models/optimal_threshold.pkl')
        models['loaded']    = True

    except FileNotFoundError as e:
        models['loaded'] = False
        models['error']  = str(e)

    return models

# Load models on startup
models = load_all_models()

# ============================================================
# SECTION 3b: Rebuild preprocessing tools
# (Same settings as Week 3 — must be identical)
# ============================================================

STOP_WORDS  = set(stopwords.words('english'))
LEMMATIZER  = WordNetLemmatizer()

# Phishing keywords (same as Week 4)
PHISHING_KEYWORDS = {
    'urgency'  : ['urgent','immediately','alert','warning','critical','expire',
                  'expires','expiring','deadline','limited','suspend','suspended',
                  'suspension','terminate','terminated','locked','disabled',
                  'restricted','blocked','unauthorized'],
    'action'   : ['verify','confirm','validate','update','click','login',
                  'signin','access','download','open','review','respond',
                  'reply','call','contact'],
    'account'  : ['account','password','username','credential','pin','ssn',
                  'social','security','identity','personal','information',
                  'details','data','profile','user'],
    'financial': ['bank','payment','transaction','transfer','wire','refund',
                  'invoice','billing','credit','debit','card','reward',
                  'prize','lottery','winner','million','dollars','cash',
                  'funds','money'],
    'trust'    : ['official','secure','security','protected','trusted',
                  'customer','service','support','team','department',
                  'notification','notice','important','required','mandatory']
}

ALL_PHISHING_KEYWORDS = list(set(
    word for words in PHISHING_KEYWORDS.values() for word in words
))

FREE_EMAIL_PROVIDERS = [
    'gmail.com','yahoo.com','hotmail.com','outlook.com','aol.com',
    'icloud.com','mail.com','protonmail.com','zoho.com','yandex.com',
    'gmx.com','live.com','msn.com','me.com','inbox.com','fastmail.com'
]

SUSPICIOUS_TLDS = [
    'xyz','top','club','online','site','space','info','biz',
    'tk','ml','ga','cf','gq','pw','cc','ws','su','nu','in','ru'
]

SUBJECT_URGENCY_WORDS = [
    'urgent','immediate','alert','warning','important','action',
    'required','critical','attention','notice','verify','confirm',
    'suspended','locked','expire'
]

SUBJECT_MONEY_WORDS = [
    'payment','invoice','refund','reward','prize','winner','cash',
    'money','transfer','bank','credit','debit','fund','million','dollar'
]

# ============================================================
# SECTION 4: Preprocessing & feature extraction
# (Exact same logic as Weeks 3 & 4 — must be identical)
# ============================================================

def clean_text(text):
    """Week 3 preprocessing pipeline — identical copy."""
    text = str(text).lower()
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'http\S+|www\S+|https\S+', 'urllink', text)
    text = re.sub(r'\S+@\S+', 'emailaddr', text)
    text = re.sub(r'\b(\+?\d[\d\s\-().]{7,})\b', 'phonenumber', text)
    text = text.translate(str.maketrans('', '', string.punctuation))
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    tokens = text.split()
    tokens = [w for w in tokens if w not in STOP_WORDS and len(w) > 2]
    tokens = [LEMMATIZER.lemmatize(w) for w in tokens]
    return ' '.join(tokens)


def extract_all_features(text):
    """
    Run all four feature extractors from Week 4.
    Returns a dictionary of all engineered features.
    """
    text_str  = str(text)
    text_lower = text_str.lower()
    words     = text_str.split()
    features  = {}

    # --- Content features ---
    features['body_char_length']       = len(text_str)
    features['body_word_count']        = len(words)
    features['avg_word_length']        = np.mean([len(w) for w in words]) if words else 0
    features['phishing_keyword_count'] = sum(1 for w in text_lower.split() if w in ALL_PHISHING_KEYWORDS)

    for cat, kws in PHISHING_KEYWORDS.items():
        features[f'keyword_{cat}_count'] = sum(1 for w in text_lower.split() if w in kws)

    upper_chars = sum(1 for c in text_str if c.isupper())
    features['uppercase_char_ratio']  = upper_chars / max(len(text_str), 1)
    features['all_caps_word_count']   = sum(1 for w in words if w.isupper() and len(w) > 2)
    features['exclamation_count']     = text_str.count('!')
    features['question_mark_count']   = text_str.count('?')
    features['dollar_sign_count']     = text_str.count('$')
    digit_chars = sum(1 for c in text_str if c.isdigit())
    features['digit_char_ratio']      = digit_chars / max(len(text_str), 1)
    html_tags = re.findall(r'<[^>]+>', text_str)
    features['html_tag_count']        = len(html_tags)
    features['has_html']              = 1 if html_tags else 0
    urls_found = re.findall(r'http[s]?://\S+|www\.\S+', text_str)
    features['body_url_count']        = len(urls_found)
    features['has_url_in_body']       = 1 if urls_found else 0
    features['free_word_count']       = text_lower.count('free')
    cta_words = ['click','here','below','link','button','tap']
    features['call_to_action_count']  = sum(text_lower.count(w) for w in cta_words)

    # --- Subject features ---
    subj_match = re.search(r'subject[:\s]+(.+?)(?:\n|$)', text_str, re.IGNORECASE)
    subject    = subj_match.group(1).strip() if subj_match else text_str[:100]
    subj_lower = subject.lower()
    subj_words = subject.split()
    features['subject_char_length']           = len(subject)
    features['subject_word_count']            = len(subj_words)
    features['subject_urgency_count']         = sum(1 for w in subj_lower.split() if w in SUBJECT_URGENCY_WORDS)
    features['subject_money_count']           = sum(1 for w in subj_lower.split() if w in SUBJECT_MONEY_WORDS)
    subj_upper = sum(1 for c in subject if c.isupper())
    features['subject_uppercase_ratio']       = subj_upper / max(len(subject), 1)
    features['subject_all_caps']              = 1 if subject.isupper() and len(subject) > 3 else 0
    features['subject_exclamation_count']     = subject.count('!')
    features['subject_is_reply_or_forward']   = 1 if re.search(r'\b(re:|fw:|fwd:)', subj_lower) else 0

    # --- Header features ---
    sender_match  = re.search(r'from[:\s]+.*?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', text_str, re.IGNORECASE)
    replyto_match = re.search(r'reply-to[:\s]+.*?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', text_str, re.IGNORECASE)
    sender_email  = sender_match.group(1).lower()  if sender_match  else ''
    replyto_email = replyto_match.group(1).lower() if replyto_match else ''
    sender_domain  = sender_email.split('@')[1]  if '@' in sender_email  else ''
    replyto_domain = replyto_email.split('@')[1] if '@' in replyto_email else ''
    features['sender_domain_length']       = len(sender_domain)
    features['sender_domain_dot_count']    = sender_domain.count('.')
    features['sender_is_free_email']       = 1 if sender_domain in FREE_EMAIL_PROVIDERS else 0
    features['sender_domain_numeric_count']= sum(1 for c in sender_domain if c.isdigit())
    features['domain_mismatch']            = 0 if (not sender_domain or not replyto_domain or sender_domain == replyto_domain) else 1
    features['has_reply_to']               = 1 if replyto_email else 0
    features['sender_domain_has_hyphen']   = 1 if '-' in sender_domain else 0
    features['total_at_symbol_count']      = text_str.count('@')

    # --- URL features ---
    all_urls = re.findall(r'http[s]?://[^\s<>"\']+|www\.[^\s<>"\']+', text_str)
    features['total_url_count'] = len(all_urls)
    features['has_any_url']     = 1 if all_urls else 0

    def _analyze_url(url):
        try:
            parsed    = urlparse(url)
            extracted = tldextract.extract(url)
            subdomain = extracted.subdomain
            tld       = extracted.suffix.lower() if extracted.suffix else ''
            return {
                'url_length'         : len(url),
                'url_dot_count'      : url.count('.'),
                'url_hyphen_count'   : url.count('-'),
                'url_at_symbol'      : 1 if '@' in url else 0,
                'url_is_ip_based'    : 1 if re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', url) else 0,
                'url_subdomain_depth': len(subdomain.split('.')) if subdomain else 0,
                'url_uses_https'     : 1 if parsed.scheme == 'https' else 0,
                'url_suspicious_tld' : 1 if tld in SUSPICIOUS_TLDS else 0,
                'url_has_redirect'   : 1 if any(p in url.lower() for p in ['redirect','url=','goto','link=','forward']) else 0,
                'url_path_length'    : len(parsed.path),
                'url_param_count'    : len(parsed.query.split('&')) if parsed.query else 0,
            }
        except Exception:
            return {k: 0 for k in ['url_length','url_dot_count','url_hyphen_count',
                                    'url_at_symbol','url_is_ip_based','url_subdomain_depth',
                                    'url_uses_https','url_suspicious_tld','url_has_redirect',
                                    'url_path_length','url_param_count']}

    if all_urls:
        longest_url = max(all_urls, key=len)
        features.update(_analyze_url(longest_url))
        features['avg_url_length'] = np.mean([len(u) for u in all_urls])
        features['max_url_length'] = max(len(u) for u in all_urls)
    else:
        for k in ['url_length','url_dot_count','url_hyphen_count','url_at_symbol',
                  'url_is_ip_based','url_subdomain_depth','url_uses_https',
                  'url_suspicious_tld','url_has_redirect','url_path_length',
                  'url_param_count','avg_url_length','max_url_length']:
            features[k] = 0

    return features


def analyze_email(email_text, models):
    """
    Complete pipeline: raw email → risk score + features.
    This is the function that ties everything together.
    """
    # Step 1: Clean text for TF-IDF
    cleaned = clean_text(email_text)

    # Step 2: TF-IDF vectorization
    tfidf_vec = models['tfidf'].transform([cleaned])

    # Step 3: Extract engineered features
    eng_features = extract_all_features(email_text)

    # Step 4: Build feature vector in correct order
    feat_names  = models['feat_names']
    eng_vector  = np.array([[eng_features.get(f, 0) for f in feat_names]])

    # Step 5: Scale engineered features
    eng_scaled  = models['scaler'].transform(eng_vector)

    # Step 6: Combine TF-IDF + engineered into final matrix
    eng_sparse  = sp.csr_matrix(eng_scaled)
    X_final     = sp.hstack([tfidf_vec, eng_sparse])

    # Step 7: Get probability from XGBoost
    probability = models['xgb'].predict_proba(X_final)[0][1]
    score_pct   = round(probability * 100, 1)

    # Step 8: Classify using optimal threshold
    threshold   = models['threshold']
    if probability >= threshold:
        label = 'PHISHING'
    elif probability >= 0.45:
        label = 'SUSPICIOUS'
    else:
        label = 'SAFE'

    return score_pct, label, eng_features

# ============================================================
# SECTION 5: Sidebar — branding and session history
# ============================================================

with st.sidebar:
    st.markdown("# 🛡️ PhishGuard AI")
    st.markdown("**AI-Powered Email Security Analyzer**")
    st.markdown("---")

    st.markdown("### 📊 Risk Level Guide")
    st.markdown("🟢 **SAFE** — Score 0–44%")
    st.markdown("🟡 **SUSPICIOUS** — Score 45–74%")
    st.markdown("🔴 **PHISHING** — Score 75–100%")
    st.markdown("---")

    st.markdown("### ℹ️ How It Works")
    st.markdown("""
    1. Paste email text or upload `.eml` file
    2. AI analyzes 3,000+ text features
    3. 40+ security signals are extracted
    4. XGBoost model scores the risk
    5. Result shown with full breakdown
    """)
    st.markdown("---")

    # Session statistics
    if 'history' not in st.session_state:
        st.session_state.history = []

    st.markdown("### 📈 Session Stats")
    history = st.session_state.history
    if history:
        total   = len(history)
        safe    = sum(1 for h in history if h['label'] == 'SAFE')
        susp    = sum(1 for h in history if h['label'] == 'SUSPICIOUS')
        phish   = sum(1 for h in history if h['label'] == 'PHISHING')
        st.metric("Emails Analyzed", total)
        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 Safe",       safe)
        col2.metric("🟡 Suspicious", susp)
        col3.metric("🔴 Phishing",   phish)
    else:
        st.info("No emails analyzed yet in this session.")

    st.markdown("---")
    st.markdown("*Collaborative Prototype Project*")
    st.markdown("*PhishGuard AI v1.0*")

# ============================================================
# SECTION 6: Main page — input and analysis
# ============================================================

st.markdown("# 🛡️ PhishGuard AI")
st.markdown("### AI-Powered Phishing Detection & Email Security Analyzer")
st.markdown("---")

# Check models loaded correctly
if not models.get('loaded', False):
    st.error(f"❌ Model files not found. Please ensure all .pkl files are in the models/ folder.")
    st.error(f"Error: {models.get('error', 'Unknown')}")
    st.stop()

# ---- Input Section ----
st.markdown('<div class="section-header">📧 Email Input</div>', unsafe_allow_html=True)

input_mode = st.radio(
    "Choose input method:",
    ["📋 Paste Email Text", "📁 Upload .eml File"],
    horizontal=True
)

email_text = ""

if input_mode == "📋 Paste Email Text":
    email_text = st.text_area(
        label="Paste the complete email content below (including headers if available):",
        height=250,
        placeholder="""From: support@yourbank-secure.xyz
Subject: URGENT: Your account has been suspended!
Reply-To: hacker@totallynotlegit.com

Dear Customer,

Your account access has been SUSPENDED due to unusual activity.
Click here immediately to verify: http://fake-login.xyz/verify

Failure to verify within 24 hours will result in permanent suspension.""",
        help="Paste the full email including From, Subject, and body text for best results."
    )

else:
    uploaded_file = st.file_uploader(
        "Upload an .eml email file:",
        type=['eml'],
        help="Export an email as .eml from your email client and upload here."
    )
    if uploaded_file:
        email_text = uploaded_file.read().decode('utf-8', errors='ignore')
        st.success(f"✅ File loaded: {uploaded_file.name}")
        with st.expander("👁️ Preview uploaded email content"):
            st.text(email_text[:1000] + ("..." if len(email_text) > 1000 else ""))

# ---- Analyze Button ----
st.markdown("")
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    analyze_clicked = st.button(
        "🔍 ANALYZE EMAIL",
        use_container_width=True,
        type="primary"
    )

# ---- Run Analysis ----
if analyze_clicked:
    if not email_text.strip():
        st.warning("⚠️ Please paste email text or upload a file before clicking Analyze.")
    else:
        with st.spinner("🔍 Analyzing email... running 3,040+ feature checks..."):
            score, label, features = analyze_email(email_text, models)

        # Save to history
        st.session_state.history.append({
            'label': label, 'score': score,
            'preview': email_text[:80] + "..."
        })

        st.markdown("---")
        st.markdown('<div class="section-header">🎯 Analysis Result</div>',
                    unsafe_allow_html=True)

        # ---- Risk Result Display ----
        col_gauge, col_result = st.columns([1, 1])

        with col_gauge:
            # Plotly gauge chart (PRD: FR-06 risk gauge)
            if label == 'SAFE':
                gauge_color = '#2ecc71'
            elif label == 'SUSPICIOUS':
                gauge_color = '#f39c12'
            else:
                gauge_color = '#e74c3c'

            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=score,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "Phishing Risk Score", 'font': {'size': 18, 'color': 'white'}},
                number={'suffix': "%", 'font': {'size': 36, 'color': gauge_color}},
                gauge={
                    'axis': {
                        'range': [0, 100],
                        'tickwidth': 1,
                        'tickcolor': "white",
                        'tickfont': {'color': 'white'}
                    },
                    'bar': {'color': gauge_color},
                    'bgcolor': "#1e2130",
                    'borderwidth': 2,
                    'bordercolor': "#2d3250",
                    'steps': [
                        {'range': [0,  44], 'color': '#1a472a'},
                        {'range': [45, 74], 'color': '#7d6608'},
                        {'range': [75,100], 'color': '#641e16'}
                    ],
                    'threshold': {
                        'line': {'color': gauge_color, 'width': 4},
                        'thickness': 0.75,
                        'value': score
                    }
                }
            ))
            fig_gauge.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font={'color': 'white'},
                height=300,
                margin=dict(l=20, r=20, t=50, b=20)
            )
            st.plotly_chart(fig_gauge, use_container_width=True)

        with col_result:
            st.markdown("<br><br>", unsafe_allow_html=True)

            # Colored result box
            if label == 'SAFE':
                st.markdown(f'<div class="safe-box">🟢 SAFE<br><small>Risk Score: {score}%</small></div>',
                            unsafe_allow_html=True)
            elif label == 'SUSPICIOUS':
                st.markdown(f'<div class="suspicious-box">🟡 SUSPICIOUS<br><small>Risk Score: {score}%</small></div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="phishing-box">🔴 PHISHING DETECTED<br><small>Risk Score: {score}%</small></div>',
                            unsafe_allow_html=True)

            # Advice box (PRD: FR-05 user guidance)
            st.markdown("<br>", unsafe_allow_html=True)
            if label == 'SAFE':
                advice = "✅ **Email appears legitimate.** No immediate action required. Always stay cautious with unexpected emails."
                st.success(advice)
            elif label == 'SUSPICIOUS':
                advice = "⚠️ **Treat with caution.** Verify the sender's identity through an official channel before clicking any links or providing any information."
                st.warning(advice)
            else:
                advice = "🚨 **Do NOT click any links or provide any information.** Report this email to your IT security team immediately and delete it."
                st.error(advice)

        # ---- Feature Breakdown Panel ----
        st.markdown("---")
        st.markdown('<div class="section-header">🔬 Feature Breakdown</div>',
                    unsafe_allow_html=True)

        key_features = {
            '🔑 Phishing Keywords Found' : features.get('phishing_keyword_count', 0),
            '❗ Exclamation Marks'        : features.get('exclamation_count', 0),
            '🔗 URLs Detected'            : features.get('total_url_count', 0),
            '🏷️ HTML Tags Found'          : features.get('html_tag_count', 0),
            '📢 ALL CAPS Words'           : features.get('all_caps_word_count', 0),
            '💰 Financial Keywords'        : features.get('keyword_financial_count', 0),
            '⚡ Urgency Keywords'          : features.get('keyword_urgency_count', 0),
            '🌐 Suspicious TLD'           : features.get('url_suspicious_tld', 0),
            '🔄 Domain Mismatch'          : features.get('domain_mismatch', 0),
            '📧 Free Email Provider'       : features.get('sender_is_free_email', 0),
            '🖥️ IP-based URL'             : features.get('url_is_ip_based', 0),
            '📋 Subject Urgency Words'    : features.get('subject_urgency_count', 0),
        }

        cols = st.columns(4)
        for i, (feat_name, feat_val) in enumerate(key_features.items()):
            with cols[i % 4]:
                if feat_val > 0:
                    color = "#e74c3c"
                    icon  = "⚠️"
                else:
                    color = "#2ecc71"
                    icon  = "✅"
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div style="font-size:11px;color:#a0aec0;">{feat_name}</div>'
                    f'<div style="font-size:22px;color:{color};font-weight:bold;">{icon} {feat_val}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        # ---- Full Feature Table (expandable) ----
        with st.expander("📋 View All Extracted Features"):
            feat_df = pd.DataFrame(
                list(features.items()),
                columns=['Feature', 'Value']
            ).sort_values('Value', ascending=False)
            st.dataframe(feat_df, use_container_width=True, height=300)

# ============================================================
# SECTION 7: Session analytics charts (PRD: FR-06)
# ============================================================

st.markdown("---")
st.markdown('<div class="section-header">📊 Session Analytics</div>',
            unsafe_allow_html=True)

history = st.session_state.history

if len(history) == 0:
    st.info("📭 No emails analyzed yet this session. Analyze some emails above to see analytics here.")

else:
    hist_df = pd.DataFrame(history)

    col_pie, col_bar = st.columns(2)

    with col_pie:
        # Pie chart of classification distribution (PRD: FR-06)
        label_counts = hist_df['label'].value_counts()
        color_map    = {'SAFE': '#2ecc71', 'SUSPICIOUS': '#f39c12', 'PHISHING': '#e74c3c'}
        pie_colors   = [color_map.get(l, '#95a5a6') for l in label_counts.index]

        fig_pie = go.Figure(go.Pie(
            labels=label_counts.index,
            values=label_counts.values,
            hole=0.4,
            marker=dict(colors=pie_colors, line=dict(color='#0f1117', width=2)),
            textinfo='label+percent',
            textfont=dict(color='white', size=13)
        ))
        fig_pie.update_layout(
            title=dict(text="Classification Distribution", font=dict(color='white', size=16)),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white'),
            legend=dict(font=dict(color='white')),
            height=350
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_bar:
        # Bar chart of risk scores per email (PRD: FR-06)
        email_labels = [f"Email {i+1}" for i in range(len(hist_df))]
        bar_colors   = [color_map.get(l, '#95a5a6') for l in hist_df['label']]

        fig_bar = go.Figure(go.Bar(
            x=email_labels,
            y=hist_df['score'],
            marker=dict(color=bar_colors, line=dict(color='white', width=0.5)),
            text=[f"{s}%" for s in hist_df['score']],
            textposition='outside',
            textfont=dict(color='white')
        ))
        fig_bar.add_hline(y=75, line_dash="dash", line_color="#e74c3c",
                          annotation_text="Phishing threshold (75%)",
                          annotation_font_color="#e74c3c")
        fig_bar.add_hline(y=45, line_dash="dash", line_color="#f39c12",
                          annotation_text="Suspicious threshold (45%)",
                          annotation_font_color="#f39c12")
        fig_bar.update_layout(
            title=dict(text="Risk Scores — All Analyzed Emails", font=dict(color='white', size=16)),
            xaxis=dict(tickfont=dict(color='white'), title_font=dict(color='white')),
            yaxis=dict(tickfont=dict(color='white'), range=[0, 110],
                       title='Risk Score (%)', title_font=dict(color='white')),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=350
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # History table
    st.markdown('<div class="section-header">📜 Analysis History</div>',
                unsafe_allow_html=True)
    display_df = hist_df[['label', 'score', 'preview']].copy()
    display_df.columns = ['Classification', 'Risk Score (%)', 'Email Preview']
    display_df.index   = [f"Email {i+1}" for i in range(len(display_df))]
    st.dataframe(display_df, use_container_width=True)


# Footer

st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#4a5568; font-size:13px;'>"
    "🛡️ PhishGuard AI — H2S Solution Challenge 2026 &nbsp;|&nbsp; "
    "Built with XGBoost + Streamlit &nbsp;|&nbsp; "
    "All processing is local — no data is stored or transmitted"
    "</div>",
    unsafe_allow_html=True
)

