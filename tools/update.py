#!/usr/bin/env python3
"""Mise à jour de la base sabre FFE (M9 à Senior).
Usage: python3 update.py PREV_HTML OUT_HTML WORKDIR
 - PREV_HTML : page publiée (contient `const D={...};` suivi de `const CATS=`)
 - OUT_HTML  : même page avec les données mises à jour et la liste des changements
 - WORKDIR   : dossier de cache (pages FFE, notes PDF)
Besoin: curl, pdftotext (poppler). tesseract facultatif (notes scannées)."""
import base64, collections, hashlib, html, json, os, re, subprocess, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date

BASE = "https://www.ffescrime.fr"
CATS = ["M9", "M11", "M13", "M15", "M17", "M20", "SENIOR"]
VETC = ["V1", "V2", "V3", "V4"]  # fusionnés en une seule catégorie « VET » (Vétérans)
RANK = {c: i for i, c in enumerate(CATS + ["VET"])}
CATRX = {"M9": r"M\s?9", "M11": r"M\s?11", "M13": r"M\s?13", "M15": r"M\s?15", "M17": r"M\s?17", "M20": r"M\s?20", "SENIOR": r"S[ée]nior?s?", "VET": r"(?:V[ée]t[ée]rans?|V\s?[1-4])"}
MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}
PREV, OUT, WORK = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(WORK + "/pages", exist_ok=True)
os.makedirs(WORK + "/notes", exist_ok=True)
TODAY = date.today().isoformat()


def fetch(url, path, retries=3, binary=False):
    if os.path.exists(path) and os.path.getsize(path) > 500:
        return open(path, "rb").read() if binary else open(path, encoding="utf-8", errors="replace").read()
    for i in range(retries):
        r = subprocess.run(["curl", "-sSL", "-m", "40", "-o", path, "-w", "%{http_code}", url], capture_output=True, text=True)
        if r.stdout.strip() == "200" and os.path.exists(path) and os.path.getsize(path) > 500:
            return open(path, "rb").read() if binary else open(path, encoding="utf-8", errors="replace").read()
        time.sleep(1.5 * (i + 1))
    return None


def md5(s): return hashlib.md5(s.encode()).hexdigest()[:10]
def clean(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


# ---------- FFE : calendrier, fiches, engagés ----------
def page(url, name):
    return fetch(url, f"{WORK}/pages/{name}.html") or ""


def fiche_links(p):
    return sorted(set(re.findall(r'href="(?:https://www\.ffescrime\.fr)?(/competition/[A-Za-z0-9=_%-]+/?)"', p)))


def parse_fiche(path):
    key = path.strip("/").split("/")[-1]
    p = page(BASE + path, "fiche_" + md5(key))
    if not p:
        return None
    body = p.split("Partagez cet")[0]
    h2 = re.search(r"<h2[^>]*>(.*?)</h2>", body[body.find("Retour"):], re.S)
    m = re.search(r"Du (\d{1,2}) au (\d{1,2}) ([a-zéû]+) (\d{4})", body)
    if not m:
        return None
    mo = MOIS[m.group(3)]
    d1 = date(int(m.group(4)), mo, int(m.group(1))).isoformat()
    d2 = date(int(m.group(4)), mo, int(m.group(2))).isoformat()
    ville = ""
    pin = re.search(r"icon-pin-dark\.png[^>]*>\s*([^<\s][^<]*)", body)
    if pin:
        ville = clean(pin.group(1))
    if not ville:
        try:
            ville = base64.b64decode(key + "=" * (-len(key) % 4)).decode().split("-separator-")[-1]
        except Exception:
            pass
    note = re.search(r'href="(https://dirigeant[^"]+)"[^>]*>\s*Note d(?:&#039;|\')organisation', p)
    eps, seen = [], set()
    for mm in re.finditer(r'href="(/engages/[^"]+)"', p):
        href = mm.group(1)
        if href in seen:
            continue
        seen.add(href)
        win = p[max(0, mm.start() - 2500):mm.start()]
        ds = re.findall(r"tile__discipline-description[^>]*>\s*<p>\s*([^<]+?)\s*</p>", win, re.S)
        cs = re.findall(r"tile__discipline-rank[^>]*>\s*<p>\s*([^<]+?)\s*</p>", win, re.S)
        eps.append({"epreuve": clean(ds[-1]) if ds else "", "cat": clean(cs[-1]) if cs else "", "href": href})
    return {"k": key, "nom": clean(h2.group(1)) if h2 else "", "d": d1, "f": d2, "v": ville.title() if ville.isupper() else ville,
            "nt": note.group(1) if note else "", "eps": eps}


def tireurs(href):
    key = href.strip("/").split("/")[-1]
    p = page(BASE + href, "eng_" + md5(key))
    if not p:
        return None
    h = re.search(r"<h2>\s*(\d+) tireurs? engagés?", p)
    if not h:
        return []
    out = []
    for row in re.findall(r'section__table-row">(.*?)</ul>', p[h.end():], re.S):
        li = [clean(x) for x in re.findall(r"<li>(.*?)</li>", row, re.S)]
        if len(li) >= 4:
            out.append((li[0], li[1], li[3]))
    return out


def split_name(n):
    t = n.split()
    i = 0
    while i < len(t) - 1 and (t[i].isupper() or t[i] in ("DE", "DU", "LE", "LA", "DES", "DI", "VAN", "VON", "D'", "DA")):
        i += 1
    i = i or 1
    return " ".join(t[:i]), " ".join(t[i:])


# ---------- Notes d'organisation (extraction automatique) ----------
def note_text(url):
    h = md5(url)
    p = f"{WORK}/notes/{h}.pdf"
    if not fetch(url, p, binary=True) or open(p, "rb").read(4) != b"%PDF":
        return ""
    t = subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, text=True).stdout
    if len(re.sub(r"\s", "", t)) < 80 and subprocess.run(["which", "tesseract"], capture_output=True).returncode == 0:
        subprocess.run(["pdftoppm", "-r", "150", "-png", p, f"{WORK}/notes/{h}"])
        t = ""
        for f in sorted(os.listdir(WORK + "/notes")):
            if f.startswith(h) and f.endswith(".png"):
                t += subprocess.run(["tesseract", f"{WORK}/notes/{f}", "-", "-l", "fra"], capture_output=True, text=True).stdout
    return re.sub(r"\s+", " ", t)


