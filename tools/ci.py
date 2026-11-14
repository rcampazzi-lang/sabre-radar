#!/usr/bin/env python3
"""Mise à jour automatique sur GitHub Actions.
Usage: python3 tools/ci.py MODE [CLES]
 MODE = full (FFE + Greg) | live (Greg, compétitions du jour) | comp (Greg, compétitions CLES séparées par des virgules)
Lit index.html du dépôt, régénère les données, réécrit index.html / resultats.json / candidats.json."""
import json, os, re, shutil, subprocess, sys
mode = sys.argv[1] if len(sys.argv) > 1 else "live"
keys = sys.argv[2].strip() if len(sys.argv) > 2 else ""
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tools = os.path.join(root, "tools")
tmp = "/tmp/ffe"; work = tmp + "/work"; greg = tmp + "/greg"
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(greg + "/gcache"); os.makedirs(work)
s = open(root + "/index.html", encoding="utf-8").read()
core = re.sub(r"\s*</body>\s*</html>\s*$", "", s[s.index("<title>Sabre Radar</title>"):])
open(tmp + "/prev.html", "w", encoding="utf-8").write(core)
ffe = tmp + "/ffe.html"
if mode == "full":
    subprocess.run([sys.executable, "-I", tools + "/update.py", tmp + "/prev.html", ffe, work], check=True)
    out = open(ffe, encoding="utf-8").read()
    D = json.loads(re.search(r"const D=(\{.*?\});\s*\nconst CATS=", out, re.S).group(1).replace("<\\/", "</"))
    n = len(D["comps"])
    print("compétitions:", n, "tireurs:", len(D["tir"]))
    if not (238 <= n <= 322):
        sys.exit("Nombre de compétitions inattendu (%d) : rien n'est publié." % n)
else:
    shutil.copy(tmp + "/prev.html", ffe)
for f in ("greg_match.py", "greg_fetch.py", "greg_run.py", "geo.py"):
    shutil.copy(tools + "/" + f, greg + "/" + f)
shutil.copy(ffe, greg + "/ffe.html")
for f in ("resultats.json", "candidats.json", "greg_valid.json"):
    if os.path.exists(root + "/" + f):
        shutil.copy(root + "/" + f, greg + "/" + f)
env = dict(os.environ, GREG_FRESH="1")
subprocess.run([sys.executable, "greg_match.py"], cwd=greg, env=env, check=True)
args = [sys.executable, "greg_run.py"]
if mode == "live":
    args.append("--live")
elif mode == "comp":
    if not keys:
        sys.exit("Aucune clé de compétition.")
    args.append("--comp=" + keys)
subprocess.run(args, cwd=greg, env=env, check=True)
shutil.copy(greg + "/resultats.json", root + "/resultats.json")
shutil.copy(greg + "/candidats.json", root + "/candidats.json")
if mode == "full":
    subprocess.run([sys.executable, root + "/build_site.py", ffe, root + "/resultats.json", root + "/candidats.json"], check=True)
print("terminé:", mode)
