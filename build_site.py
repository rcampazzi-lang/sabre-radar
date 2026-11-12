#!/usr/bin/env python3
"""Usage: python3 build_site.py PAGE_HTML RESULTATS_JSON CANDIDATS_JSON
Met à jour index.html, resultats.json et candidats.json à la racine du dépôt (les icônes et le manifest y sont déjà)."""
import sys,os,shutil
page,res,cand=sys.argv[1:4]
here=os.path.dirname(os.path.abspath(__file__))
HEAD=('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
 '<link rel="manifest" href="manifest.json"><link rel="apple-touch-icon" href="apple-touch-icon.png">'
 '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Sabre Radar">'
 '<meta name="apple-mobile-web-app-status-bar-style" content="default"><meta name="theme-color" content="#0a5c50">')
s=open(page,encoding='utf-8').read()
assert '<title>Sabre Radar</title>' in s[:200] and 'const D=' in s, "page inattendue"
open(os.path.join(here,'index.html'),'w',encoding='utf-8').write(HEAD+s)
shutil.copy(res,os.path.join(here,'resultats.json'));shutil.copy(cand,os.path.join(here,'candidats.json'))
print("ok")