TM = r"(\d{1,2}\s?[hH:]\s?\d{0,2})"


def nt(x):
    x = re.sub(r"\s", "", x).lower().replace(":", "h")
    m = re.match(r"(\d+)h(\d*)", x)
    return f"{int(m.group(1))}h{(m.group(2) or '00').zfill(2)}" if m else x


def hours(t, cat):
    res = []
    rx = (r"(?<![A-Za-z0-9])" + CATRX[cat] + r"(?![0-9])((?:\s*(?:&|et|,|-|–|/|à)\s*(?:M\s?\d+|S[ée]niors?|V[ée]t[ée]rans?|M20)|[^0-9]){0,60}?)"
          + TM + r"\s+" + TM + r"\s+" + TM)
    for m in re.finditer(rx, t):
        w = t[max(0, m.start() - 350):m.start()].lower()
        gap = m.group(1).lower()
        idx = {k: w.rfind(k) for k in ("sabre", "épée", "epee", "fleuret")}
        loc = [k for k in idx if k in gap]
        if loc:
            arm = loc[0]
        else:
            best = max(idx, key=lambda k: idx[k])
            arm = best if idx[best] >= 0 else None
        res.append((arm, tuple(nt(m.group(i)) for i in (2, 3, 4))))
    sab = [r for r in res if r[0] == "sabre"]
    if sab:
        return sab[0][1]
    none = [r for r in res if r[0] is None]
    if none and not any(r[0] for r in res):
        return none[0][1]
    return None


def price(t, cat):
    ps = [m.group(1).replace(".", ",") + " € (auto)" for m in re.finditer(CATRX[cat] + r"(?![0-9])[^€0-9]{0,40}?(\d{1,3}(?:[.,]\d{1,2})?)\s?(?:€|euros?|Euros?)", t)]
    if ps:
        return ps[0]
    al = {m.group(1).replace(".", ",") for m in re.finditer(r"(\d{1,3}(?:[.,]\d{1,2})?)\s?(?:€|euros?)", t)}
    return (al.pop() + " € (auto)") if len(al) == 1 else ""


def deadline(t, comp):
    y0, m0 = int(comp[:4]), int(comp[5:7])
    for m in re.finditer(r"(?i)(?:jusqu.{0,3}au|avant le|avant|au plus tard le|date limite[^0-9]{0,40}|clôture[^0-9]{0,40}|le)\s*(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\s*(\d{1,2}|1er)\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)(?:\s+(20\d\d))?", t):
        ctx = t[max(0, m.start() - 120):m.end() + 40].lower()
        if not re.search(r"inscri|engag|extranet|ffe|clôture|date limite", ctx):
            continue
        d = int(m.group(1).replace("er", ""))
        mo = MOIS[m.group(2).lower()]
        y = int(m.group(3)) if m.group(3) else (y0 if mo <= m0 else y0 - 1)
        return f"{y}-{mo:02d}-{d:02d}"
    return ""


