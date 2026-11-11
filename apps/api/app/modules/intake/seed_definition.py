"""DEMO questionnaire. Written by a software developer, NOT reviewed by a qualified Ayurveda
practitioner or a professional translator. Hindi/Tamil strings are unreviewed drafts.
Practitioner-observation fields record free-text observations only; nothing here scores or
infers Prakriti/Vikriti."""

from typing import Any


def L(en: str, hi: str | None = None, ta: str | None = None) -> dict[str, str | None]:  # noqa: N802
    return {"en": en, "hi": hi, "ta": ta}


def opt(code: str, en: str, hi: str | None = None, ta: str | None = None) -> dict[str, Any]:
    return {"code": code, "label": L(en, hi, ta)}


YES_NO_UNSURE_NOTE = "Use 'unknown' or 'declined' instead of guessing."

DEMO_DEFINITION: dict[str, Any] = {
    "code": "general_ayurveda_intake",
    "title": L(
        "General and Ayurveda intake (DEMO)",
        "सामान्य एवं आयुर्वेद प्रारंभिक जानकारी (डेमो)",
        "பொது மற்றும் ஆயுர்வேத முன்தகவல் (டெமோ)",
    ),
    "clinical_disclaimer": (
        "Demo questionnaire for a portfolio project. Not clinically reviewed. Translations are "
        "unreviewed drafts. Not for use with real patients."
    ),
    "sections": [
        {
            "code": "presenting_complaint",
            "title": L("Presenting complaint", "मुख्य समस्या", "முக்கிய பிரச்சனை"),
            "questions": [
                {
                    "code": "chief_complaint",
                    "type": "text",
                    "required": True,
                    "text": L(
                        "What is the main problem that brings you here today?",
                        "आज आप किस मुख्य समस्या के लिए आए हैं?",
                        "இன்று நீங்கள் வந்ததற்கான முக்கிய பிரச்சனை என்ன?",
                    ),
                },
                {
                    "code": "complaint_duration",
                    "type": "duration",
                    "required": True,
                    "text": L(
                        "How long have you had this problem?",
                        "यह समस्या कितने समय से है?",
                        "இந்த பிரச்சனை எவ்வளவு காலமாக உள்ளது?",
                    ),
                },
                {
                    "code": "onset",
                    "type": "single_choice",
                    "text": L("How did it start?", "यह कैसे शुरू हुआ?", "இது எப்படி தொடங்கியது?"),
                    "options": [
                        opt("sudden", "Suddenly", "अचानक", "திடீரென"),
                        opt("gradual", "Gradually", "धीरे-धीरे", "படிப்படியாக"),
                    ],
                },
                {
                    "code": "severity",
                    "type": "number",
                    "min": 0,
                    "max": 10,
                    "text": L(
                        "How severe is it now, from 0 (none) to 10 (worst)?",
                        "अभी यह कितना गंभीर है, 0 (नहीं) से 10 (सबसे अधिक) तक?",
                        "இப்போது இது எவ்வளவு கடுமையாக உள்ளது, 0 (இல்லை) முதல் 10 (மிக அதிகம்) வரை?",
                    ),
                },
                {
                    "code": "progression",
                    "type": "single_choice",
                    "text": L(
                        "Since it started, has it been…",
                        "शुरू होने के बाद से यह…",
                        "தொடங்கியதிலிருந்து இது…",
                    ),
                    "options": [
                        opt("improving", "Improving", "सुधर रहा है", "குறைந்து வருகிறது"),
                        opt("worsening", "Getting worse", "बढ़ रहा है", "அதிகரித்து வருகிறது"),
                        opt("unchanged", "Unchanged", "वैसा ही है", "மாறாமல் உள்ளது"),
                        opt(
                            "fluctuating",
                            "Coming and going",
                            "कभी कम कभी ज़्यादा",
                            "ஏற்ற இறக்கமாக உள்ளது",
                        ),
                    ],
                },
                {
                    "code": "associated_symptoms",
                    "type": "multi_choice",
                    "text": L(
                        "Do you have any of these along with it?",
                        "क्या इसके साथ इनमें से कुछ है?",
                        "இதனுடன் இவற்றில் ஏதேனும் உள்ளதா?",
                    ),
                    "options": [
                        opt("fever", "Fever", "बुखार", "காய்ச்சல்"),
                        opt("fatigue", "Tiredness", "थकान", "சோர்வு"),
                        opt(
                            "weight_loss",
                            "Unplanned weight loss",
                            "बिना कारण वज़न घटना",
                            "திட்டமிடாத எடை இழப்பு",
                        ),
                        opt("pain", "Pain", "दर्द", "வலி"),
                        opt("sleep_disturbance", "Sleep problems", "नींद की समस्या", "தூக்கப் பிரச்சனை"),
                        opt(
                            "digestive_upset",
                            "Digestive upset",
                            "पाचन संबंधी परेशानी",
                            "செரிமானக் கோளாறு",
                        ),
                        opt(
                            "none_of_these", "None of these", "इनमें से कोई नहीं", "இவற்றில் எதுவும் இல்லை"
                        ),
                    ],
                },
                {
                    "code": "chest_pain",
                    "type": "boolean",
                    "required": True,
                    "text": L(
                        "Do you have chest pain right now or in the last 24 hours?",
                        "क्या अभी या पिछले 24 घंटों में सीने में दर्द हुआ है?",
                        "இப்போது அல்லது கடந்த 24 மணி நேரத்தில் நெஞ்சு வலி இருந்ததா?",
                    ),
                },
                {
                    "code": "chest_pain_breathless",
                    "type": "boolean",
                    "required": True,
                    "show_if": {"question": "chest_pain", "op": "is_true"},
                    "text": L(
                        "Is the chest pain accompanied by breathlessness or sweating?",
                        "क्या सीने के दर्द के साथ सांस फूलना या पसीना आता है?",
                        "நெஞ்சு வலியுடன் மூச்சுத் திணறல் அல்லது வியர்வை உள்ளதா?",
                    ),
                },
                {
                    "code": "prior_treatment",
                    "type": "long_text",
                    "text": L(
                        "What treatment have you already tried for this problem?",
                        "इस समस्या के लिए आपने पहले क्या इलाज लिया है?",
                        "இந்த பிரச்சனைக்கு ஏற்கனவே என்ன சிகிச்சை எடுத்தீர்கள்?",
                    ),
                },
            ],
        },
        {
            "code": "history",
            "title": L("Medical history", "चिकित्सा इतिहास", "மருத்துவ வரலாறு"),
            "questions": [
                {
                    "code": "medical_history",
                    "type": "long_text",
                    "text": L(
                        "Any long-term illnesses or past medical conditions?",
                        "कोई दीर्घकालिक बीमारी या पहले की स्वास्थ्य समस्या?",
                        "நீண்டகால நோய் அல்லது முந்தைய உடல்நலப் பிரச்சனைகள் ஏதேனும்?",
                    ),
                },
                {
                    "code": "surgical_history",
                    "type": "long_text",
                    "text": L(
                        "Any past surgeries?",
                        "क्या पहले कोई ऑपरेशन हुआ है?",
                        "முன்பு அறுவை சிகிச்சை ஏதேனும் நடந்ததா?",
                    ),
                },
                {
                    "code": "family_history",
                    "type": "long_text",
                    "text": L(
                        "Any illnesses that run in your family?",
                        "परिवार में कोई बीमारी जो चलती आई हो?",
                        "குடும்பத்தில் தொடர்ந்து வரும் நோய்கள் ஏதேனும்?",
                    ),
                },
                {
                    "code": "current_medications",
                    "type": "long_text",
                    "required": True,
                    "text": L(
                        "List all medicines, herbal preparations or supplements you currently take.",
                        "आप अभी जो भी दवाइयाँ, जड़ी-बूटी या सप्लीमेंट लेते हैं, सब बताइए।",
                        "தற்போது எடுத்துக்கொள்ளும் மருந்துகள், மூலிகைகள், சப்ளிமெண்ட்கள் அனைத்தையும் குறிப்பிடவும்.",
                    ),
                    "help": L(
                        "If none, choose 'answered' and write 'none'. If you are not sure, mark unknown.",
                    ),
                },
                {
                    "code": "has_allergies",
                    "type": "boolean",
                    "required": True,
                    "text": L(
                        "Do you have any known allergies to medicines, foods or other substances?",
                        "क्या आपको किसी दवा, भोजन या अन्य चीज़ से एलर्जी है?",
                        "மருந்து, உணவு அல்லது வேறு பொருட்களுக்கு ஒவ்வாமை உள்ளதா?",
                    ),
                },
                {
                    "code": "allergy_details",
                    "type": "text",
                    "required": True,
                    "show_if": {"question": "has_allergies", "op": "is_true"},
                    "text": L(
                        "What are you allergic to and what happens?",
                        "किस चीज़ से एलर्जी है और क्या होता है?",
                        "எதற்கு ஒவ்வாமை, என்ன நடக்கும்?",
                    ),
                },
            ],
        },
        {
            "code": "lifestyle",
            "title": L(
                "Lifestyle (Ahara and Vihara)",
                "जीवनशैली (आहार और विहार)",
                "வாழ்க்கை முறை (ஆஹாரம் மற்றும் விஹாரம்)",
            ),
            "questions": [
                {
                    "code": "diet_type",
                    "type": "single_choice",
                    "text": L(
                        "Which best describes your diet?", "आपका भोजन कैसा है?", "உங்கள் உணவு முறை எது?"
                    ),
                    "options": [
                        opt("vegetarian", "Vegetarian", "शाकाहारी", "சைவம்"),
                        opt(
                            "eggetarian",
                            "Vegetarian with eggs",
                            "अंडे सहित शाकाहारी",
                            "முட்டையுடன் சைவம்",
                        ),
                        opt("non_vegetarian", "Non-vegetarian", "मांसाहारी", "அசைவம்"),
                        opt("vegan", "Vegan", "वीगन", "வீகன்"),
                    ],
                },
                {
                    "code": "meal_regularity",
                    "type": "single_choice",
                    "text": L(
                        "Are your meal times regular?",
                        "क्या आपके भोजन का समय नियमित है?",
                        "உங்கள் உணவு நேரம் சீராக உள்ளதா?",
                    ),
                    "options": [
                        opt("regular", "Mostly regular", "ज़्यादातर नियमित", "பெரும்பாலும் சீராக"),
                        opt("irregular", "Often irregular", "अक्सर अनियमित", "அடிக்கடி சீரற்ற"),
                    ],
                },
                {
                    "code": "exercise_frequency",
                    "type": "single_choice",
                    "text": L(
                        "How often do you exercise?",
                        "आप कितनी बार व्यायाम करते हैं?",
                        "எவ்வளவு அடிக்கடி உடற்பயிற்சி செய்கிறீர்கள்?",
                    ),
                    "options": [
                        opt("daily", "Daily", "रोज़", "தினமும்"),
                        opt("weekly", "A few times a week", "हफ़्ते में कुछ बार", "வாரத்தில் சில முறை"),
                        opt("rarely", "Rarely or never", "शायद ही कभी", "அரிதாக அல்லது இல்லை"),
                    ],
                },
                {
                    "code": "tobacco_use",
                    "type": "single_choice",
                    "text": L(
                        "Do you use tobacco?",
                        "क्या आप तंबाकू का सेवन करते हैं?",
                        "நீங்கள் புகையிலை பயன்படுத்துகிறீர்களா?",
                    ),
                    "options": [
                        opt("never", "Never", "कभी नहीं", "ஒருபோதும் இல்லை"),
                        opt("former", "In the past", "पहले करता/करती था/थी", "முன்பு"),
                        opt("current", "Currently", "अभी करता/करती हूँ", "தற்போது"),
                    ],
                },
                {
                    "code": "alcohol_use",
                    "type": "single_choice",
                    "text": L(
                        "Do you drink alcohol?", "क्या आप शराब पीते हैं?", "நீங்கள் மது அருந்துகிறீர்களா?"
                    ),
                    "options": [
                        opt("never", "Never", "कभी नहीं", "ஒருபோதும் இல்லை"),
                        opt("occasional", "Occasionally", "कभी-कभी", "எப்போதாவது"),
                        opt("regular", "Regularly", "नियमित रूप से", "வழக்கமாக"),
                    ],
                },
            ],
        },
        {
            "code": "ayurveda_patient_reported",
            "title": L(
                "Digestion, sleep and mind (patient-reported)",
                "पाचन, नींद और मन (रोगी द्वारा बताया गया)",
                "செரிமானம், தூக்கம், மனம் (நோயாளி கூறியது)",
            ),
            "questions": [
                {
                    "code": "appetite_pattern",
                    "type": "single_choice",
                    "text": L(
                        "How is your appetite usually?",
                        "आपकी भूख आमतौर पर कैसी रहती है?",
                        "உங்கள் பசி பொதுவாக எப்படி இருக்கும்?",
                    ),
                    "options": [
                        opt("regular", "Regular", "नियमित", "சீராக"),
                        opt("variable", "Varies a lot", "बदलती रहती है", "மாறுபடும்"),
                        opt("strong", "Very strong", "बहुत तेज़", "மிகவும் அதிகம்"),
                        opt("low", "Low", "कम", "குறைவு"),
                    ],
                },
                {
                    "code": "bowel_pattern",
                    "type": "single_choice",
                    "text": L(
                        "How are your bowel movements usually?",
                        "आपका मल त्याग आमतौर पर कैसा है?",
                        "உங்கள் மலம் கழிப்பு பொதுவாக எப்படி?",
                    ),
                    "options": [
                        opt("soft", "Soft / easy", "नरम / आसान", "மென்மையாக / எளிதாக"),
                        opt("moderate", "Normal", "सामान्य", "இயல்பாக"),
                        opt("hard", "Hard / constipated", "कड़ा / कब्ज़", "கடினமாக / மலச்சிக்கல்"),
                        opt("variable", "Varies", "बदलता रहता है", "மாறுபடும்"),
                    ],
                },
                {
                    "code": "bowel_frequency_per_day",
                    "type": "number",
                    "min": 0,
                    "max": 20,
                    "text": L(
                        "How many times a day do you pass stool?",
                        "दिन में कितनी बार मल त्याग होता है?",
                        "நாளுக்கு எத்தனை முறை மலம் கழிப்பீர்கள்?",
                    ),
                },
                {
                    "code": "urine_frequency_per_day",
                    "type": "number",
                    "min": 0,
                    "max": 40,
                    "text": L(
                        "How many times a day do you pass urine?",
                        "दिन में कितनी बार पेशाब होता है?",
                        "நாளுக்கு எத்தனை முறை சிறுநீர் கழிப்பீர்கள்?",
                    ),
                },
                {
                    "code": "sleep_hours",
                    "type": "number",
                    "min": 0,
                    "max": 24,
                    "unit": "hours",
                    "text": L(
                        "How many hours do you usually sleep?",
                        "आप आमतौर पर कितने घंटे सोते हैं?",
                        "பொதுவாக எத்தனை மணி நேரம் தூங்குவீர்கள்?",
                    ),
                },
                {
                    "code": "sleep_quality",
                    "type": "single_choice",
                    "text": L("How is your sleep?", "आपकी नींद कैसी है?", "உங்கள் தூக்கம் எப்படி?"),
                    "options": [
                        opt("sound", "Sound", "गहरी", "ஆழ்ந்த"),
                        opt("disturbed", "Disturbed", "टूटी-टूटी", "இடையூறான"),
                        opt(
                            "difficulty_falling_asleep",
                            "Hard to fall asleep",
                            "नींद आने में कठिनाई",
                            "தூங்குவதில் சிரமம்",
                        ),
                        opt("excessive", "Sleep too much", "बहुत ज़्यादा", "அதிகமாக"),
                    ],
                },
                {
                    "code": "mental_state",
                    "type": "multi_choice",
                    "text": L(
                        "Recently, have you felt…",
                        "हाल ही में आपने कैसा महसूस किया…",
                        "சமீபத்தில் நீங்கள் உணர்ந்தது…",
                    ),
                    "options": [
                        opt("calm", "Calm", "शांत", "அமைதியாக"),
                        opt("anxious", "Anxious or worried", "चिंतित", "பதற்றமாக"),
                        opt("irritable", "Irritable", "चिड़चिड़ा", "எரிச்சலாக"),
                        opt("low_mood", "Low or sad", "उदास", "சோகமாக"),
                    ],
                },
            ],
        },
        {
            "code": "practitioner_observations",
            "title": L("Practitioner observations (Ashtavidha / Dashavidha Pariksha)"),
            "questions": [
                {
                    "code": "nadi_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Nadi (pulse) observation"),
                },
                {
                    "code": "mutra_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Mutra (urine) observation"),
                },
                {
                    "code": "mala_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Mala (stool) observation"),
                },
                {
                    "code": "jihva_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Jihva (tongue) observation"),
                },
                {
                    "code": "shabda_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Shabda (voice/sounds) observation"),
                },
                {
                    "code": "sparsha_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Sparsha (touch) observation"),
                },
                {
                    "code": "drik_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Drik (eyes) observation"),
                },
                {
                    "code": "akriti_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Akriti (general build) observation"),
                },
                {
                    "code": "agni_observation",
                    "type": "text",
                    "respondent": "practitioner",
                    "text": L("Agni assessment notes (practitioner judgement)"),
                },
                {
                    "code": "ama_signs",
                    "type": "single_choice",
                    "respondent": "practitioner",
                    "text": L("Ama-related signs"),
                    "options": [
                        opt("not_observed", "Not observed"),
                        opt("observed", "Observed"),
                        opt("uncertain", "Uncertain"),
                    ],
                },
                {
                    "code": "koshta_assessment",
                    "type": "single_choice",
                    "respondent": "practitioner",
                    "text": L("Koshta (practitioner assessment)"),
                    "options": [
                        opt("mridu", "Mridu"),
                        opt("madhya", "Madhya"),
                        opt("krura", "Krura"),
                        opt("not_assessed", "Not assessed"),
                    ],
                },
                {
                    "code": "prakriti_status",
                    "type": "single_choice",
                    "respondent": "practitioner",
                    "text": L("Prakriti assessment status"),
                    "help": L(
                        "The system never infers Prakriti. Record only a practitioner's own assessment."
                    ),
                    "options": [
                        opt("not_assessed", "Not assessed"),
                        opt("in_progress", "Assessment in progress"),
                        opt("assessed", "Assessed by practitioner"),
                    ],
                },
                {
                    "code": "prakriti_notes",
                    "type": "long_text",
                    "respondent": "practitioner",
                    "required": True,
                    "show_if": {"question": "prakriti_status", "op": "equals", "value": "assessed"},
                    "text": L("Practitioner's Prakriti assessment"),
                },
                {
                    "code": "vikriti_notes",
                    "type": "long_text",
                    "respondent": "practitioner",
                    "text": L("Practitioner's Vikriti notes"),
                },
                {
                    "code": "dashavidha_notes",
                    "type": "long_text",
                    "respondent": "practitioner",
                    "text": L("Dashavidha Pariksha notes"),
                },
            ],
        },
    ],
}
