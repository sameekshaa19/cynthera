import sqlite3
import json

conn = sqlite3.connect('data/cynthera.db')
cursor = conn.cursor()

try:
    rows = cursor.execute('SELECT cache_key, drug_name, disease_name, retrieval_policy, created_at, expires_at, hit_count, result_json FROM evaluation_cache').fetchall()
    print('=== EVALUATION CACHE ENTRIES ===')
    print(f'Total entries: {len(rows)}')
    for r in rows:
        res = json.loads(r[7])
        ma = res.get('mechanistic_assessment', {})
        ar = res.get('audit_report', {})
        print(f"Key: {r[0][:10]}... | Drug: {r[1]} | Disease: {r[2]} | Policy: {r[3]} | Hits: {r[6]}")
        print(f"  Score: {ma.get('score')} | Level: {ma.get('level')}")
        print(f"  MA candidate_mechanisms: {len(ma.get('candidate_mechanisms', []))}")
        print(f"  AR candidate_mechanisms: {len(ar.get('candidate_mechanisms', []))}")
        print(f"  Chain: {ma.get('mechanistic_chain')}")
except Exception as e:
    print("Error querying evaluation_cache:", e)

try:
    evals = cursor.execute('SELECT hypothesis_id, drug_name, disease_name, recommendation, mechanistic_score, completed_at FROM evaluations').fetchall()
    print('\n=== PERSISTENT EVALUATIONS ===')
    for e in evals:
        print(e)
except Exception as e:
    print("Error querying evaluations:", e)