def address(t):
    for m in re.finditer(r"([^.;:|•]{8,110}?\b\d{5}\s+[A-ZÉÈ][A-Za-zÀ-ÿ'’ -]{2,30})", t):
        s = m.group(1).strip()
        if re.search(r"(?i)@|tél|tel\.|siret|BP \d|cedex", s):
            continue
        k = re.search(r"(?i)(salle|gymnase|complexe|halle|palais|centre|espace|cosec|dojo|maison|pôle|stade|\d+\s*,?\s*(?:rue|avenue|av|bd|boulevard|chemin|route|place|allée|impasse))", s)
        return s[k.start():] if k else s
    return ""


def maps(addr):
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(addr) if addr else ""


# ---------- Géographie (grande région / région / département) et type de compétition ----------
import unicodedata
_GEO = {}


def gnorm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\bsaint(e?)\b", lambda m: "st" + m.group(1), s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def geo_load():
    """Découpage administratif (npm @etalab/decoupage-administratif), installé dans WORK au besoin."""
    if _GEO:
        return
    p = f"{WORK}/geo/node_modules/@etalab/decoupage-administratif/data/"
    if not os.path.exists(p + "communes.json"):
        os.makedirs(WORK + "/geo", exist_ok=True)
        subprocess.run(["npm", "i", "@etalab/decoupage-administratif"], cwd=WORK + "/geo", capture_output=True)
    com = json.load(open(p + "communes.json"))
    _GEO["dep"] = {x["code"]: x["nom"] for x in json.load(open(p + "departements.json"))}
    _GEO["reg"] = {}
    _GEO["idx"] = {}
    _GEO["depreg"] = {}
    for c in com:
        if c.get("type") != "commune-actuelle":
            continue
        _GEO["idx"].setdefault(gnorm(c["nom"]), []).append(c)
        _GEO["depreg"][c["departement"]] = c["region"]


GRAND = {"11": "Île-de-France", "24": "Centre-Val de Loire", "27": "Bourgogne-Franche-Comté", "28": "Normandie", "32": "Hauts-de-France",
         "44": "Grand Est", "52": "Pays de la Loire", "53": "Bretagne", "75": "Nouvelle-Aquitaine", "76": "Occitanie",
         "84": "Auvergne-Rhône-Alpes", "93": "Provence-Alpes-Côte d'Azur", "94": "Corse", "01": "Guadeloupe", "02": "Martinique",
         "03": "Guyane", "04": "La Réunion", "06": "Mayotte"}
ANC = {}
for _r, _l in {"Alsace": "67 68", "Lorraine": "54 55 57 88", "Champagne-Ardenne": "08 10 51 52", "Aquitaine": "24 33 40 47 64",
               "Limousin": "19 23 87", "Poitou-Charentes": "16 17 79 86", "Languedoc-Roussillon": "11 30 34 48 66",
               "Midi-Pyrénées": "09 12 31 32 46 65 81 82", "Auvergne": "03 15 43 63", "Rhône-Alpes": "01 07 26 38 42 69 73 74",
               "Bourgogne": "21 58 71 89", "Franche-Comté": "25 39 70 90", "Nord-Pas-de-Calais": "59 62", "Picardie": "02 60 80",
               "Basse-Normandie": "14 50 61", "Haute-Normandie": "27 76"}.items():
    for _d in _l.split():
        ANC[_d] = _r


def geo_of(ville, addr):
    """-> (grande région, région, département) ; chaînes vides si introuvable (ex. étranger)."""
    geo_load()
    n = gnorm(ville)
    cands = list(_GEO["idx"].get(n, []))
    if not cands and len(n) >= 8:
        cands = [c for k, v in _GEO["idx"].items() if k.startswith(n) for c in v]
    cp = re.findall(r"\b(\d{5})\b", addr or "")
    if len(cands) > 1:
        m_ = [c for c in cands if any(p_ in c.get("codesPostaux", []) for p_ in cp)]
        cands = m_ or cands
    if cands:
        dep = sorted(cands, key=lambda c: -c.get("population", 0))[0]["departement"]
    elif cp:
        dep = cp[0][:3] if cp[0][:2] in ("97", "98") else cp[0][:2]
        if dep not in _GEO["dep"]:
            return "", "", ""
    else:
        return "", "", ""
    g = GRAND.get(_GEO["depreg"].get(dep, ""), "")
    return g, ANC.get(dep) or g, _GEO["dep"].get(dep, "")


