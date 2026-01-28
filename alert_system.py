import os
import requests

def main(args):
    # 1. Configuration & Thresholds
    # Using 100 as the surge threshold for PSI/PM2.5 as planned
    SURGE_THRESHOLD = 100 
    API_KEY = os.getenv('DATA_GOV_SG_API_KEY')
    
    try:
        # 2. Fetch Live Data from NEA/Data.gov.sg
        # Replace this URL with your specific NEA endpoint if different
        response = requests.get(
            "https://api-open.data.gov.sg/v2/realtime/api/psi",
            headers={"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
        )
        data = response.json()
        
        # 3. Extract PSI (Example: National or specific region)
        # Adjust the path based on the actual JSON structure of your API
        current_psi = data['data']['items'][0]['readings']['psi_twenty_four_hourly']['national']
        
        # 4. The Logic Gate: Is there a surge?
        if current_psi > SURGE_THRESHOLD:
            # 5. Trigger the Alert
            # In a real scenario, this calls the watsonx Orchestrate Webhook
            alert_msg = f"URGENT: Air quality surge detected (PSI: {current_psi}). Notify Polyclinic to prepare masks."
            print(alert_msg)
            
            return {
                "body": {
                    "status": "ALERT_TRIGGERED",
                    "psi": current_psi,
                    "message": alert_msg
                },
                "statusCode": 200
            }
        else:
            return {
                "body": {"status": "NORMAL", "psi": current_psi, "message": "Air quality is within safe limits."},
                "statusCode": 200
            }

    except Exception as e:
        return {
            "body": {"error": str(e)},
            "statusCode": 500
        }
