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

# 2. Admin Wachtwoord Check (standaard 'admin' als je niks instelt)
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
def laad_pdf_automatisch():
    bestand_naam = "reglement.pdf"
    if os.path.exists(bestand_naam):
        try:
            with open(bestand_naam, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                tekst = ""
                for page in reader.pages:
                    tekst += page.extract_text()
            return tekst
        except Exception:
            return None
    return None

def repareer_uitspraak(tekst, taal):
    if taal == 'nl':
        tekst = tekst.replace(" les ", " less ").replace(" les.", " less.")
        tekst = tekst.replace(" les,", " less,").replace(" Les ", " Less ")
    return tekst

def log_gemiste_vraag(vraag_orig, vraag_nl, taal):
    """Schrijft de vraag + vertaling weg naar CSV"""
    bestand = "gemiste_vragen.csv"
    
    # Hier maken we de rij met 4 kolommen
    nieuwe_data = pd.DataFrame([{
        "Datum": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Taal": taal,
        "Originele Vraag": vraag_orig,
        "Vraag in NL": vraag_nl
    }])
    
    if os.path.exists(bestand):
        # We voegen toe aan bestaand bestand
        # Let op: als het oude bestand minder kolommen heeft, geeft dit een fout.
        # Daarom best eerst wissen.
        try:
            nieuwe_data.to_csv(bestand, mode='a', header=False, index=False)
        except:
            # Als het misgaat (bijv oude versie), overschrijven we het
            nieuwe_data.to_csv(bestand, mode='w', header=True, index=False)
    else:
        # Nieuw bestand maken
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
                st.dataframe(df) # Toon tabel
                
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
                st.error("Het logboek is beschadigd of verouderd.")
                if st.button("🗑️ Reset logboek"):
                    os.remove("gemiste_vragen.csv")
                    st.rerun()
        else:
            st.info("Nog geen gemiste vragen.")

# --- HOOFDSCHERM ---
st.title("🏫 Vraag het aan het Centrum")
st.write("Druk op de knop, spreek je vraag in en luister naar het antwoord.")

reglement_tekst = laad_pdf_automatisch()

if reglement_tekst is None:
    st.error("⚠️ Oeps! Het bestand 'reglement.pdf' ontbreekt.")
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
                
                # --- AANGEPASTE PROMPT MET VERTALING ---
                prompt = f"""
                CONTEXT (BRONTEKST):
                {reglement_tekst}
                
                JOUW TAAK:
                1. Luister naar de audio en schrijf de vraag uit (transcriptie).
                2. Vertaal deze vraag ook naar het NEDERLANDS (voor het logboek).
                3. Zoek het antwoord in de brontekst.
                4. Bepaal: Staat het antwoord in de tekst? (Ja/Nee).
                5. Vertaal het antwoord naar de taal van de spreker.
                
                REGELS:
                - GEVONDEN? -> Geef een vriendelijke uitleg (2-3 zinnen, A2 niveau).
                - NIET GEVONDEN? -> Zeg "Dat staat niet in het reglement." EN voeg toe: "Vraag het aan je klasleerkracht of ga naar het onthaal." (Vertaal dit!).
                
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
                
                # LOGICA: Opslaan als niet gevonden
                # We sturen nu ZOWEL origineel ALS vertaling naar de functie
                if gevonden is False:
                    log_gemiste_vraag(vraag_orig, vraag_nl, taal)

                # Resultaat tonen
                st.success(f"🗣️ **Antwoord:** {antwoord}")
                
                # Audio afspelen
                spraak_tekst = repareer_uitspraak(antwoord, taal)
                mp3_fp = io.BytesIO()
                tts = gTTS(text=spraak_tekst, lang=taal)
                tts.write_to_fp(mp3_fp)
                st.audio(mp3_fp, format="audio/mpeg", autoplay=True)
                
                # Reset knop
                st.write("") 
                st.button("🔄 Stel een nieuwe vraag", on_click=reset_app)
                    
            except Exception as e:
                st.error(f"Technische foutmelding: {e}")
