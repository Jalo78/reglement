import streamlit as st
import warnings
import os
import google.generativeai as genai 
from gtts import gTTS
import PyPDF2
import json
import io
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------
# CONFIGURATIE
# ---------------------------------------------------------
st.set_page_config(page_title="Ligo Assistent", page_icon="🏫")
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")

# 1. API Sleutel Check
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
else:
    st.error("⛔ CRITICALE FOUT: Geen API-sleutel gevonden in Secrets.")
    st.stop()

# 2. Admin Wachtwoord Check
ADMIN_WW = st.secrets.get("ADMIN_WACHTWOORD", "admin")

# Sessie status voor de reset knop
if 'vraag_teller' not in st.session_state:
    st.session_state.vraag_teller = 0

def reset_app():
    st.session_state.vraag_teller += 1

# ---------------------------------------------------------
# FUNCTIES
# ---------------------------------------------------------

@st.cache_data
def laad_documenten_automatisch():
    """Zoekt en leest zowel reglement.pdf als kalender.pdf"""
    bestanden = ["reglement.pdf", "kalender.pdf"]
    alle_tekst = ""
    
    for bestand_naam in bestanden:
        if os.path.exists(bestand_naam):
            try:
                with open(bestand_naam, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    alle_tekst += f"\n--- INHOUD VAN {bestand_naam.upper()} ---\n"
                    for page in reader.pages:
                        alle_tekst += page.extract_text() + "\n"
            except Exception as e:
                st.warning(f"Fout bij lezen van {bestand_naam}: {e}")
        else:
            st.warning(f"⚠️ Bestand '{bestand_naam}' ontbreekt in de map.")
            
    return alle_tekst if alle_tekst.strip() else None

def repareer_uitspraak(tekst, taal):
    if taal == 'nl':
        tekst = tekst.replace(" les ", " less ").replace(" les.", " less.")
        tekst = tekst.replace(" les,", " less,").replace(" Les ", " Less ")
    return tekst

def log_gemiste_vraag(vraag_orig, vraag_nl, taal):
    bestand = "gemiste_vragen.csv"
    nieuwe_data = pd.DataFrame([{
        "Datum": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Taal": taal,
        "Originele Vraag": vraag_orig,
        "Vraag in NL": vraag_nl
    }])
    
    if os.path.exists(bestand):
        try:
            nieuwe_data.to_csv(bestand, mode='a', header=False, index=False)
        except:
            nieuwe_data.to_csv(bestand, mode='w', header=True, index=False)
    else:
        nieuwe_data.to_csv(bestand, mode='w', header=True, index=False)

# ---------------------------------------------------------
# DE APPLICATIE
# ---------------------------------------------------------

# --- ZIJBALK (DOCENTEN) ---
with st.sidebar:
    st.header("🔐 Docenten Login")
    invoer_ww = st.text_input("Wachtwoord", type="password")
    
    if invoer_ww == ADMIN_WW:
        st.success("Toegang verleend ✅")
        st.divider()
        st.subheader("📋 Logboek Gemiste Vragen")
        
        if os.path.exists("gemiste_vragen.csv"):
            try:
                df = pd.read_csv("gemiste_vragen.csv")
                st.dataframe(df)
                
                csv_data = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download Excel (CSV)",
                    csv_data,
                    "gemiste_vragen.csv",
                    "text/csv"
                )
                
                if st.button("🗑️ Wis logboek"):
                    os.remove("gemiste_vragen.csv")
                    st.rerun()
            except:
                st.error("Het logboek is beschadigd.")
                if st.button("🗑️ Reset logboek"):
                    os.remove("gemiste_vragen.csv")
                    st.rerun()
        else:
            st.info("Nog geen gemiste vragen.")

# --- HOOFDSCHERM ---
st.title("🏫 Vraag het aan het Centrum")
st.write("Druk op de knop, spreek je vraag in en luister naar het antwoord.")

documenten_tekst = laad_documenten_automatisch()

if documenten_tekst is None:
    st.error("⚠️ Geen documenten gevonden. Zorg voor reglement.pdf en kalender.pdf.")
else:
    st.divider()
    
    audio_opname = st.audio_input(
        "Start opname 🎤", 
        key=f"audio_recorder_{st.session_state.vraag_teller}"
    )

    if audio_opname:
        with st.spinner("Even luisteren en zoeken... 🧠"):
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                
                # We halen de datum van vandaag op (inclusief weekdag)
                vandaag_str = datetime.now().strftime("%A %d %B %Y (tijd: %H:%M)")
                
                # --- AANGEPASTE PROMPT MET DATUM EN MULTIPLE DOCS ---
                prompt = f"""
                HUIDIGE DATUM EN TIJD:
                Vandaag is het {vandaag_str}. Gebruik dit als iemand vraagt naar 'vandaag', 'morgen', of een specifieke datum.
                
                CONTEXT (BRONTEKSTEN):
                {documenten_tekst}
                
                JOUW TAAK:
                1. Luister naar de audio en schrijf de vraag uit (transcriptie).
                2. Vertaal deze vraag ook naar het NEDERLANDS (voor het logboek).
                3. Zoek het antwoord in de bronteksten (reglement of kalender).
                4. Bepaal: Staat het antwoord in de teksten of kun je het afleiden uit de kalender? (Ja/Nee).
                5. Vertaal het antwoord naar de taal van de spreker.
                
                REGELS:
                - GEVONDEN? -> Geef een vriendelijke uitleg (2-3 zinnen, A2 niveau).
                - NIET GEVONDEN? -> Zeg "Dat staat niet in de informatie." EN voeg toe: "Vraag het aan je klasleerkracht of ga naar het onthaal." (Vertaal dit!).
                
                OUTPUT FORMAAT (JSON):
                {{
                    "taal_code": "code (bv: en, ar, fr)",
                    "vraag_orig": "De vraag in de originele taal",
                    "vraag_nl": "De vraag vertaald naar het Nederlands",
                    "antwoord_gevonden": true of false,
                    "antwoord_tekst": "Het antwoord voor de cursist"
                }}
                """

                audio_bytes = audio_opname.read()
                
                response = model.generate_content([
                    prompt,
                    {"mime_type": "audio/wav", "data": audio_bytes}
                ])
                
                ruwe_json = response.text.replace('```json', '').replace('```', '').strip()
                data = json.loads(ruwe_json)
                
                taal = data.get("taal_code", "nl")
                vraag_orig = data.get("vraag_orig", "")
                vraag_nl = data.get("vraag_nl", "")
                gevonden = data.get("antwoord_gevonden", True)
                antwoord = data.get("antwoord_tekst", "Sorry, ik begreep het niet.")
                
                if gevonden is False:
                    log_gemiste_vraag(vraag_orig, vraag_nl, taal)

                st.success(f"🗣️ **Antwoord:** {antwoord}")
                
                spraak_tekst = repareer_uitspraak(antwoord, taal)
                mp3_fp = io.BytesIO()
                tts = gTTS(text=spraak_tekst, lang=taal)
                tts.write_to_fp(mp3_fp)
                st.audio(mp3_fp, format="audio/mpeg", autoplay=True)
                
                st.write("") 
                st.button("🔄 Stel een nieuwe vraag", on_click=reset_app)
                    
            except Exception as e:
                st.error(f"Technische foutmelding: {e}")
