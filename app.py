import streamlit as st
import warnings
import os
import google.generativeai as genai 
from gtts import gTTS
import PyPDF2
import json
import tempfile

# ---------------------------------------------------------
# CONFIGURATIE & VEILIGHEID
# ---------------------------------------------------------

st.set_page_config(page_title="Ligo Assistent", page_icon="🏫")

# Waarschuwingen onderdrukken
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")

# --- VEILIGE SLEUTEL TOEGANG ---
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
else:
    st.error("⛔ CRITICALE FOUT: Geen API-sleutel gevonden in Secrets.")
    st.stop()

# --- SESSIE STATUS (Het geheugen voor de reset-knop) ---
if 'vraag_teller' not in st.session_state:
    st.session_state.vraag_teller = 0

def reset_app():
    """Deze functie wordt uitgevoerd als je op de reset knop drukt"""
    st.session_state.vraag_teller += 1

# ---------------------------------------------------------
# FUNCTIES
# ---------------------------------------------------------

@st.cache_data
def laad_pdf_automatisch():
    """Zoekt en leest reglement.pdf in dezelfde map."""
    bestand_naam = "reglement.pdf"
    if os.path.exists(bestand_naam):
        try:
            with open(bestand_naam, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                tekst = ""
                for page in reader.pages:
                    tekst += page.extract_text()
            return tekst
        except Exception as e:
            st.error(f"Fout bij lezen PDF: {e}")
            return None
    else:
        return None

def repareer_uitspraak(tekst, taal):
    """Repareert uitspraakfouten (zoals 'les' -> 'less')"""
    if taal == 'nl':
        # Vervang 'les' door 'less' zodat het niet als 'lee' klinkt
        tekst = tekst.replace(" les ", " less ")
        tekst = tekst.replace(" les.", " less.")
        tekst = tekst.replace(" les,", " less,")
        tekst = tekst.replace(" Les ", " Less ")
    return tekst

# ---------------------------------------------------------
# DE APPLICATIE
# ---------------------------------------------------------

st.title("🏫 Vraag het aan het Centrum")
st.write("Druk op de knop, spreek je vraag in en luister naar het antwoord.")

# 1. Laad het reglement
reglement_tekst = laad_pdf_automatisch()

if reglement_tekst is None:
    st.error("⚠️ Oeps! Het bestand 'reglement.pdf' ontbreekt.")
else:
    st.divider()
    
    # 2. De Audio Knop (Met dynamische key!)
    # Door de 'key' te veranderen (vraag_teller), wordt de widget leeggemaakt.
    audio_opname = st.audio_input(
        "Start opname 🎤", 
        key=f"audio_recorder_{st.session_state.vraag_teller}"
    )

    if audio_opname:
        with st.spinner("Even luisteren en vertalen... 🧠"):
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                
                # --- PROMPT (Volledig & Vriendelijk) ---
                prompt = f"""
                CONTEXT (BRONTEKST):
                {reglement_tekst}
                
                JOUW TAAK:
                1. Luister naar de audio.
                2. Detecteer de taal.
                3. Zoek het antwoord in de Nederlandse brontekst.
                4. Vertaal het antwoord naar de taal van de spreker.
                
                BELANGRIJKE REGELS:
                - Antwoord in de taal van de vraag.
                - Geef een VOLLEDIG antwoord. Niet te kortaf.
                - Leg het vriendelijk uit in 2 of 3 zinnen.
                - Gebruik simpele woorden (Niveau A2).
                
                OUTPUT FORMAAT (JSON):
                {{
                    "taal_code": "nl",
                    "antwoord": "Hier het volledige, vriendelijke antwoord."
                }}
                """

                # Lees audio bytes
                audio_bytes = audio_opname.read()
                
                # Stuur naar Google
                response = model.generate_content([
                    prompt,
                    {"mime_type": "audio/wav", "data": audio_bytes}
                ])
                
                # JSON verwerken
                ruwe_json = response.text.replace('```json', '').replace('```', '').strip()
                data = json.loads(ruwe_json)
                
                taal = data.get("taal_code", "nl")
                antwoord = data.get("antwoord", "Sorry, ik begreep het niet.")
                
                # 3. Resultaat Tonen
                st.success(f"🗣️ **Antwoord:** {antwoord}")
                
                # --- DE UITSPRAAK REPARATIE ---
                spraak_tekst = repareer_uitspraak(antwoord, taal)
                
                # 4. Audio Genereren en Afspelen
                tts = gTTS(text=spraak_tekst, lang=taal)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    tts.save(fp.name)
                    st.audio(fp.name, format="audio/mp3", autoplay=True)
                
                # 5. KNOP OM OPNIEUW TE BEGINNEN
                st.write("") # Witregel
                # Als je hierop drukt, wordt 'reset_app' uitgevoerd, verhoogt de teller, en reset de microfoon.
                st.button("🔄 Stel een nieuwe vraag", on_click=reset_app)
                    
            except Exception as e:
                st.error(f"Technische foutmelding: {e}")
