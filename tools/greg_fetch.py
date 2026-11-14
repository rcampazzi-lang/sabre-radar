import json,re,sys,html,time
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,'.')
from greg_match import get,B
def tx(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s))).strip()
def page(gid,mode):
    u=f"{B}/afficher.php?epreuve={gid}"+(f"&mode={mode}" if mode else "")
    time.sleep(0.2)
    return get(u,f"gcache/{gid}_{mode or 'final'}.html")
def body(h):
    i=h.find('</nav>');h=h[i:] if i>0 else h
    return re.split(r'<script>\(function\(\)\{function c\(\)',h)[0]
def tables(h):
    out=[];ctx=''
    for m in re.finditer(r'<h5>(.*?)</h5>|<caption>(.*?)</caption>|<table.*?</table>',body(h),re.S):
        if m.group(1) is not None: ctx=tx(m.group(1));continue
        if m.group(2) is not None: ctx=tx(m.group(2));continue
        t=m.group(0);rows=[]
        cm=re.search(r'<caption>(.*?)</caption>',t,re.S)
        if cm: ctx=tx(cm.group(1))
        for r in re.findall(r'<tr(.*?)</tr>',t,re.S):
            idm=re.search(r'id=(\d+)',r.split('>')[0])
            cells=[tx(x) for x in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>',r,re.S)]
            rows.append((idm.group(1) if idm else None,cells,'overheader' in r.split('>')[0]))
        out.append((ctx,rows))
    return out
def num(x):
    try: return float(x) if '.' in x else int(x)
    except: return x
def parse_ins(h):
    P={}
    for ctx,rows in tables(h):
        for gid,c,hd in rows:
            if gid and len(c)>=4 and not hd: P[gid]=[c[1],c[2],c[3],c[4] if len(c)>4 else '']
    return P
def parse_poules(h,P):
    poules=[];clas=[]
    for ctx,rows in tables(h):
        if not rows: continue
        head=rows[0][1]
        m=re.search(r'Tour n°\s*(?:Tour n°\s*)?(\d+)',ctx);tour=int(m.group(1)) if m else 1
        if 'Poule' in ctx:
            pn=re.search(r'Poule n°\s*(\d+)',ctx);arb=re.search(r'Arbitre\s*:\s*(.*)$',ctx)
            R=[]
            for gid,c,hd in rows[1:]:
                if not gid or len(c)<8: continue
                nb=len(rows)-1
                # c = N°, Nation, Nom, Prénom, Club, résultats(nb+? cellules), V, TD, TR, Pl
                n=c[0];nom,pre,club=c[2],c[3],c[4];rest=c[5:]
                P.setdefault(gid,[nom,pre,club,''])
                R.append(dict(id=gid,n=n,m=[x for x in rest[:-4]][:-1],v=num(rest[-4]),td=num(rest[-3]),tr=num(rest[-2]),pl=num(rest[-1])))
            poules.append(dict(tour=tour,poule=int(pn.group(1)) if pn else 0,arb=(arb.group(1).strip() if arb else ''),rows=R))
        elif head and head[0].startswith('Pl') and 'Indice' in head:
            R=[]
            for gid,c,hd in rows[1:]:
                if not gid or len(c)<8: continue
                P.setdefault(gid,[c[2],c[3],c[4],''])
                R.append(dict(pl=num(c[0]),id=gid,v=num(c[5]),td=num(c[6]),tr=num(c[7]),ind=num(c[8]) if len(c)>8 else ''))
            clas.append(dict(tour=tour,rows=R))
    return poules,clas
class TP(HTMLParser):
    def __init__(s):
        super().__init__();s.stack=[];s.trees=[];s.cur=None;s.match=None;s.ti=None;s.lab=None;s.place='';s.h5=False;s.buf=''
    def handle_starttag(s,tag,a):
        a=dict(a);cl=(a.get('class') or '').split()
        if tag=='h5':s.h5=True;s.buf=''
        if tag!='div':return
        s.stack.append(cl)
        if 'root' in cl: s.cur={'place':s.place,'matches':[]};s.trees.append(s.cur)
        if 'match' in cl: s.match={'t':[],'depth':sum('branch' in c for c in s.stack),'arb':'','piste':''}
        if 'tireur' in cl and s.match is not None:
            s.ti={'name':'','club':'','sc':'','ex':False};s.match['t'].append(s.ti);s.ti['_div']=len(s.stack)
        if 'intitule' in cl and s.ti is not None: s.ti['club']=a.get('title','');s.lab='name'
        if 'score' in cl and s.ti is not None: s.lab='sc'
        if 'arbitre' in cl and s.match is not None: s.lab='arb'
        if 'piste' in cl and s.match is not None: s.lab='piste'
    def handle_data(s,d):
        if s.h5:s.buf+=d
        if s.lab and s.match is not None:
            if s.lab in('name','sc'): s.ti[s.lab]+=d
            else: s.match[s.lab]+=d
        elif s.ti is not None and s.lab is None and 'Exempt' in d: s.ti['ex']=True
    def handle_endtag(s,tag):
        if tag=='h5':
            s.h5=False;m=re.search(r'Place n°\s*(\d+)',s.buf)
            if m:s.place=m.group(1)
        if tag!='div':return
        cl=s.stack.pop() if s.stack else []
        if 'intitule' in cl or 'score' in cl or 'arbitre' in cl or 'piste' in cl:s.lab=None
        if 'tireur' in cl:s.ti=None
        if 'match' in cl and s.match is not None:
            s.cur['matches'].append(s.match);s.match=None
def parse_tab(h,P):
    p=TP();p.feed(body(h))
    out=[]
    def norm(s): return re.sub(r'\s+',' ',s.strip().lower())
    byname={(norm(pre+' '+nom),club):gid for gid,(nom,pre,club,_) in P.items()}
    for t in p.trees:
        M=[]
        for m in t['matches']:
            T=[]
            for x in m['t']:
                if x['ex'] or not x['name'].strip(): T.append(None);continue
                nm=norm(x['name']);gid=byname.get((nm,x['club']))
                if not gid:
                    for (n2,c2),g2 in byname.items():
                        if n2==nm: gid=g2;break
                T.append(dict(id=gid,name=x['name'].strip(),sc=x['sc'].strip()))
            M.append(dict(r=m['depth'],a=T[0] if T else None,b=T[1] if len(T)>1 else None,arb=re.sub(r'^.*Arbitre\s*:','',m['arb']).strip(),piste=m['piste'].strip()))
        out.append(dict(place=t['place'],matches=M))
    return out
def parse_final(h):
    R=[]
    for ctx,rows in tables(h):
        for gid,c,hd in rows:
            if gid and not hd and c and c[0].isdigit(): R.append(dict(pl=int(c[0]),id=gid))
    return R
def fetch(gid):
    ins=page(gid,'Inscrits');P=parse_ins(ins) if ins else {}
    po,cl=parse_poules(page(gid,'Poules'),P)
    tab=parse_tab(page(gid,'Tableau_tree'),P)
    fin=parse_final(page(gid,''))
    return dict(gid=gid,url=f"{B}/afficher.php?epreuve={gid}",players=P,ins=sorted(parse_ins(ins)) if ins else [],poules=po,classement_poules=cl,tableau=tab,final=fin)
if __name__=='__main__':
    r=fetch(sys.argv[1]);print(json.dumps(r,ensure_ascii=False)[:2500]);print({k:(len(v) if hasattr(v,'__len__') else v) for k,v in r.items()})
