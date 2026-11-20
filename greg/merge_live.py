"""merge_live.py ORIG.json NEW.json CLES OUT.json — reporte dans ORIG uniquement les épreuves des compétitions CLES refaites par greg_run.
greg_run réécrit resultats.json avec les seules épreuves Greg : on ne doit pas perdre les épreuves issues des PDF FFE.
Une épreuve déjà terminée et issue d'un PDF (src pdf ou greg+pdf) n'est jamais remplacée."""
import sys, json
orig = json.load(open(sys.argv[1])); new = json.load(open(sys.argv[2]))
cles = {c.strip() for c in sys.argv[3].split(",") if c.strip()}
eps = orig.get("eps", {}); n = 0
for k, v in new.get("eps", {}).items():
    if k.split("|")[0] not in cles: continue
    o = eps.get(k)
    if o and o.get("done") and o.get("src") in ("pdf", "greg+pdf"): continue
    if o != v: eps[k] = v; n += 1
orig["eps"] = eps; orig["built"] = new.get("built", orig.get("built"))
json.dump(orig, open(sys.argv[4], "w"), ensure_ascii=False, separators=(",", ":"))
print("épreuves remplacées :", n, "| total :", len(eps))