NIVEAUX = {}


def niveaux_load():
    """Niveau FFE (filtre « niveaux » du calendrier) -> {clé fiche: [ids]}."""
    if NIVEAUX:
        return
    jobs = [(n_, c_, b_) for n_ in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20, 30) for c_ in CATS + ["V1"] for b_ in ("calendrier", "calendrier-sportif")]

    def one(a):
        n_, c_, b_ = a
        h = page(f"{BASE}/{b_}/?arme%5BSAB%5D=on&categories={c_}&niveaux={n_}", f"niv_{b_}_{c_}_{n_}")
        return n_, set(re.findall(r"/competition/([A-Za-z0-9=_%-]+)", h))
    with ThreadPoolExecutor(8) as ex:
        for n_, s_ in ex.map(one, jobs):
            for k_ in s_:
                NIVEAUX.setdefault(k_, set()).add(n_)


def type_of(c, txt):
    """-> (type, raison). La note d'organisation (titre) prime sur le nom de la fiche."""
    geo_load()
    niveaux_load()
    depn = _GEO.setdefault("depn", sorted({gnorm(v) for v in _GEO["dep"].values() if len(v) > 3}, key=len, reverse=True))
    oldn = ["lorraine", "alsace", "champagne", "picardie", "aquitaine", "limousin", "poitou", "midi pyrenees", "languedoc", "auvergne",
            "rhone alpes", "bourgogne", "franche comte", "nord pas de calais", "haute normandie", "basse normandie"]
    n = gnorm(c["n"])
    head = gnorm((txt or "")[:300])
    nn = gnorm(c.get("nn") or "")
    t = n + " | " + head + " | " + nn
    niv = NIVEAUX.get(c["k"], set())
    pre = r"(coupe|championnats?|critere?ium|trophee|challenge|circuit|tournoi|open|rencontre|animation)s?\s+(de |d |du |des )?(la |l )?"
    if re.search(r"\bmaster\b", n + " " + nn): return "grande régional", "master = niveau grande région"
    if re.search(r"arbitrage|formation|qcm|\bjna\b", t): return "formation", "arbitrage / formation"
    if re.search(r"\bstage\b", n + " " + head[:120]): return "stage", "stage"
    if 10 in niv or "international" in n: return "international", "niveau FFE international"
    if re.search(r"\bnational\b|championnats? de france", n) or niv & {8, 9}: return "national", "niveau FFE national"
    if re.search(r"circuit regional|epreuve regionale|circuit (nouvelle aquitaine|grand est|hdf)", head + " " + nn): return "grande régional", "circuit régional (note)"
    if re.search(pre + "(" + "|".join(oldn) + ")", t): return "régional", "ancienne région dans le nom"
    if re.search(pre + "(" + "|".join(depn) + r")\b", t) or re.search(r"depart|inter ?depart|\bcd ?\d\d|\bcde ?\d\d", t): return "départemental", "département dans le nom"
    if re.search(r"circuit regional|regional|\bidf\b|ligue|h2036|horizon|nouvelle aquitaine|grand est|\bhdf\b|aura|circuit .*sud ouest|\bzone\b|interzone|coupe du futur", t) or niv & {6, 7, 11, 12}:
        return "grande régional", "circuit / ligue / régional"
    if niv & {2, 3, 4, 5}: return "départemental", "niveau FFE départemental"
    if "departemental" in n: return "départemental", "nom fiche départemental (à vérifier)"
    return "grande régional", "par défaut (à vérifier)"


def enrich(c, txt, old=None):
    """Ajoute gr / rg / dt (géographie) et ty / tw (type) ; réutilise l'ancien si la note est inchangée."""
    if old and old.get("ty") and not old.get("_redo"):
        for a in ("gr", "rg", "dt", "ty", "tw"):
            c[a] = old.get(a, "")
        return
    c["gr"], c["rg"], c["dt"] = geo_of(c["v"], c.get("ad"))
    c["ty"], c["tw"] = type_of(c, txt)
    if not c["gr"]:
        sp = {"monaco": "Monaco", "en distanciel": "En ligne"}.get(gnorm(c["v"]))
        if sp or c["ty"] == "international":
            c["gr"] = c["rg"] = sp or "Étranger"


