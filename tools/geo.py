import re,unicodedata
def norm(s): s=unicodedata.normalize('NFD',s.lower()); s=''.join(c for c in s if unicodedata.category(c)!='Mn'); s=re.sub(r'\bsaint(e?)\b',lambda m:'st'+m.group(1),s); return re.sub(r'[^a-z0-9]+',' ',s).strip()
