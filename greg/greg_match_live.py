"""greg_match_live.py — comme greg_match.py (règles inchangées, importé tel quel) mais interroge aussi Greg pour les compétitions
qui commencent DEMAIN (greg_match.py ignore celles dont la date de début est postérieure à aujourd'hui).
Usage : GREG_FRESH=1 python3 greg_match_live.py   (dans le dossier contenant ffe.html, geo.py, greg_match.py)
Écrit greg_match.json comme greg_match.py. Sert à voir les inscrits dès la veille, quand Greg les publie déjà."""
import datetime, sys
sys.path.insert(0, ".")
import greg_match
_REAL = datetime.date
class _D(_REAL):
    @classmethod
    def today(cls):
        return _REAL.today() + datetime.timedelta(days=1)
datetime.date = _D
greg_match.main()
