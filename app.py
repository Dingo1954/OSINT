# app.py
import sqlite3
from pathlib import Path
from datetime import datetime
import bcrypt
import hashlib
import hmac
from typing import Optional, Tuple
import time
import webbrowser
import html
import pandas as pd
import streamlit as st
import urllib.parse
import requests

DB_PATH = Path(__file__).resolve().with_name("osint_tools.db")

# --- CSS / farveskema inspireret af Docker Desktop ---
DOCKER_PRIMARY = "#1b5a83"   # dyb blå
DOCKER_DARK = "#061b2b"      # mørk blå
DOCKER_ACCENT = "#0684ad"    # kølig cyan
CARD_BG = "#0a121d"          # mørk kort baggrund

st.set_page_config(page_title="OSINT-værktøjer", layout="wide")

st.markdown(
    f"""
    <style>
    :root {{
      --primary: {DOCKER_PRIMARY};
      --dark: {DOCKER_DARK};
      --accent: {DOCKER_ACCENT};
      --card-bg: {CARD_BG};
      --text: #e6eef6;
    }}
    .stApp {{
      background: #050a12;
      color: var(--text);
      font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial;
    }}
    body {{
      background: #050a12;
    }}
    .header {{
      padding: 1rem 1rem;
      border-radius: 8px;
      background: linear-gradient(90deg, var(--dark), var(--primary));
      color: white;
      margin-bottom: 1rem;
    }}
    .tool-card {{
      background: linear-gradient(135deg, rgba(10,27,42,0.95), rgba(5,16,28,0.92));
      border: 1px solid rgba(13,132,173,0.25);
      padding: 0.75rem;
      border-radius: 8px;
      margin-bottom: 0.5rem;
      overflow-wrap: anywhere;
    }}
    a.tool-link {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
      overflow-wrap: anywhere;
    }}
    .stTextInput>div>input,
    .stTextArea>div>textarea,
    .stSelectbox>div>div>select,
    .stForm {{
      background: rgba(5,20,35,0.92);
      color: var(--text);
    }}
    .stTextInput>div>input,
    .stTextArea>div>textarea,
    .stSelectbox>div>div>select {{
      border: 1px solid rgba(13,132,173,0.4);
    }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.85rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 999px;
    }}
    .status-pill span {{
      font-weight: 500;
      opacity: 0.8;
    }}
    .status-pill.status-online {{
      background: rgba(31,200,138,0.16);
      color: #49f5b9;
    }}
    .status-pill.status-issue {{
      background: rgba(217,119,6,0.16);
      color: #f1b565;
    }}
    .status-pill.status-offline {{
      background: rgba(239,68,68,0.18);
      color: #f38c8c;
    }}
    .stButton>button {{
      background: var(--primary);
      color: white;
      border: none;
    }}
    .small-muted {{
      color: #9fb6d6;
      font-size: 0.9rem;
      overflow-wrap: anywhere;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Database opsætning ---
def init_db(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT
        )
        """
    )
    conn.commit()
    return conn

