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
    
    # 2. De Audio Knop
    audio_opname = st.audio_input("Start opname 🎤")

    if audio_opname:
        with st.spinner("Even luisteren en vertalen... 🧠"):
            try:
                # Model aanroepen
                model = genai.GenerativeModel("gemini-2.5-flash")
                
                # --- DE MAGISCHE INSTRUCTIES (PROMPT) ---
                # Hier vertellen we de AI hoe hij met uitspraak moet omgaan.
                prompt = f"""
                CONTEXT (BRONTEKST):
                {reglement_tekst}
                
                JOUW TAAK:
                1. Luister naar de audio.
                2. Detecteer de taal.
                3. Zoek het antwoord in de brontekst.
                4. Vertaal het antwoord naar de taal van de spreker.
                
                CRUCIAAL VOOR UITSPRAAK (FONETISCH):
                Computerstemmen maken fouten. Jij moet dat corrigeren in de 'luister_tekst'.
                Schrijf de 'luister_tekst' precies zoals je het moet UITSPREKEN.
                
                Voorbeelden van correcties die jij moet toepassen:
                - Nederlands woord 'les' -> Schrijf 'less' (anders zegt hij 'lee').
                - Nederlands woord 'PC' -> Schrijf 'pee see'.
                - Engels woord 'WiFi' -> Schrijf 'wai fai' (als de taal anders is).
                - Frans leenwoord in NL -> Schrijf het fonetisch.
                
                OUTPUT FORMAAT (JSON):
                {{
                    "taal_code": "nl",
                    "lees_tekst": "Hier de nette tekst met juiste spelling (bijv: De les begint).",
                    "luister_tekst": "Hier de fonetische tekst voor de computer (bijv: De less begint)."
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
                tekst_scherm = data.get("lees_tekst", "Sorry, ik begreep het niet.")
                tekst_audio = data.get("luister_tekst", tekst_scherm)
                
                # 3. Resultaat Tonen
                st.success(f"🗣️ **Antwoord:** {tekst_scherm}")
                
                # (Optioneel: Laat zien wat hij stiekem leest om te testen)
                # st.caption(f"Debug (Audio leest): {tekst_audio}")
                
                # 4. Audio Genereren en Afspelen
                tts = gTTS(text=tekst_audio, lang=taal)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    tts.save(fp.name)
                    st.audio(fp.name, format="audio/mp3", autoplay=True)
                    
            except Exception as e:
                st.error(f"Technische foutmelding: {e}")