def inherit_types(comps):
    for c in comps:
        if not c.get("go") and re.search(r"\bmaster\b", gnorm(c["n"] + " " + (c.get("nn") or ""))):
            c["ty"], c["tw"] = "grande régional", "master = niveau grande région"
    """Une valeur « par défaut » reprend le type d'une autre compétition qui partage la même note."""
    byn = {}
    for c in comps:
        if c.get("nt") and "défaut" not in c.get("tw", "défaut"):
            byn.setdefault(c["nt"], c)
    for c in comps:
        if "défaut" in c.get("tw", "") and c.get("nt") in byn:
            s_ = byn[c["nt"]]
            c["ty"], c["tw"] = s_["ty"], "même note que " + s_["n"][:30]


# ---------- Chargement de la base précédente ----------
# ---------- Croisement avec le calendrier du comité Grand Est ----------
import difflib

GE_URL = "https://escrime-grandest.fr/calendrier/"
_MOIS = {"janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "août": 8, "aout": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12}
_STOP = {"sur", "aux", "des", "les", "lacs", "set", "pour", "epreuve", "sabre", "definir", "attente", "reponse", "mairie"}


def ge_rows():
    """Lignes de sabre (hors sabre laser, stages et formations) du calendrier Grand Est."""
    h = page(GE_URL, "ge_calendrier")
    out = []
    for m in re.finditer(r'<tr class="lrg-row"(.*?)</tr>', h, re.S):
        r = m.group(0)
        a = dict(re.findall(r'data-(\w+)="([^"]*)"', r.split(">")[0]))
        cells = {k: clean(v) for k, v in re.findall(r'<td[^>]*data-l="([^"]*)"[^>]*>(.*?)</td>', r, re.S)}
        arme, sup = a.get("f", ""), a.get("s", "")
        if "laser" in arme.lower() or "Stages" in arme:
            continue
        if not ("sabre" in arme.lower() or "|Sabre|" in sup):
            continue
        dm = re.search(r'lrg-d">(.*?)</span>', r)
        mm = re.match(r"(\d+)(?:er)?\s*(?:-\s*(\d+))?\s*(\w+)\.?\s*(\d{4})", clean(dm.group(1))) if dm else None
        if not mm:
            continue
        mo = next((v for k, v in _MOIS.items() if mm.group(3).lower().startswith(k[:3])), 0)
        d1 = f"{mm.group(4)}-{mo:02d}-{int(mm.group(1)):02d}"
        d2 = f"{mm.group(4)}-{mo:02d}-{int(mm.group(2) or mm.group(1)):02d}"
        out.append({"d": d1, "f": d2, "lieu": cells.get("Lieu", ""), "type": cells.get("Type", ""), "cats": cells.get("Catégories / Épreuves", ""),
                    "arme": arme, "sup": sup, "txt": a.get("txt", "")})
    return out


def _mots(s):
    return [w for w in gnorm(s).split() if len(w) >= 3 and w not in _STOP]


def ge_match(row, c):
    if not (row["d"] <= (c["f"] or c["d"]) and c["d"] <= row["f"]):
        return False
    return any(difflib.SequenceMatcher(None, a, b).ratio() >= 0.85 for a in _mots(row["lieu"]) for b in _mots(c["v"]))


def ge_type(row):
    t = gnorm(row["type"] + " " + row["arme"] + " " + row["sup"])
    if re.search(r"\bcdl\b|\bchdl\b|coupe de lorraine|championnats? d alsace|championnats? de lorraine", t): return "régional"
    if re.search(r"coupe de (moselle|meurthe|meuse|vosges|marne|aube|ardennes|haut rhin|bas rhin)|championnat (54|55|57|88|08|10|51|52|67|68)\b", t): return "départemental"
    if re.search(r"\ber ?\d\b|epreuve regionale|\bcr ?\d?\b|championnat regional|circuit regional", t): return "grande régional"
    return None


def ge_sync(comps):
    """Ajoute gc (catégories du comité), corrige le type, et crée les compétitions absentes du calendrier FFE (go=1)."""
    try:
        rows = ge_rows()
    except Exception as ex:
        print("calendrier Grand Est indisponible :", ex, file=sys.stderr)
        return [], False
    if not rows:
        return [], False
    new = []
    for row in rows:
        ms = [c for c in comps if ge_match(row, c)]
        ty = ge_type(row)
        for c in ms:
            c["gc"] = row["cats"]
            if ty and c["ty"] != ty and not c.get("go"):
                c["ty"], c["tw"] = ty, "comité Grand Est : " + row["type"]
        if ms or "Stages" in row["arme"] or re.search(r"formation|stage", row["txt"]):
            continue
        cats = [x for x in ["M9", "M11", "M13", "M15", "M17", "M20"] if re.search(r"\b" + x + r"\b", row["cats"])]
        if re.search(r"senior", row["cats"], re.I):
            cats.append("SENIOR")
        if re.search(r"v[ée]t[ée]ran|\bV[1-4]\b", row["cats"], re.I):
            cats.append("VET")
        # tournoi de club : « Sabre M9, M11 … » -> seule la partie sabre compte
        sm = re.search(r"Sabre\s+((?:M\d+|Seniors|Vétérans|,|-|\s)+)", row["cats"])
        if sm:
            seg = sm.group(1)
            cats = [x for x in ["M9", "M11", "M13", "M15", "M17", "M20"] if re.search(r"\b" + x + r"\b", seg)] + (["SENIOR"] if re.search("Seniors", seg) else []) + (["VET"] if re.search("V[ée]t[ée]rans", seg) else [])
        if not cats:
            continue
        lieu = re.split(r" pour | - |\d{5}", row["lieu"])[0].strip().title()
        if "finir" in lieu.lower():
            lieu = "À définir"
        k = f"GE|{row['d']}|{gnorm(lieu)}|{gnorm(row['type'])[:30]}"
        c = {"id": 0, "n": row["type"] or "Compétition", "d": row["d"], "f": row["f"], "v": lieu, "nt": "", "nn": "", "ad": "", "mp": "", "dl": "", "dp": "", "src": "",
             "k": k, "nh": "", "gc": row["cats"], "go": 1, "eps": [{"c": x, "s": s, "n": 0, "u": "", "a": "", "sc": "", "b": "", "t": "", "o": 0, "lic": []} for x in cats for s in ("Hommes", "Dames")]}
        c["gr"], c["rg"], c["dt"] = geo_of(lieu, "")
        if not c["gr"]:
            c["gr"], c["rg"], c["dt"] = "Grand Est", "", ""
        c["ty"], c["tw"] = (ge_type(row) or ("départemental" if re.search("club", gnorm(row["type"])) else "grande régional")), "comité Grand Est (hors calendrier FFE)"
        new.append(c)
    return new, True


prev_html = open(PREV, encoding="utf-8").read()
m = re.search(r"const D=(\{.*?\});\s*\nconst CATS=", prev_html, re.S)
PD = json.loads(m.group(1).replace("<\\/", "</"))
ptir = PD["tir"]
pcomp = {c["k"]: c for c in PD["comps"] if re.match(r"\d{4}-", str(c.get("d"))) and not c.get("go")}

# ---------- Collecte ----------
links = set()
for c in CATS + VETC:
    for lab, base in (("a", "calendrier"), ("p", "calendrier-sportif")):
        links |= set(fiche_links(page(f"{BASE}/{base}/?arme%5BSAB%5D=on&categories={c}", f"liste_{lab}_{c}")))
print("fiches:", len(links), file=sys.stderr)
with ThreadPoolExecutor(8) as ex:
    fiches = [f for f in ex.map(parse_fiche, sorted(links)) if f]
RX = re.compile(r"\b(M9|M11|M13|M15|M17|M20|SENIOR|VET)\b")


def normcat(s_):
    """V1..V4 -> VET (dédoublonné, ordre conservé)."""
    out = []
    for x in re.split(r",\s*", re.sub(r"\s*\(.*?\)", "", s_).strip()):
        x = "VET" if re.fullmatch(r"V[1-4]", x) else x
        if x and x not in out:
            out.append(x)
    return ", ".join(out)
jobs = []
for f in fiches:
    f["epl"] = []
    for e in f["eps"]:
        if not re.search("sabre", e["epreuve"], re.I) or not RX.search(normcat(e["cat"])):
            continue
        sx = "Mixte" if re.search("mixte", e["epreuve"], re.I) else "Dames" if re.search("dames|femmes", e["epreuve"], re.I) else "Hommes" if re.search("hommes", e["epreuve"], re.I) else "?"
        cat = normcat(e["cat"])
        jobs.append((f, {"c": cat, "s": sx, "u": BASE + e["href"], "href": e["href"], "vc": [x for x in VETC if re.search(r"\b" + x + r"\b", e["cat"])]}))
print("épreuves:", len(jobs), file=sys.stderr)
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(lambda j: tireurs(j[1]["href"]), jobs))
for (f, e), r in zip(jobs, res):
    e["lic"] = [x[1] for x in (r or [])]
    e["pl"] = {x[1]: x for x in (r or [])}
    e["ok"] = r is not None
    f["epl"].append(e)