def seed_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tools")
    existing = cur.fetchone()[0]
    if existing:
        return

    entries = [
        (
            "Bullsh*t Hunting",
            "https://bullshithunting.com",
          "MJ Banias forklarer, at dette er en hjemmeside, han skriver for sammen med sine kolleger. Den handler ikke nødvendigvis om OSINT-værktøjer, men om kunsten at indsamle efterretninger og efterforskning. Han anbefaler den til alle, der vil lære mere om open-source efterretningsindhentning, og nævner, at det meste af indholdet er gratis.",
        ),
        (
            "WhatsMyName.app",
            "https://whatsmyname.app",
          "Dette værktøj er skabt af OSINT Combine og er et søgeværktøj til brugernavne. MJ beskriver det som \"super cool\", fordi det gennemsøger alle de forskellige steder på internettet, hvor et brugernavn kan findes, og giver dig en liste. Han bruger det i næsten hver eneste efterforskning, fordi det fungerer så godt.",
        ),
        (
            "DorkGPT",
            "https://dorkgpt.com",
          "MJ forklarer, at Google Dorking er kunsten at manipulere Google-søgninger til at lede efter specifikke filtyper eller dokumenter. Dork GPT gør dette nemt ved, at du blot fortæller værktøjet, hvad du vil søge efter, og så genererer det den specifikke Google Dork for dig.",
        ),
        (
            "DorkSearch Pro",
            "https://dorksearch.pro",
          "Dette er en anden side til Google Dorking, som MJ har fundet for nylig. Han beskriver den som meget sjov med mange forskellige værktøjer. Man kan indtaste meget specifikke ting, man leder efter, såsom offentlige PDF'er eller Excel-data, og værktøjet gør arbejdet for dig. Han advarer dog om, at siden har mange reklamer.",
        ),
        (
            "ODCrawler",
            "https://odcrawler.xyz",
          "MJ beskriver dette værktøj (Open Directory Crawler) som noget, der gennemsøger åbne mapper. Det er filer, der er offentligt tilgængelige på internettet i åbne lagre. Det er et nyttigt værktøj, hvis man leder efter specifik dokumentation om et mål, som måske findes i et offentligt arkiv et eller andet sted.",
        ),
        (
            "Kagi Search",
            "https://kagi.com",
          "Dette er en betalt søgemaskine (ca. 5 dollars om måneden), som MJ beskriver som \"det Google var i 2004\". Han elsker det, fordi man ikke bliver bombarderet med reklamer eller AI-genereret indhold. Man kan også målrette sin søgning mod \"det lille web\" (små blogs og lokalaviser) eller søge direkte efter PDF'er og fora.",
        ),
        (
            "Vortimo (Ubicron)",
            "https://www.vortimo.com",
          "MJ giver en stor anbefaling til dette værktøj, som hjælper med at holde en efterforskning organiseret. Han fremhæver en widget til browseren, hvor man kan tage skærmbilleder, skrive noter og gemme hele websider som PDF'er. En særlig funktion er \"auto-scroll\", som automatisk ruller ned over en side (f.eks. et forum) og gemmer det hele.",
        ),
        (
            "Forensic OSINT",
            "https://www.forensicosint.com",
          "MJ nævner dette som et alternativ til Ubicron. Han forklarer, at de laver et lignende værktøj, der gør et godt stykke arbejde, især når det kommer til at udtrække data fra YouTube-videoer.",
        ),
        (
            "Newspapers.com",
            "https://www.newspapers.com",
          "MJ kalder dette sit yndlingssted. Det er et arkiv over gamle aviser, hvor man kan finde fødselsannoncer og information om gamle bekendtskaber. Han påpeger, at aviser aldrig glemmer, og at man ofte kan finde information her, som ikke dukker op i en almindelig Google-søgning.",
        ),
        (
            "Judy Records",
            "https://www.judyrecords.com",
          "Dette er et gratis værktøj til at søge i over 760 millioner retsjournaler i USA. MJ forklarer, at man kan finde utrolig meget efterretningsmateriale i retssager, hvilket kan hjælpe med at tegne et billede af en person eller en virksomhed.",
        ),
        (
            "CanLII",
            "https://www.canlii.org",
          "MJ nævner dette som den canadiske kilde til at søge i offentlige retsjournaler og dokumenter fra retssager.",
        ),
        (
            "OSINT Industries",
            "https://www.osint.industries",
          "Dette er et værktøj, som MJ bruger hele tiden. Man indtaster en e-mail, et brugernavn eller et telefonnummer, og så gennemsøger det internettet for information om målet. Det kan vise en tidslinje for, hvornår konti blev oprettet, og finde billeder eller profiler på tværs af mange platforme.",
        ),
        (
            "Epieos (epio.me)",
            "https://epieos.com",
          "MJ nævner kort dette værktøj (som han kalder Epio) som værende i samme kategori som OSINT Industries til at finde information baseret på digitale spor.",
        ),
        (
            "Maltego",
            "https://www.maltego.com",
          "MJ beskriver dette som et professionelt værktøj, der nu er gået sammen med Hunchly. Det bruges til at visualisere data i grafer og er fantastisk til større efterforskninger, hvor man har brug for at forbinde mange forskellige informationer og bygge et samlet billede af sagen.",
        ),
        (
            "Darkside.tools",
            "https://darkside.tools",
          "Dette er en søgemaskine til lækkede data (breach data) baseret i USA. MJ forklarer, at man kan søge på IP-adresser, adgangskoder og e-mails for at forbinde prikkerne i en efterforskning. Han advarer dog kraftigt om, at man altid skal rådføre sig med juridiske eksperter, da brugen af lækkede data kan være problematisk i en retssag.",
        ),
        (
            "Hunchly",
            "https://www.hunch.ly",
            "Automatisk indsamling og dokumentation af websider under online efterforskninger.",
        ),
    ]

    for name, url, description in entries:
        cur.execute(
            "SELECT id FROM tools WHERE lower(name) = ? OR lower(url) = ?",
            (name.lower(), url.lower()),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE tools SET name = ?, url = ?, description = ? WHERE id = ?",
                (name, url, description, row[0]),
            )
        else:
            cur.execute(
                "INSERT INTO tools (name, url, description) VALUES (?, ?, ?)",
                (name, url, description),
            )

    conn.commit()

