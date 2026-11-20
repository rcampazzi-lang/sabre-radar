import json,re,sys,subprocess,difflib,os
sys.path.insert(0,'.')
from geo import norm
B="https://www.escrime-info.com/gregxml/Greg/BD"
def get(url,path):
    if os.environ.get('GREG_FRESH') and os.path.exists(path): os.remove(path)
    if os.path.exists(path) and os.path.getsize(path)>50: return open(path,encoding='utf8',errors='replace').read()
    for i in range(3):
        r=subprocess.run(['curl','-sL','-m','40','-o',path,'-w','%{http_code}',url],capture_output=True,text=True)
        if r.stdout.strip()=='200' and os.path.getsize(path)>50: return open(path,encoding='utf8',errors='replace').read()
    return ''
RXC=re.compile(r'M9|M11|M13|M15|M17|M20|SENIOR|SÉNIOR|SENIORS?',re.I)
def cats(s):
    o=set()
    for x in re.findall(r'M\s?9\b|M\s?11\b|M\s?13\b|M\s?15\b|M\s?17\b|M\s?20\b|S[ée]nior?s?\b|\bS\b|V[1-4]\b|\bV\b|V[ée]t[ée]rans?|\bVET\b',s or '',re.I):
        x=x.upper().replace(' ','')
        o.add('SENIOR' if x.startswith('S') else 'VET' if x.startswith('V') else x)
    return o
def W(s): return {w for w in norm(s).split() if len(w)>=4 and w not in('saint','epreuve','coupe')}
def vlab(g):
    m=re.search(r'\bV([1-4])\b',g['lieu'] or '')
    if m: return 'V'+m.group(1)
    m=re.search(r'\bV[1-4](?:V[1-4])*\b',g['libelle'] or '')
    if m: return re.sub(r'V','-V',m.group(0))[1:].replace('-V','-V')
    return 'Général'
def city(g,c):
    a=W(g['lieu']);b=W(c['v']);a2=W(g['libelle'])
    if (a|a2)&b: return 2
    if any(difflib.SequenceMatcher(None,x,y).ratio()>=0.85 for x in a for y in b): return 1
    return 0
def main():
    html=get(B+"/services/service.php/derniersResultats?jours=400",'gcache/list.json')
    G=[g for g in json.loads(html) if g['libArme']=='S' and g['date']>='2026-08-01']
    h=open('ffe.html').read()
    D=json.loads(re.search(r"const D=(\{.*?\});\s*\nconst CATS=",h,re.S).group(1).replace('<\\/','</'))
    today=__import__('datetime').date.today().isoformat()
    out=[]
    for c in D['comps']:
        if c.get('go') or c['d']>today: continue
        for ei,e in enumerate(c['eps']):
            ec=cats(e['c']);team='equipe' in (e.get('u') or '').lower()
            cand=[]
            for g in G:
                if not (c['d']<=g['date']<=c['f']): continue
                ct=city(g,c)
                if not ct: continue
                if e['s']!='Mixte' and ((g['libSexe']=='H')!=(e['s']=='Hommes')): continue
                if (g['equipe']=='1')!=team: continue
                gc=cats(g['libCategorie'])|cats(g['libelle'])
                if gc and not (ec&gc): continue
                cand.append((g,ct,gc,ec&gc,gc==ec))
            exact=[x for x in cand if x[4] and x[1]==2]
            if ec=={'VET'} and exact and len(exact)==len([x for x in cand if x[3]]): st='auto';sel=exact
            elif len(exact)==1 and len([x for x in cand if x[3]])==1: st='auto';sel=exact
            elif 'VET' in ec and [x for x in cand if x[1]==2 and x[2]=={'VET'}]: st='auto';sel=[x for x in cand if x[1]==2 and x[2]=={'VET'}]  # vétérans: toutes les sous-épreuves V1-V4/Général du même lieu et même date
            elif [x for x in cand if x[3] and ec<=x[2] and W(x[0]['lieu'])&W(c['v'])] and len({re.sub(r'\s*N\d\b','',x[0]['libelle'] or '').strip().lower() for x in cand if x[3] and ec<=x[2] and W(x[0]['lieu'])&W(c['v'])})==1: st='auto';sel=[x for x in cand if x[3] and ec<=x[2] and W(x[0]['lieu'])&W(c['v'])]  # un seul tournoi Greg (tableaux N1/N2/N3 ou lieux suffixés) dans la même ville
            elif cand and any(x[3] for x in cand): st='valider';sel=[x for x in cand if x[3]]
            elif cand: st='valider';sel=cand
            else: st='aucun';sel=[]
            out.append(dict(k=c['k'],cid=c['id'],ei=ei,d=c['d'],f=c['f'],v=c['v'],n=c['n'],cat=e['c'],s=e['s'],st=st,eq=1 if team else 0,
                 cand=[dict(id=x[0]['id'],lieu=x[0]['lieu'],lib=x[0]['libelle'],cat=x[0]['libCategorie'],date=x[0]['date'],lab=vlab(x[0]) if 'VET' in x[2] else '') for x in sel]))
    json.dump(out,open('greg_match.json','w'),ensure_ascii=False)
    import collections;print(collections.Counter(x['st'] for x in out),len(G))
if __name__=='__main__': main()
