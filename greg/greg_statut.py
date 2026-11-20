"""greg_statut.py CLES FFE_HTML GREG_MATCH.json RESULTATS.json STATUT.json — compte rendu de l'actualisation Greg ciblée.
CLES = clés de compétition séparées par des virgules (celles de CIBLE:). Pour chaque épreuve de ces compétitions écrit
STATUT.json : {"built":..., "eps":{"<clé épreuve>":{"st":..., "t":"AAAA-MM-JJTHH:MM", "why":"..."}}}.
st : ok (résultats Greg trouvés) | inscrits (épreuve sur Greg avec ses inscrits, pas encore de résultats) | vide (épreuve rapprochée mais Greg n'a encore rien publié) | valider (plusieurs
candidats Greg, rapprochement à valider) | aucun (pas (encore) sur Greg) | futur (compétition trop lointaine, non cherchée). Les autres entrées du fichier existant sont conservées (fusion)."""
import sys, json, re, datetime
try:
    from zoneinfo import ZoneInfo
    now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
except Exception:
    now = datetime.datetime.now()
cles = {c.strip() for c in sys.argv[1].split(",") if c.strip()}
h = open(sys.argv[2], encoding="utf-8").read()
D = json.loads(re.search(r"const D=(\{.*?\});\s*\nconst CATS=", h, re.S).group(1).replace("<\\/", "</"))
M = json.load(open(sys.argv[3]))
R = json.load(open(sys.argv[4])).get("eps", {})
try: S = json.load(open(sys.argv[5]))
except Exception: S = {}
eps = S.get("eps", {})
today = now.date().isoformat(); t = now.strftime("%Y-%m-%dT%H:%M")
def key(k, c, s, eq=False): return f"{k}|{c}|{s}" + ("|Eq" if eq else "")
byk = {}
for m in M: byk[key(m["k"], m["cat"], m["s"], m.get("eq"))] = m
n = {"ok": 0, "inscrits": 0, "vide": 0, "valider": 0, "aucun": 0, "futur": 0}
for c in D["comps"]:
    if c["k"] not in cles: continue
    for e in c["eps"]:
        team = "equipe" in (e.get("u") or "").lower()
        k = key(c["k"], e["c"], e["s"], team)
        m = byk.get(k)
        r0 = (R.get(k) or {}).get("res") or []
        cnt = None
        if r0:
            r = r0[0]
            if r.get("poules") or r.get("tableau") or r.get("final"): st, why = "ok", ""
            else:
                st, why = "inscrits", "épreuve présente sur Greg avec ses inscrits, sans résultat pour l'instant"
                cnt = len(r.get("ins") or r.get("players") or {})
        elif m is None:
            st, why = ("futur", "compétition trop lointaine : Greg non interrogé") if c["d"] > (now.date() + datetime.timedelta(days=1)).isoformat() else ("aucun", "épreuve absente du rapprochement Greg")
        elif m["st"] == "valider":
            st, why = "valider", "plusieurs épreuves Greg possibles : rapprochement à valider"
        elif m["st"] == "aucun":
            st, why = "aucun", "pas (encore) sur Greg : aucune épreuve correspondante"
        else:
            st, why = "vide", "épreuve Greg rapprochée mais sans inscrits ni résultat publiés"
        eps[k] = {"st": st, "t": t, "why": why, **({"n": cnt} if cnt is not None else {})}; n[st] = n.get(st, 0) + 1
json.dump({"built": t, "eps": eps}, open(sys.argv[5], "w"), ensure_ascii=False, separators=(",", ":"))
print("statut :", n)