conn = init_db(DB_PATH)
seed_db(conn)

# --- Helper functions ---
def get_tools_df(conn, q=None):
    sql = "SELECT id, name, url, description FROM tools"
    params = ()
    if q:
        sql += " WHERE name LIKE ? OR url LIKE ? OR description LIKE ?"
        like = f"%{q}%"
        params = (like, like, like)
    df = pd.read_sql_query(sql, conn, params=params)
    return df

def add_tool(conn, name, url, description):
    cur = conn.cursor()
    cur.execute("INSERT INTO tools (name, url, description) VALUES (?, ?, ?)", (name, url, description))
    conn.commit()

def update_tool_url(conn, tool_id, url):
    cur = conn.cursor()
    cur.execute("UPDATE tools SET url = ? WHERE id = ?", (url, tool_id))
    conn.commit()

@st.cache_data(show_spinner=False, ttl=300)
def get_url_status(url: str):
  """Check whether a URL responds within a short timeout."""
  url = normalize_url(url)
  if not url:
    return "offline", "Ingen URL"
  if not is_valid_http_url(url):
    return "issue", "Ugyldig URL"

  def _interpret_response(response):
    if 200 <= response.status_code < 400:
      return "online", f"HTTP {response.status_code}"
    return "issue", f"HTTP {response.status_code}"

  headers = {"User-Agent": "Mozilla/5.0 (compatible; OSINT-Tool-Checker/1.0)"}
  try:
    response = requests.head(url, timeout=4, allow_redirects=True, headers=headers)
    # Nogle servere tillader ikke HEAD eller blokerer uden browser-lignende klient.
    if response.status_code in {403, 405}:
      response = requests.get(url, timeout=6, allow_redirects=True, headers=headers)
    return _interpret_response(response)
  except requests.RequestException:
    try:
      response = requests.get(url, timeout=6, allow_redirects=True, headers=headers)
      return _interpret_response(response)
    except requests.RequestException:
      return "offline", "Ingen forbindelse"