# Vétérans : V1..V4 = une seule épreuve par sexe (inscrits fusionnés)
for f in fiches:
    mg = {}
    out_ = []
    for e in f["epl"]:
        if e["c"] == "VET":
            m_ = mg.get(e["s"])
            if m_ is None:
                e["us"] = [e["u"]]
                e["vn"] = {v_: len(e["lic"]) for v_ in e["vc"]}
                mg[e["s"]] = e
                out_.append(e)
            else:
                m_["us"].append(e["u"])
                for v_ in e["vc"]:
                    m_["vn"][v_] = len(e["lic"])
                    if v_ not in m_["vc"]:
                        m_["vc"].append(v_)
                m_["lic"] = list(dict.fromkeys(m_["lic"] + e["lic"]))
                m_["pl"].update(e["pl"])
                m_["ok"] = m_["ok"] and e["ok"]
        else:
            out_.append(e)
    f["epl"] = out_
newk = {f["k"]: f for f in fiches if f["epl"]}

# notes : texte uniquement pour les compétitions nouvelles ou dont la note a changé
need = {}
for k, f in newk.items():
    if f["nt"]:
        need[f["nt"]] = None
with ThreadPoolExecutor(6) as ex:
    for u, t in zip(need, ex.map(note_text, list(need))):
        need[u] = t

