import json

for fname, label in [
    ("output/dhanush_canonical.json",  "DHANUSH"),
    ("output/srividya_canonical.json", "SRIVIDYA"),
]:
    d = json.load(open(fname, encoding="utf-8"))
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    print(f"  full_name          : {d.get('full_name')}")
    print(f"  primary_email      : {d.get('primary_email')}")
    print(f"  phone              : {d.get('phone')}")
    print(f"  location           : {d.get('location')}")
    print(f"  links.github       : {d.get('links', {}).get('github')}")
    print(f"  links.linkedin     : {d.get('links', {}).get('linkedin')}")
    print(f"  years_experience   : {d.get('years_experience')}")
    print(f"  skills count       : {len(d.get('skills') or [])}")
    print(f"  experience entries : {len(d.get('experience') or [])}")
    print(f"  education entries  : {len(d.get('education') or [])}")
    print(f"  overall_confidence : {d.get('overall_confidence')}")