def delete_tool(conn, tool_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM tools WHERE id = ?", (tool_id,))
    conn.commit()

def get_user_by_username(conn, username: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE lower(username) = ?", (username.strip().lower(),))
    row = cur.fetchone()
    return dict(row) if row else None

def hash_password(password: str, salt: bytes) -> str:
    # Bcrypt inkluderer salt og work factor i resultatstrengen.
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(password: str, hashed: str, salt: Optional[str] = None) -> Tuple[bool, bool]:
    try:
        if hashed.startswith("$2"):
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")), False
    except ValueError:
        return False, False

    if salt:
        legacy_hash = hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_hash, hashed), True

    return False, False

def create_user(conn, username: str, password: str):
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("Brugernavn må ikke være tomt.")
    if len(password) < 6:
        raise ValueError("Adgangskode skal mindst indeholde 6 tegn.")

    if get_user_by_username(conn, normalized_username):
        raise ValueError("Brugernavnet er allerede registreret.")

    salt = bcrypt.gensalt()
    password_hash = hash_password(password, salt)
    salt_str = salt.decode("utf-8")
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (username, password_hash, salt, created_at, last_login)
        VALUES (?, ?, ?, ?, ?)
        """,
        (normalized_username, password_hash, salt_str, now, now),
    )
    conn.commit()
    return dict(get_user_by_username(conn, normalized_username))

def record_user_login(conn, user_id: int):
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (timestamp, user_id),
    )
    conn.commit()
    return timestamp

def authenticate_user(conn, username: str, password: str):
    user_row = get_user_by_username(conn, username)
    if not user_row:
        return None, "Brugernavn ikke fundet."

    is_valid, used_legacy = verify_password(password, user_row["password_hash"], user_row.get("salt"))
    if not is_valid:
        return None, "Forkert adgangskode."

    if used_legacy:
        salt = bcrypt.gensalt()
        new_hash = hash_password(password, salt)
        salt_str = salt.decode("utf-8")
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (new_hash, salt_str, user_row["id"]),
        )
        conn.commit()
        user_row["password_hash"] = new_hash
        user_row["salt"] = salt_str

    last_login = record_user_login(conn, user_row["id"])
    user_data = dict(user_row)
    user_data["last_login"] = last_login
    return user_data, None

def ensure_authenticated(conn):
    if st.session_state.get("user_id"):
        return

    st.markdown(
        """
        <div class="header"><h2 style="margin:0">OSINT værktøjer</h2></div>
        <p>Log ind for at få adgang til værktøjerne.</p>
        """,
        unsafe_allow_html=True,
    )

    login_tab, register_tab = st.tabs(["Log ind", "Registrer"])

    with login_tab:
        with st.form("login_form"):
            login_username = st.text_input("Brugernavn", key="login_username")
            login_password = st.text_input("Adgangskode", type="password", key="login_password")
            login_submit = st.form_submit_button("Log ind")
            if login_submit:
                user, error = authenticate_user(conn, login_username, login_password)
                if error:
                    st.error(error)
                else:
                    st.session_state["user_id"] = user["id"]
                    st.session_state["username"] = user["username"]
                    st.session_state["last_login"] = user.get("last_login")
                    st.success("Login lykkedes.")
                    st.rerun()

    with register_tab:
        with st.form("register_form"):
            register_username = st.text_input("Brugernavn", key="register_username")
            register_password = st.text_input("Adgangskode", type="password", key="register_password")
            register_password_repeat = st.text_input("Gentag adgangskode", type="password", key="register_password_repeat")
            register_submit = st.form_submit_button("Opret bruger")
            if register_submit:
                if register_password != register_password_repeat:
                    st.error("Adgangskoderne er ikke ens.")
                else:
                    try:
                        user = create_user(conn, register_username, register_password)
                    except ValueError as exc:
                        st.error(str(exc))
                    except sqlite3.IntegrityError:
                        st.error("Kunne ikke oprette bruger. Prøv et andet brugernavn.")
                    else:
                        st.session_state["user_id"] = user["id"]
                        st.session_state["username"] = user["username"]
                        st.session_state["last_login"] = user.get("last_login")
                        st.success("Bruger oprettet og logget ind.")
                        st.rerun()

    st.stop()


def normalize_url(url: str) -> str:
    return (url or "").strip()


def is_valid_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def escape_html_text(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)

# --- Kræv login før indhold ---
ensure_authenticated(conn)

user_display_name = escape_html_text(st.session_state.get("username", ""))
last_login_raw = st.session_state.get("last_login")
last_login_display = ""
if last_login_raw:
    try:
        last_login_dt = datetime.fromisoformat(last_login_raw)
        last_login_display = last_login_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        last_login_display = last_login_raw

last_login_text = escape_html_text(last_login_display) if last_login_display else ""
subtitle_text = f"Logget ind som {user_display_name}" if user_display_name else "Logget ind"
if last_login_text:
    subtitle_text += f" · Sidst aktiv: {last_login_text}"

st.markdown(
    f'<div class="header"><h2 style="margin:0">OSINT værktøjer</h2><p class="small-muted" style="margin:0">{subtitle_text}</p></div>',
    unsafe_allow_html=True,
)

# --- Sidebar: søg og tilføj ---
with st.sidebar:
    if user_display_name:
        st.markdown(f"**Logget ind som:** {user_display_name}")
    if st.button("Log ud"):
        for key in ("user_id", "username", "last_login"):
            st.session_state.pop(key, None)
        st.rerun()

    st.markdown("### Søg i værktøjer")
    q = st.text_input("Søg (navn, url, beskrivelse)", value="")
    st.markdown("---")
    st.markdown("### Tilføj nyt værktøj")
    with st.form("add_form"):
        name = st.text_input("Navn")
        url = st.text_input("URL (inkl. https://)")
        desc = st.text_area("Kort beskrivelse", height=80)
        submitted = st.form_submit_button("Tilføj")
        if submitted:
            trimmed_name = name.strip()
            trimmed_url = normalize_url(url)
            trimmed_desc = desc.strip()
            if not trimmed_name or not trimmed_url:
                st.error("Navn og URL er påkrævet.")
            elif not is_valid_http_url(trimmed_url):
                st.error("URL skal starte med http:// eller https:// og indeholde et domæne.")
            else:
                add_tool(conn, trimmed_name, trimmed_url, trimmed_desc)
                st.success(f"Tilføjet: {trimmed_name}")
                # refresh by rerunning
                st.rerun()

# --- Hovedindhold: visning og handlinger ---
st.markdown("#### Værktøjer")
df = get_tools_df(conn, q if q else None)

if df.empty:
    st.info("Ingen værktøjer fundet. Prøv at fjerne søgefilteret eller tilføj et nyt værktøj.")
else:
    open_all_clicked = st.button("Åbn alle links i faner")
    if open_all_clicked:
        urls_to_open = [
            normalize_url(url)
            for url in df["url"].dropna().unique()
            if is_valid_http_url(normalize_url(url))
        ]
        if urls_to_open:
        # Åbn links direkte fra serveren, fungerer kun hvis app og browser kører på samme maskine.
            for index, url in enumerate(urls_to_open):
              webbrowser.open_new_tab(url)
              time.sleep(0.15)  # kort pause for at undgå at browseren blokerer
            st.success("Åbnede alle links i nye faner.")
        else:
            st.warning("Ingen gyldige http(s)-links at åbne.")

    for _, row in df.iterrows():
        raw_name = row["name"] if pd.notna(row["name"]) else ""
        raw_url = normalize_url(row["url"] if pd.notna(row["url"]) else "")
        description_text = row["description"] if pd.notna(row["description"]) else ""
        escaped_name = escape_html_text(raw_name)
        escaped_url = escape_html_text(raw_url)
        escaped_description = escape_html_text(description_text)
        safe_href = escaped_url if is_valid_http_url(raw_url) else "#"
        status_state, status_detail = get_url_status(raw_url)
        status_state = status_state or "offline"
        status_labels = {"online": "Online", "issue": "Svar men problem", "offline": "Offline"}
        status_label = status_labels.get(status_state, "Ukendt")
        status_extra = status_detail or "Ingen data"
        with st.form(f"tool_form_{row['id']}"):
            widget_key = f"url_input_{row['id']}"
            current_db_url = raw_url
            stored_url = st.session_state.get(widget_key)
            if stored_url is None or stored_url != current_db_url:
                st.session_state[widget_key] = current_db_url

            st.markdown(
                f"""
                <div class="tool-card" style="padding:0; border:none;">
                  <div style="display:flex; align-items:flex-start; gap:1rem; padding:0.5rem 0;">
                    <div>
                      <div style="font-size:1.05rem; font-weight:700; color:var(--text)">{escaped_name}</div>
                      <div class="small-muted"><span style="color:#d6e6ff; font-weight:600;">Beskrivelse:</span> {escaped_description}</div>
                      <div style="margin-top:6px;">
                        <a class="tool-link" href="{safe_href}" target="_blank" rel="noopener noreferrer">{escaped_url}</a>
                      </div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            new_url = st.text_input("Opdater URL", value=st.session_state[widget_key], key=widget_key)
            action_cols = st.columns([1, 1, 2])
            save_clicked = action_cols[0].form_submit_button("Gem URL")
            delete_clicked = action_cols[1].form_submit_button("Slet")
            share_link = urllib.parse.quote(raw_url)
            share_subject = urllib.parse.quote(f"Del: {raw_name}")
            action_cols[2].markdown(
                f"""
                <div style=\"display:flex; align-items:center; justify-content:flex-end; gap:8px;\">
                  <span class=\"status-pill status-{status_state}\">{status_label}<span>{status_extra}</span></span>
                  <a href=\"mailto:?subject={share_subject}&body={share_link}\" style=\"color:#cfeeff; text-decoration:none;\">Del via e-mail</a>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if save_clicked:
                trimmed = normalize_url(new_url)
                if not trimmed:
                    st.error("URL kan ikke være tom.")
                elif not is_valid_http_url(trimmed):
                    st.error("Ugyldig URL. Brug http:// eller https://.")
                else:
                    update_tool_url(conn, row["id"], trimmed)
                    st.success("URL opdateret.")
                    get_url_status.clear()
                    st.rerun()

            if delete_clicked:
                delete_tool(conn, row["id"])
                get_url_status.clear()
                st.rerun()

st.markdown("---")
st.markdown("**Bemærk:** Jeg har indsat de mest sandsynlige officielle webadresser som startpunkt. Ret eller opdater dem efter behov via formularen i sidebaren.")
