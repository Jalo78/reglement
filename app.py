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

# Pagina instellingen (Titel in browser tabblad, icoontje)
st.set_page_config(page_title="Ligo Assistent", page_icon="🏫")

# Waarschuwingen onderdrukken voor een schone log
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")

# --- VEILIGE SLEUTEL TOEGANG ---
# Hier controleren we of de sleutel in de veilige kluis zit.
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
else:
    # Als er geen sleutel is (bijv. lokaal zonder secrets.toml), stop de app.
    st.error("⛔ CRITICALE FOUT: Geen API-sleutel gevonden.")
    st.info("Ben je de beheerder? Voeg 'GOOGLE_API_KEY' toe aan de Streamlit Secrets.")
    st.stop() # Stop de app hier, ga niet verder.

# ---------------------------------------------------------
# FUNCTIES
# ---------------------------------------------------------

@st.cache_data # Dit zorgt dat we de PDF maar 1x hoeven te lezen (sneller!)
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
# DE APPLICATIE (UI)
# ---------------------------------------------------------

st.title("🏫 Vraag het aan het Centrum")
st.write("Druk op de knop, spreek je vraag in en luister naar het antwoord.")

# 1. Laad het reglement
reglement_tekst = laad_pdf_automatisch()

if reglement_tekst is None:
    st.error("⚠️ Oeps! Het bestand 'reglement.pdf' ontbreekt.")
    st.warning("Upload 'reglement.pdf' naar je GitHub map naast dit bestand.")
else:
    # Als de PDF er is, tonen we een scheidingslijn en de microfoon
    st.divider()
    
    # 2. De Audio Knop
    audio_opname = st.audio_input("Start opname 🎤")

    if audio_opname:
        with st.spinner("Even luisteren en vertalen... 🧠"):
            try:
                # We gebruiken het snelle Flash model
                model = genai.GenerativeModel("gemini-2.5-flash")
                
                # De 'System Prompt' - De strenge instructies voor de AI
                prompt = f"""
                CONTEXT (BRONTEKST):
                {reglement_tekst}
                
                JOUW TAAK:
                Je bent een behulpzame assistent voor laaggeletterde cursisten.
                1. Luister naar de audio input.
                2. Detecteer de taal van de spreker.
                3. Zoek het antwoord in de Nederlandse brontekst.
                4. Vertaal het antwoord naar de taal van de spreker.
                
                BELANGRIJKE REGELS:
                - Antwoord altijd in de taal van de vraag (Engels -> Engels, Arabisch -> Arabisch).
                - Houd het antwoord kort, vriendelijk en simpel (Niveau A1/A2).
                - Als het antwoord niet in de tekst staat, zeg: "Dat weet ik niet, vraag het aan je leerkracht."
                
                OUTPUT FORMAAT (JSON):
                Geef ALLEEN een JSON object terug met deze velden:
                {{
                    "taal_code": "de 2-letterige taalcode (bijv: nl, en, ar, fr)",
                    "lees_tekst": "Het antwoord in correcte spelling voor op het scherm",
                    "luister_tekst": "Het antwoord fonetisch geschreven voor de computerstem (zodat uitspraak klopt)"
                }}
                """

                # Lees audio bytes
                audio_bytes = audio_opname.read()
                
                # Stuur naar Google
                response = model.generate_content([
                    prompt,
                    {"mime_type": "audio/wav", "data": audio_bytes}
                ])
                
                # JSON Opschonen (soms zet AI er ```json ... ``` omheen)
                ruwe_json = response.text.replace('```json', '').replace('```', '').strip()
                
                # Omzetten naar Python data
                data = json.loads(ruwe_json)
                
                taal = data.get("taal_code", "nl")
                tekst_scherm = data.get("lees_tekst", "Sorry, ik begreep het niet.")
                tekst_audio = data.get("luister_tekst", tekst_scherm)
                
                # 3. Resultaat Tonen
                st.success(f"🗣️ **Antwoord:** {tekst_scherm}")
                
                # 4. Audio Genereren en Afspelen
                tts = gTTS(text=tekst_audio, lang=taal)
                
                # Tijdelijk bestand aanmaken
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    tts.save(fp.name)
                    st.audio(fp.name, format="audio/mp3", autoplay=True)
                    
            except Exception as e:
                st.error("Er ging iets mis bij de verwerking.")
                # Voor debugging (alleen aanzetten als je zelf test):
                # st.write(e)