import csv

FILE = "./questions.csv"

with open(FILE, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile, ["ID", "question", "location", "comment"])
    locations = set()
    for row in reader:
        loc = row["location"].strip()
        if loc:
            locations.add(loc   )
            
with open("locs.txt", "w", encoding="utf-8") as f:
    for loc in sorted(locations):
        f.write(f"{loc}\n")
        
