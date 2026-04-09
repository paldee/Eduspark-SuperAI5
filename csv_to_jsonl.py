import csv
import json

# Open the CSV and output JSONL with appropriate encoding
with open("train.csv", "r", encoding="utf-8-sig") as csvfile, open("output.jsonl", "w", encoding="utf-8") as jsonlfile:
    reader = csv.DictReader(csvfile)
    
    for row in reader:
        prompt = row.get("sentence", "").strip()
        completion = row.get("thai_sentence", "").strip()

        json_obj = {
            "prompt": prompt,
            "completion": f" {completion}"  # leading space for training formats like OpenAI fine-tuning
        }

        jsonlfile.write(json.dumps(json_obj, ensure_ascii=False) + "\n")