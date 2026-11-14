"""Collecte des résultats Greg -> resultats.json (incrémental).
Usage: python3 greg_run.py [--live | --comp=CLE[,CLE2]]
 - défaut : récupère les épreuves pas encore terminées (compétition passée avec classement final = 'done', jamais retouchée).
 - --comp=CLE[,CLE2] : ne rafraîchit que la compétition de clé CLE (même terminée).
 - --live : ne rafraîchit que les compétitions dont les dates incluent aujourd'hui (résultats en direct).
Prérequis : greg_match.json (python3 greg_match.py, avec ffe.html dans le dossier) ; GREG_FRESH=1 pour ignorer le cache."""
import json,sys,datetime,os
os.environ.setdefault('GREG_FRESH','1')
sys.path.insert(0,'.')
from greg_fetch import fetch
from concurrent.futures import ThreadPoolExecutor
LIVE='--live' in sys.argv
_c=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--comp=')),None)
COMP=set(x.strip() for x in _c.split(',') if x.strip()) if _c else None
try:
    from zoneinfo import ZoneInfo
    now=datetime.datetime.now(ZoneInfo('Europe/Paris'))
except Exception: now=datetime.datetime.now()
today=now.date().isoformat()
M=json.load(open('greg_match.json'))
try: VAL=json.load(open('greg_valid.json'))
except: VAL={}
try: OLD=json.load(open('resultats.json')).get('eps',{})
except: OLD={}
LAB={c['id']:c.get('lab','') for m in M for c in m['cand']}
def lord(i): l=LAB.get(i,''); return (0,'') if l=='Général' else (1,l)
def key(m): return f"{m['k']}|{m['cat']}|{m['s']}"
def ids_of(m): return sorted([c['id'] for c in m['cand']] if m['st']=='auto' else VAL.get(key(m),[]),key=lord)
todo={};keep={}
for m in M:
    ids=ids_of(m)
    if not ids: continue
    o=OLD.get(key(m))
    f=m.get('f') or m['d']
    if o and o.get('done') and o.get('gids')==ids and not COMP: keep[key(m)]=o;continue
    if COMP:
        if m['k'] not in COMP:
            if o: keep[key(m)]=o
            continue
    elif LIVE and not (m['d']<=today<=f):
        if o: keep[key(m)]=o
        continue
    for i in ids: todo[i]=None
with ThreadPoolExecutor(3) as ex:
    for gid,r in zip(list(todo),ex.map(fetch,list(todo))): todo[gid]=r
R={}
for m in M:
    k=key(m);ids=ids_of(m)
    if not ids: continue
    if k in keep: R[k]=keep[k];continue
    res=[todo[i] for i in ids if todo.get(i)]
    if not res: continue
    f=m.get('f') or m['d']
    done=f<today and all(r['final'] for r in res)
    R[k]={'src':'greg','gids':ids,'res':res,**({'labels':[LAB.get(i,'') or 'Tableau' for i in ids if todo.get(i)]} if any(LAB.get(i) for i in ids) else {}),'t':now.strftime('%Y-%m-%dT%H:%M'),**({'done':True} if done else {})}
# candidats à valider (page Admin)
pend=[m for m in M if m['st']=='valider' and key(m) not in VAL]
cres={}
need=[c['id'] for m in pend for c in m['cand']]
try: OC=json.load(open('candidats.json')).get('res',{})
except: OC={}
if LIVE or COMP: cres.update({i:OC[i] for i in need if i in OC})
todo2=[i for i in dict.fromkeys(need) if i not in cres]
with ThreadPoolExecutor(3) as ex:
    for gid,r in zip(todo2,ex.map(lambda i: todo.get(i) or fetch(i),todo2)): cres[gid]=r
json.dump({'built':now.strftime('%Y-%m-%dT%H:%M'),'pend':[{'key':key(m),'k':m['k'],'cat':m['cat'],'s':m['s'],'cand':[dict(id=c['id'],lieu=c['lieu'],lib=c['lib'],cat=c['cat'],lab=c.get('lab','')) for c in m['cand']]} for m in pend],'res':cres},open('candidats.json','w'),ensure_ascii=False,separators=(',',':'))
json.dump({'built':now.strftime('%Y-%m-%dT%H:%M'),'eps':R},open('resultats.json','w'),ensure_ascii=False,separators=(',',':'))
print(len(pend),'à valider;',len(R),'épreuves,',len(todo),'récupérées,',len(keep),'conservées,',sum(1 for v in R.values() if v.get('done')),'terminées')