# ---------- Construction ----------
tinfo = {}  # licence -> (nom, prenom, club)
for t in ptir:
    tinfo[t[2]] = (t[0], t[1], t[6])
comps = []
changes = []
for k, f in newk.items():
    old = pcomp.get(k)
    txt = need.get(f["nt"], "") if f["nt"] else ""
    nh = md5(txt) if txt else ""
    reuse = old is not None and (not nh or not old.get("nh") or old["nh"] == nh)
    if old and not reuse:
        changes.append({"k": "Note modifiée", "t": f"{f['v']} · {f['nom']} (horaires, tarifs ou adresse à revérifier)"})
    c = {"k": k, "n": f["nom"], "d": f["d"], "f": f["f"], "v": f["v"], "nt": f["nt"], "nh": nh or (old or {}).get("nh", "")}
    if reuse:
        for a in ("nn", "ad", "mp", "dl", "dp", "src"):
            c[a] = old.get(a, "")
    else:
        addr = address(txt) if txt else ""
        c.update(nn=txt[:80] if txt else "", ad=addr, mp=maps(addr), dl=deadline(txt, f["d"]) if txt else "", dp="",
                 src="Extraction auto" if txt else ("Note illisible" if f["nt"] else ""))
    enrich(c, txt, old if reuse else None)
    oe = {(e["c"], e["s"]): e for e in (old["eps"] if old else [])}
    c["eps"] = []
    for e in f["epl"]:
        for l in e["lic"]:
            if l not in tinfo:
                n, p_, club = e["pl"][l][0], None, e["pl"][l][2]
                tinfo[l] = (*split_name(n), club)
            else:
                tinfo[l] = (tinfo[l][0], tinfo[l][1], e["pl"][l][2] or tinfo[l][2])
        o = oe.get((e["c"], e["s"]))
        if o and reuse:
            fields = {k2: o.get(k2, "") for k2 in ("a", "sc", "b", "t", "o")}
        else:
            c1 = RX.findall(e["c"])[0]
            h = hours(txt, c1) if txt else None
            h = h or ("", "", "")
            fields = {"a": h[0], "sc": h[1], "b": h[2], "t": price(txt, c1) if txt else "",
                      "o": 1 if txt and re.search(r"(?i)\bopen\b", txt) else 0}
        hn = list((o or {}).get("hn") or ([[PD.get("built") or TODAY, o["n"]]] if o else []))
        if not hn or hn[-1][1] != len(e["lic"]):
            hn.append([TODAY, len(e["lic"])])
        c["eps"].append({"c": e["c"], "s": e["s"], "n": len(e["lic"]), "u": e["u"], "lic": e["lic"], "hn": hn, **({"vn": e["vn"], "us": e["us"]} if e.get("vn") else {}), **fields})
        if o:
            oldl = {ptir[i][2] for i in o["l"]}
            add = set(e["lic"]) - oldl
            if o["n"] != len(e["lic"]):
                changes.append({"k": "Inscrits", "t": f"{f['v']} · {e['c']} {e['s']} ({f['d'][8:]}/{f['d'][5:7]}) : {o['n']} → {len(e['lic'])}"})
            for fk, lab in (("a", "appel"), ("sc", "scratch"), ("b", "début"), ("t", "tarif")):
                if reuse and o.get(fk) != fields[fk]:
                    changes.append({"k": "Horaire/tarif", "t": f"{f['v']} · {e['c']} : {lab} {o.get(fk) or '–'} → {fields[fk] or '–'}"})
        else:
            if old:
                changes.append({"k": "Nouvelle épreuve", "t": f"{f['v']} · {e['c']} {e['s']} ({f['d'][8:]}/{f['d'][5:7]})"})
    if old and old.get("dl") != c.get("dl"):
        changes.append({"k": "Date limite", "t": f"{f['v']} · {old.get('dl') or '–'} → {c.get('dl') or '–'}"})
    if not old:
        changes.append({"k": "Nouvelle compétition", "t": f"{f['v']} · {f['nom']} ({f['d'][8:]}/{f['d'][5:7]}/{f['d'][:4]}) · {len(c['eps'])} épreuve(s)"})
    comps.append(c)

