#!/usr/bin/env python3
"""Usage: python3 build_site.py PAGE_HTML RESULTATS_JSON CANDIDATS_JSON
Met à jour index.html, resultats.json et candidats.json à la racine du dépôt (les icônes et le manifest y sont déjà)."""
import sys,os,shutil
page,res,cand=sys.argv[1:4]
here=os.path.dirname(os.path.abspath(__file__))
HEAD=('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
 '<link rel="manifest" href="manifest.json"><link rel="apple-touch-icon" href="apple-touch-icon.png">'
 '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Sabre Radar">'
 '<meta name="apple-mobile-web-app-status-bar-style" content="default"><meta name="theme-color" content="#D9541E">')
import time
BUILD=str(int(time.time()))
HEAD+=('<script>(function(){var B="%s";try{if(location.search.indexOf("v=")>-1&&location.search.indexOf("v="+B)>-1)return;'
 'fetch(location.pathname+"?c="+Date.now(),{cache:"no-store"}).then(function(r){return r.text()}).then(function(t){'
 'var m=t.match(/var B="(\\d+)"/);if(m&&m[1]!==B){location.replace(location.pathname+"?v="+m[1])}}).catch(function(){})}catch(e){}})()</script>')%BUILD
s=open(page,encoding='utf-8').read()
assert '<title>Sabre Radar</title>' in s[:200] and 'const D=' in s, "page inattendue"
open(os.path.join(here,'index.html'),'w',encoding='utf-8').write(HEAD+s)
shutil.copy(res,os.path.join(here,'resultats.json'));shutil.copy(cand,os.path.join(here,'candidats.json'))
print("ok")
