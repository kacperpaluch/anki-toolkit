def truncate(text,limit=60): return text if len(text)<=limit else text[:limit-1]+'…'
def oxford_fields(entry,existing,match): return {k:v for k,v in entry.items() if not k.startswith('_') and k!=match and k in existing and not existing[k].strip() and v.strip()}
def sm_fields(entry,existing,mapping,match):
 out={}
 for src,dst in mapping.items():
  value=entry.get(src,'').strip()
  if src=='PartOfSpeech': value=value.rstrip(')').strip()
  if dst!=match and dst in existing and not existing[dst].strip() and value: out[dst]=value
 return out