inherit_types(comps)
_ge_new, _ge_ok = ge_sync(comps)
_pgo = {c["k"] for c in PD["comps"] if c.get("go")}
for c in _ge_new:
    comps.append(c)
    if c["k"] not in _pgo:
        changes.append({"k": "Nouvelle compétition", "t": f"{c['v']} · {c['n']} ({c['d'][8:]}/{c['d'][5:7]}/{c['d'][:4]}) · seulement au calendrier Grand Est"})

# compétitions absentes du calendrier : on garde les passées, on signale les futures
for k, old in pcomp.items():
    if k in newk:
        continue
    if old["f"] < TODAY:
        c = {a: old[a] for a in old if a != "eps"}
        c["eps"] = [{**{a: e[a] for a in e if a != "l"}, "lic": [ptir[i][2] for i in e["l"]]} for e in old["eps"]]
        comps.append(c)
    else:
        changes.append({"k": "Disparue du calendrier", "t": f"{old['v']} · {old['n']} ({old['d']})"})

# tireurs
parts = collections.defaultdict(list)
for c in comps:
    for e in c["eps"]:
        for l in e["lic"]:
            parts[l].append(e)
tir, tidx = [], {}
for l in sorted(parts, key=lambda x: (tinfo[x][0], tinfo[x][1])):
    cs = sorted({RX.findall(e["c"])[0] for e in parts[l] if len(RX.findall(e["c"])) == 1}, key=lambda x: RANK[x])
    n, p_, club = tinfo[l]
    tidx[l] = len(tir)
    tir.append([n, p_, l, cs[0] if cs else "", cs[-1] if len(cs) > 1 else "", len(parts[l]), club])
old_lics = {t[2] for t in ptir}
newt = [l for l in tidx if l not in old_lics]
if newt:
    changes.append({"k": "Nouveaux tireurs", "t": f"{len(newt)} tireur(s) ajouté(s) à la base"})
for c in comps:
    for e in c["eps"]:
        e["l"] = [tidx[l] for l in e.pop("lic")]
        e.pop("href", None)
comps.sort(key=lambda c: (c["d"], c["v"]))
for i, c in enumerate(comps):
    c["id"] = i
hist = [h for h in PD.get("hist", []) if h["d"] != TODAY]
if not PD.get("hist") and PD.get("changes") and PD.get("built") != TODAY:
    hist.append({"d": PD.get("built", TODAY), "c": PD["changes"]})
if changes:
    hist.append({"d": TODAY, "c": changes[:400]})
D = {"built": TODAY, "since": PD.get("built", ""), "comps": comps, "tir": tir, "changes": changes[:400], "hist": hist[-80:]}
s = json.dumps(D, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
_out = prev_html[:m.start(1)] + s + prev_html[m.end(1):]
# la lecture Artifact renvoie la page enveloppée ; on retire l'enveloppe pour republier et pour build_site.py
_i = _out.find("<title>Sabre Radar</title>")
if _i > 0:
    _out = re.sub(r"\s*</body>\s*</html>\s*$", "", _out[_i:])
open(OUT, "w", encoding="utf-8").write(_out)
print(json.dumps({"comps": len(comps), "tireurs": len(tir), "changements": len(changes)}), file=sys.stderr)
