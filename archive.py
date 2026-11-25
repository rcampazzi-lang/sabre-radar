#!/usr/bin/env python3
"""archive.py ARCHIVE.json FFE_HTML RESULTATS.json [OUT.json]
Archive permanente des résultats d'épreuves (jamais effacée) : sert au classement glissant et à la note de force.
- reprend l'archive existante (si elle existe) ;
- ajoute / remplace, pour chaque épreuve de RESULTATS.json qui a des résultats, l'entrée complète (joueurs, poules, tableaux, classement final)
  avec les informations de la compétition (date, lieu, nom, type) prises dans la page FFE_HTML ;
- ne remplace jamais une entrée par une version moins complète (poules, matchs de tableau, classement final) ;
- ne supprime jamais rien : une compétition qui disparaît du calendrier FFE reste dans l'archive.
Écrit OUT.json (par défaut ARCHIVE.json)."""
import sys, os, re, json, time
arch_p, html_p, res_p = sys.argv[1:4]
out_p = sys.argv[4] if len(sys.argv) > 4 else arch_p
h = open(html_p, encoding="utf-8").read()
D = json.loads(re.search(r"const D=(\{.*?\});\s*\nconst CATS=", h, re.S).group(1).replace("<\\/", "</"))
comps = {c["k"]: c for c in D["comps"]}
try: A = json.load(open(arch_p, encoding="utf-8"))
except Exception: A = {}
eps = A.get("eps", {})
OLD = json.loads(json.dumps(eps))
R = json.load(open(res_p, encoding="utf-8")).get("eps", {})
def score(e):
    rs = e.get("res", [])
    return (sum(len(r.get("poules", [])) for r in rs), sum(len(m.get("matches", [])) for r in rs for m in r.get("tableau", [])), sum(len(r.get("final", [])) for r in rs))
new = upd = skip = keep = 0
# épreuves tirées en mixte : le résultat « <cat> Mixte » remplace les anciennes entrées Hommes / Dames de la même catégorie (sinon matchs comptés plusieurs fois)
for key in list(R):
    p = key.split("|")
    if len(p) == 3 and p[2] == "Mixte" and R[key] and R[key].get("res"):
        for sx in ("Hommes", "Dames"):
            eps.pop("%s|%s|%s" % (p[0], p[1], sx), None)
def _mixte_existe(key):
    p = key.split("|")
    return len(p) == 3 and p[2] in ("Hommes", "Dames") and ("%s|%s|Mixte" % (p[0], p[1])) in eps
for key, e in R.items():
    if _mixte_existe(key): skip += 1; continue
    if not e or not e.get("res"): skip += 1; continue
    parts = key.split("|")
    ck, cat, sex, eq = parts[0], parts[1], parts[2], (len(parts) > 3 and parts[3] == "Eq")
    c = comps.get(ck)
    old = eps.get(key)
    meta = ({k: c.get(k, "") for k in ("k", "d", "f", "v", "n", "nn", "ty")} if c else (old or {}).get("c"))
    if not meta: skip += 1; continue
    if old and score(old["e"]) > score(e):   # on ne remplace jamais par un résultat moins complet
        keep += 1; continue
    if old: upd += 1
    else: new += 1
    eps[key] = {"c": meta, "cat": cat, "s": sex, "eq": 1 if eq else 0, "e": e}
if OLD == eps and os.path.exists(out_p) and out_p == arch_p:
    print("archive : inchangée (%d épreuves)" % len(eps)); sys.exit(0)
A = {"built": time.strftime("%Y-%m-%dT%H:%M"), "eps": eps}
json.dump(A, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("archive : %d épreuves (+%d nouvelles, %d mises à jour, %d conservées car plus complètes, %d ignorées) -> %s, %.1f Mo" % (len(eps), new, upd, keep, skip, out_p, os.path.getsize(out_p) / 1e6))
