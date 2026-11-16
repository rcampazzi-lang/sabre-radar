#!/usr/bin/env python3
"""Récupère les classements OFFICIELS FFE (sabre, individuel) et écrit des fichiers JSON dans ffe/.
Totalement séparé des classements calculés de Sabre Radar (resultats.json / index.html).

Usage : python3 ffe_classements.py [--saison 2027] [--ids 1423,1424] [--force]
  - saison : 2027 = saison 2026/2027 (paramètre du site FFE)
  - --ids   : ne traiter que ces classements (test)
  - --force : retélécharger même si la date « Dernière mise à jour » FFE n'a pas changé
Sorties (points par épreuve au format creux [[n° colonne, points], ...]) : ffe/index.json, ffe/<id>.json (un fichier par classement, chargé à la demande par la page).
"""
import argparse, csv, html, io, json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'ffe')
UA = 'Mozilla/5.0 (compatible; SabreRadar/1.0)'
SITE = 'https://www.ffescrime.fr'
EXPORT = 'https://dirigeant.escrime-ffe.fr/classements/export/%s/csv'
MAX_HIST = 12          # nombre de relevés conservés pour l'évolution des rangs
FIXED = ['Rang', 'Nom', 'Prenom', 'Catégorie', 'Nationalité', 'Region', 'Code club', 'Nom club', 'Points']


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError('échec %s : %s' % (url, last))


def clean(x):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', x))).strip()


def liste(saison):
    url = (SITE + '/classements/?arme%5BSAB%5D=on&individuelle_equipe%5B1%5D=on&categorie=&saison='
           + str(saison) + '&niveau=&regions=&departements=')
    s = get(url).decode('utf-8', 'ignore')
    rows = re.findall(r'<div class="section__table-row">(.*?)<!-- /\.section__table-row -->', s, re.S)
    res, vus = [], set()
    for r in rows:
        fid = re.search(r'fiche-classements/(\d+)', r)
        if not fid or fid.group(1) in vus:
            continue
        c = [clean(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', r, re.S)]
        if len(c) < 5:
            continue
        vus.add(fid.group(1))
        genre = ''
        if 'Femmes' in c[2]:
            genre = 'Dames'
        elif 'Hommes' in c[2]:
            genre = 'Hommes'
        res.append({'id': fid.group(1), 'nom': c[0], 'niveau': c[1], 'genre': genre,
                    'cats': [x.strip() for x in c[3].split('/') if x.strip()], 'type': c[4]})
    return res


def maj_fiche(fid):
    s = get('%s/fiche-classements/%s/' % (SITE, fid)).decode('utf-8', 'ignore')
    m = re.search(r'Dernière mise à jour le (\d\d)/(\d\d)/(\d{4}) à (\d\d:\d\d:\d\d)', s)
    return '%s-%s-%sT%s' % (m.group(3), m.group(2), m.group(1), m.group(4)) if m else ''


def num(x):
    x = (x or '').strip().replace(',', '.')
    if not x:
        return None
    try:
        v = float(x)
        return int(v) if v == int(v) else v
    except ValueError:
        return None


def lire_csv(fid):
    raw = get(EXPORT % fid)
    try:
        txt = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        txt = raw.decode('cp1252')
    rd = csv.reader(io.StringIO(txt), delimiter=';')
    head = next(rd)
    ix = {h: i for i, h in enumerate(head)}
    ep_cols = [i for i, h in enumerate(head) if h not in FIXED]
    epreuves = [head[i] for i in ep_cols]
    rows = []
    for r in rd:
        if len(r) < len(FIXED):
            continue
        g = lambda k: (r[ix[k]] if k in ix and ix[k] < len(r) else '').strip()
        rows.append([num(g('Rang')), g('Nom'), g('Prenom'), g('Catégorie'), g('Nationalité'), g('Region'),
                     g('Code club'), g('Nom club'), num(g('Points')),
                     [[k, v] for k, i in enumerate(ep_cols) for v in [num(r[i]) if i < len(r) else None] if v is not None]])
    return epreuves, rows


def cle(r):
    return (r[1] + '|' + r[2] + '|' + r[6]).upper()


def traiter(meta, ancien, force):
    fid = meta['id']
    maj = maj_fiche(fid)
    chemin = os.path.join(OUT, fid + '.json')
    old = None
    if os.path.exists(chemin):
        try:
            old = json.load(open(chemin, encoding='utf-8'))
        except Exception:
            old = None
    if old and not force and old.get('maj') == maj and maj:
        return meta, old, False
    epreuves, rows = lire_csv(fid)
    hist = (old or {}).get('hist', [])
    # relevé de référence = dernier relevé différent (date FFE différente)
    snap = {'maj': maj, 'd': {cle(r): [r[0], r[8]] for r in rows}}
    if not hist or hist[-1]['maj'] != maj:
        hist.append(snap)
    hist = hist[-MAX_HIST:]
    data = dict(meta, maj=maj, epreuves=epreuves, rows=rows, hist=hist)
    return meta, data, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--saison', default='2027')
    ap.add_argument('--ids', default='')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    metas = liste(a.saison)
    if a.ids:
        want = set(a.ids.split(','))
        metas = [m for m in metas if m['id'] in want]
    print('classements à examiner :', len(metas))
    index, changes, erreurs = [], 0, []

    def work(m):
        try:
            return traiter(m, None, a.force)
        except Exception as e:  # noqa
            return m, None, str(e)

    with ThreadPoolExecutor(max_workers=4) as ex:
        for m, data, changed in ex.map(work, metas):
            if data is None:
                erreurs.append((m['id'], changed))
                continue
            if changed:
                changes += 1
                with open(os.path.join(OUT, m['id'] + '.json'), 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            index.append({k: data[k] for k in ('id', 'nom', 'niveau', 'genre', 'cats', 'type', 'maj')}
                         | {'n': len(data['rows'])})
    if a.ids:  # en test, ne pas écraser l'index complet
        print('test : index non réécrit')
    else:
        index.sort(key=lambda x: (x['niveau'], x['nom']))
        with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
            json.dump({'built': time.strftime('%Y-%m-%dT%H:%M'), 'saison': a.saison,
                       'source': SITE + '/classements/', 'classements': index},
                      f, ensure_ascii=False, separators=(',', ':'))
    print('mis à jour : %d | inchangés : %d | erreurs : %d' % (changes, len(index) - changes, len(erreurs)))
    for e in erreurs:
        print('  ERREUR', e)
    return 1 if erreurs else 0


if __name__ == '__main__':
    sys.exit(main())
