"""Donor-facing message wording in regional languages, and the phone-app screen words.
Languages: English, Hindi, Marathi, Tamil, Telugu, Bengali, Gujarati, Kannada.
IMPORTANT: these sentences are standard, simple wording, but please have a native speaker of each language read them
once before you send them to donors. You can edit any of them: they are plain text in the Message templates list.
Placeholders in {braces} are filled in automatically."""

LANGS = ["English", "Hindi", "Marathi", "Tamil", "Telugu", "Bengali", "Gujarati", "Kannada"]
CODE = {"English": "en", "Hindi": "hi", "Marathi": "mr", "Tamil": "ta", "Telugu": "te", "Bengali": "bn", "Gujarati": "gu", "Kannada": "kn"}

MSG = {
 "thanks": {
  "English": "Dear {first_name}, thank you for your gift to {org}. Because of friends like you, our work continues. {contact}",
  "Hindi": "प्रिय {first_name}, {org} को आपके सहयोग के लिए धन्यवाद। आप जैसे साथियों के कारण ही हमारा काम जारी है। {contact}",
  "Marathi": "प्रिय {first_name}, {org} ला केलेल्या मदतीबद्दल धन्यवाद. तुमच्यासारख्या मित्रांमुळेच आमचे काम सुरू आहे. {contact}",
  "Tamil": "அன்புள்ள {first_name}, {org} அமைப்புக்கு உங்கள் நன்கொடைக்கு நன்றி. உங்களைப் போன்ற நண்பர்களால்தான் எங்கள் பணி தொடர்கிறது. {contact}",
  "Telugu": "ప్రియమైన {first_name}, {org} కు మీ విరాళానికి ధన్యవాదాలు. మీలాంటి మిత్రుల వల్లే మా పని కొనసాగుతోంది. {contact}",
  "Bengali": "প্রিয় {first_name}, {org}-কে আপনার দানের জন্য ধন্যবাদ। আপনার মতো বন্ধুদের জন্যই আমাদের কাজ চলছে। {contact}",
  "Gujarati": "પ્રિય {first_name}, {org} ને તમારા દાન બદલ આભાર. તમારા જેવા મિત્રોને કારણે જ અમારું કામ ચાલુ છે. {contact}",
  "Kannada": "ಪ್ರಿಯ {first_name}, {org} ಗೆ ನಿಮ್ಮ ದೇಣಿಗೆಗೆ ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮಂತಹ ಸ್ನೇಹಿತರಿಂದಲೇ ನಮ್ಮ ಕೆಲಸ ಮುಂದುವರಿಯುತ್ತಿದೆ. {contact}"},
 "festival": {
  "English": "Dear {first_name}, warm festival wishes to you and your family from {org}. {contact}",
  "Hindi": "प्रिय {first_name}, {org} की ओर से आपको और आपके परिवार को त्योहार की हार्दिक शुभकामनाएँ। {contact}",
  "Marathi": "प्रिय {first_name}, {org} तर्फे तुम्हाला आणि तुमच्या कुटुंबाला सणाच्या हार्दिक शुभेच्छा. {contact}",
  "Tamil": "அன்புள்ள {first_name}, {org} சார்பாக உங்களுக்கும் உங்கள் குடும்பத்தினருக்கும் இனிய பண்டிகை வாழ்த்துகள். {contact}",
  "Telugu": "ప్రియమైన {first_name}, {org} తరఫున మీకు, మీ కుటుంబానికి పండుగ శుభాకాంక్షలు. {contact}",
  "Bengali": "প্রিয় {first_name}, {org}-এর পক্ষ থেকে আপনাকে ও আপনার পরিবারকে উৎসবের আন্তরিক শুভেচ্ছা। {contact}",
  "Gujarati": "પ્રિય {first_name}, {org} તરફથી તમને અને તમારા પરિવારને તહેવારની હાર્દિક શુભેચ્છાઓ. {contact}",
  "Kannada": "ಪ್ರಿಯ {first_name}, {org} ಪರವಾಗಿ ನಿಮಗೂ ನಿಮ್ಮ ಕುಟುಂಬಕ್ಕೂ ಹಬ್ಬದ ಹಾರ್ದಿಕ ಶುಭಾಶಯಗಳು. {contact}"},
 "miss_you": {
  "English": "Dear {first_name}, it has been a while. Thank you for standing with {org}. We would love to share what your support has done. Reply here or call us any time. {contact}",
  "Hindi": "प्रिय {first_name}, काफ़ी समय हो गया। {org} का साथ देने के लिए धन्यवाद। हम आपको बताना चाहेंगे कि आपके सहयोग से क्या बदलाव आया। कृपया यहीं उत्तर दें या हमें कभी भी फ़ोन करें। {contact}",
  "Marathi": "प्रिय {first_name}, बराच काळ लोटला. {org} ला साथ दिल्याबद्दल धन्यवाद. तुमच्या मदतीमुळे काय बदल घडला हे तुम्हाला सांगायला आम्हाला आवडेल. कृपया येथेच उत्तर द्या किंवा आम्हाला केव्हाही फोन करा. {contact}",
  "Tamil": "அன்புள்ள {first_name}, நீண்ட நாட்கள் ஆகிவிட்டன. {org} அமைப்புக்கு துணை நின்றதற்கு நன்றி. உங்கள் உதவியால் நடந்த மாற்றங்களை உங்களுடன் பகிர்ந்துகொள்ள விரும்புகிறோம். இங்கேயே பதில் அனுப்புங்கள் அல்லது எப்போது வேண்டுமானாலும் எங்களை அழையுங்கள். {contact}",
  "Telugu": "ప్రియమైన {first_name}, చాలా కాలం అయింది. {org} కు తోడుగా నిలిచినందుకు ధన్యవాదాలు. మీ సహాయంతో జరిగిన మార్పులను మీతో పంచుకోవాలని మేము ఆశిస్తున్నాము. ఇక్కడే సమాధానం ఇవ్వండి లేదా ఎప్పుడైనా మాకు ఫోన్ చేయండి. {contact}",
  "Bengali": "প্রিয় {first_name}, অনেকদিন হয়ে গেছে। {org}-এর পাশে থাকার জন্য ধন্যবাদ। আপনার সহায়তায় কী পরিবর্তন এসেছে তা আপনাকে জানাতে চাই। এখানেই উত্তর দিন অথবা যেকোনো সময় আমাদের ফোন করুন। {contact}",
  "Gujarati": "પ્રિય {first_name}, ઘણો સમય થઈ ગયો. {org} ને સાથ આપવા બદલ આભાર. તમારી મદદથી શું બદલાવ આવ્યો તે તમને જણાવવા અમે ઇચ્છીએ છીએ. અહીં જ જવાબ આપો અથવા ગમે ત્યારે અમને ફોન કરો. {contact}",
  "Kannada": "ಪ್ರಿಯ {first_name}, ಬಹಳ ಸಮಯವಾಗಿದೆ. {org} ಜೊತೆ ನಿಂತಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ಸಹಾಯದಿಂದ ಏನು ಬದಲಾವಣೆ ಆಯಿತು ಎಂಬುದನ್ನು ನಿಮಗೆ ತಿಳಿಸಲು ನಾವು ಬಯಸುತ್ತೇವೆ. ಇಲ್ಲಿಯೇ ಉತ್ತರಿಸಿ ಅಥವಾ ಯಾವಾಗ ಬೇಕಾದರೂ ನಮಗೆ ಕರೆ ಮಾಡಿ. {contact}"},
 "lapse": {
  "English": "Dear {first_name}, it has been a while since your last gift of ₹{last_amount} on {last_date}. Thank you for standing with {org}. We would love to share what your support has done. Reply here or call us any time. {contact}",
  "Hindi": "प्रिय {first_name}, {last_date} को आपके ₹{last_amount} के सहयोग को काफ़ी समय हो गया। {org} का साथ देने के लिए धन्यवाद। हम आपको बताना चाहेंगे कि आपके सहयोग से क्या बदलाव आया। कृपया यहीं उत्तर दें या हमें कभी भी फ़ोन करें। {contact}",
  "Marathi": "प्रिय {first_name}, {last_date} रोजी तुम्ही दिलेल्या ₹{last_amount} च्या मदतीला बराच काळ लोटला. {org} ला साथ दिल्याबद्दल धन्यवाद. तुमच्या मदतीमुळे काय बदल घडला हे तुम्हाला सांगायला आम्हाला आवडेल. कृपया येथेच उत्तर द्या किंवा आम्हाला केव्हाही फोन करा. {contact}",
  "Tamil": "அன்புள்ள {first_name}, {last_date} அன்று நீங்கள் வழங்கிய ₹{last_amount} நன்கொடைக்குப் பிறகு நீண்ட நாட்கள் ஆகிவிட்டன. {org} அமைப்புக்கு துணை நின்றதற்கு நன்றி. உங்கள் உதவியால் நடந்த மாற்றங்களை உங்களுடன் பகிர்ந்துகொள்ள விரும்புகிறோம். இங்கேயே பதில் அனுப்புங்கள் அல்லது எப்போது வேண்டுமானாலும் எங்களை அழையுங்கள். {contact}",
  "Telugu": "ప్రియమైన {first_name}, {last_date} న మీరు ఇచ్చిన ₹{last_amount} విరాళం తర్వాత చాలా కాలం గడిచింది. {org} కు తోడుగా నిలిచినందుకు ధన్యవాదాలు. మీ సహాయంతో జరిగిన మార్పులను మీతో పంచుకోవాలని మేము ఆశిస్తున్నాము. ఇక్కడే సమాధానం ఇవ్వండి లేదా ఎప్పుడైనా మాకు ఫోన్ చేయండి. {contact}",
  "Bengali": "প্রিয় {first_name}, {last_date} তারিখে আপনার ₹{last_amount} দানের পর অনেকদিন হয়ে গেছে। {org}-এর পাশে থাকার জন্য ধন্যবাদ। আপনার সহায়তায় কী পরিবর্তন এসেছে তা আপনাকে জানাতে চাই। এখানেই উত্তর দিন অথবা যেকোনো সময় আমাদের ফোন করুন। {contact}",
  "Gujarati": "પ્રિય {first_name}, {last_date} ના રોજ તમે આપેલા ₹{last_amount} ના દાનને ઘણો સમય થઈ ગયો. {org} ને સાથ આપવા બદલ આભાર. તમારી મદદથી શું બદલાવ આવ્યો તે તમને જણાવવા અમે ઇચ્છીએ છીએ. અહીં જ જવાબ આપો અથવા ગમે ત્યારે અમને ફોન કરો. {contact}",
  "Kannada": "ಪ್ರಿಯ {first_name}, {last_date} ರಂದು ನೀವು ನೀಡಿದ ₹{last_amount} ದೇಣಿಗೆಯ ನಂತರ ಬಹಳ ಸಮಯವಾಗಿದೆ. {org} ಜೊತೆ ನಿಂತಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ಸಹಾಯದಿಂದ ಏನು ಬದಲಾವಣೆ ಆಯಿತು ಎಂಬುದನ್ನು ನಿಮಗೆ ತಿಳಿಸಲು ನಾವು ಬಯಸುತ್ತೇವೆ. ಇಲ್ಲಿಯೇ ಉತ್ತರಿಸಿ ಅಥವಾ ಯಾವಾಗ ಬೇಕಾದರೂ ನಮಗೆ ಕರೆ ಮಾಡಿ. {contact}"},
 "pledge_due": {
  "English": "Dear {first_name}, a gentle reminder that your regular gift of ₹{amount} to {org} is due on {due}. Thank you for your steady support. UPI: {upi}. {contact}",
  "Hindi": "प्रिय {first_name}, यह एक विनम्र स्मरण है कि {org} के लिए आपका नियमित सहयोग ₹{amount} {due} को देय है। आपके निरंतर साथ के लिए धन्यवाद। UPI: {upi}। {contact}",
  "Marathi": "प्रिय {first_name}, {org} साठी तुमची नियमित मदत ₹{amount} {due} रोजी देय आहे, याची ही नम्र आठवण. तुमच्या सततच्या साथीबद्दल धन्यवाद. UPI: {upi}. {contact}",
  "Tamil": "அன்புள்ள {first_name}, {org} அமைப்புக்கான உங்கள் வழக்கமான நன்கொடை ₹{amount} {due} அன்று செலுத்த வேண்டியது என்பதற்கான அன்பான நினைவூட்டல். உங்கள் தொடர்ந்த ஆதரவுக்கு நன்றி. UPI: {upi}. {contact}",
  "Telugu": "ప్రియమైన {first_name}, {org} కు మీ క్రమం తప్పని విరాళం ₹{amount} {due} న చెల్లించాల్సి ఉందని మర్యాదపూర్వక గుర్తుచేత. మీ నిరంతర మద్దతుకు ధన్యవాదాలు. UPI: {upi}. {contact}",
  "Bengali": "প্রিয় {first_name}, {org}-এর জন্য আপনার নিয়মিত দান ₹{amount} {due} তারিখে দেয়, এটি একটি বিনীত মনে করিয়ে দেওয়া। আপনার নিরন্তর সহযোগিতার জন্য ধন্যবাদ। UPI: {upi}। {contact}",
  "Gujarati": "પ્રિય {first_name}, {org} માટે તમારું નિયમિત દાન ₹{amount} {due} ના રોજ બાકી છે, તેની આ નમ્ર યાદ. તમારા સતત સાથ બદલ આભાર. UPI: {upi}. {contact}",
  "Kannada": "ಪ್ರಿಯ {first_name}, {org} ಗೆ ನಿಮ್ಮ ನಿಯಮಿತ ದೇಣಿಗೆ ₹{amount} {due} ರಂದು ಪಾವತಿಸಬೇಕಿದೆ ಎಂಬ ವಿನಮ್ರ ಜ್ಞಾಪನೆ. ನಿಮ್ಮ ನಿರಂತರ ಬೆಂಬಲಕ್ಕೆ ಧನ್ಯವಾದಗಳು. UPI: {upi}. {contact}"},
}
LABEL = {"thanks": "thank-you", "festival": "festival greeting", "miss_you": "we miss you"}
SEED_KINDS = ("thanks", "festival", "miss_you")      # these use only the merge fields the broadcast page understands

def render(kind, language, vals):
    lang = language if language in LANGS else "English"
    t = MSG[kind][lang]
    for k, v in vals.items(): t = t.replace("{" + k + "}", str(v if v is not None else ""))
    return " ".join(t.replace(" .", ".").split()).strip()

def seed_templates(c):
    """Add a ready template for every language (once; your edits are never overwritten)."""
    for lang in LANGS[1:]:
        for kind in SEED_KINDS:
            c.execute("INSERT OR IGNORE INTO templates(name,subject,body,channel) VALUES(?,?,?,'Email')", (f"{lang}: {LABEL[kind]}", "{org}", MSG[kind][lang]))
