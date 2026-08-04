"""Check ClinicalTrials.gov records for Duloxetine + Diabetic Neuropathy."""
import urllib.request
import json

def check_trials():
    print("=" * 60)
    print("CHECK 2: DULOXETINE + DIABETIC NEUROPATHY CLINICAL TRIALS")
    print("=" * 60)
    url = "https://clinicaltrials.gov/api/v2/studies?query.cond=Diabetic+Neuropathy&query.term=Duloxetine&pageSize=50"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    studies = data.get("studies", [])
    print(f"Total Studies returned: {len(studies)}")
    
    status_counts = {}
    terminated_studies = []
    
    for s in studies:
        protocol = s.get("protocolSection", {})
        status = protocol.get("designModule", {}).get("overallStatus") or protocol.get("statusModule", {}).get("overallStatus")
        nct_id = protocol.get("identificationModule", {}).get("nctId")
        title = protocol.get("identificationModule", {}).get("briefTitle", "")
        why_stopped = protocol.get("statusModule", {}).get("whyStopped", "N/A")
        
        status_counts[status] = status_counts.get(status, 0) + 1
        if status in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
            terminated_studies.append({
                "nct_id": nct_id,
                "status": status,
                "why_stopped": why_stopped,
                "title": title
            })
            
    print("\nOverall Status Counts:")
    for stat, count in status_counts.items():
        print(f"  - {stat}: {count}")
        
    print(f"\nTerminated / Suspended / Withdrawn Studies ({len(terminated_studies)}):")
    for ts in terminated_studies:
        print(f"  • NCT ID: {ts['nct_id']} | Status: {ts['status']}")
        print(f"    Why Stopped: \"{ts['why_stopped']}\"")
        print(f"    Title: {ts['title'][:80]}")
        print()

if __name__ == "__main__":
    check_trials()
