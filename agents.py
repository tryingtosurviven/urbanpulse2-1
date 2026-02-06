# agents.py
from datetime import datetime
import pandas as pd

class Agent:
    """Base class for all agents."""
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.memory = []

    def log_action(self, action: str, data: dict):
        """Log agent actions for transparency."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.name,
            "action": action,
            "data": data
        }
        self.memory.append(log_entry)
        print(f"[LOG] {self.name}: {action}")
        return log_entry


class EnvironmentSentinel(Agent):
    """The Manager Agent that coordinates everything."""
    def __init__(self):
        super().__init__("Environment Sentinel", "Manager")
        self.sub_agents = {}

    def register_agent(self, agent: Agent):
        """Register a sub-agent to be coordinated."""
        self.sub_agents[agent.name] = agent
        print(f"✅ Registered: {agent.name}")

    def run_cycle(self, scenario_data: dict):
        """Run one full cycle of the agent system."""
        print(f"\n{'='*60}")
        print(f"🚨 ENVIRONMENT SENTINEL: Starting cycle")
        print(f"   Scenario: {scenario_data['description']}")
        print(f"{'='*60}\n")
        
        self.log_action("start_cycle", {"scenario": scenario_data["description"]})

        # 1. Perception (Data Collection)
        scalestack_agent = self.sub_agents["Scalestack Agent"]
        environmental_data = scalestack_agent.execute(scenario_data)

        # 2. Prediction & Risk Assessment
        medical_agent = self.sub_agents["Dynamiq Medical Agent"]
        risk_assessment = medical_agent.execute(environmental_data)

        # 3. Autonomous Action (if needed)
        if risk_assessment["risk_level"] != "LOW":
            print(f"\n⚠️  HEALTH SURGE PROTOCOL ACTIVATED")
            print(f"   Risk Level: {risk_assessment['risk_level']}")
            print(f"   Predicted Surge: {risk_assessment['predicted_surge']:.0%}\n")
            
            healthcare_agent = self.sub_agents["Healthcare Preparedness Agent"]
            supply_chain_agent = self.sub_agents["Supply Chain Agent"]

            healthcare_alerts = healthcare_agent.execute(risk_assessment)
            supply_chain_actions = supply_chain_agent.execute(risk_assessment)
            
            self.log_action("end_cycle", {
                "status": "ACTION_TAKEN",
                "risk_level": risk_assessment["risk_level"]
            })
            
            return {
                "status": "ACTION_TAKEN",
                "risk_assessment": risk_assessment,
                "healthcare_alerts": healthcare_alerts,
                "supply_chain_actions": supply_chain_actions,
                "logs": self.get_all_logs()
            }
        else:
            print(f"\n✅ NO ACTION NEEDED - Air quality within safe limits\n")
            self.log_action("end_cycle", {"status": "NO_ACTION_NEEDED"})
            return {
                "status": "NO_ACTION_NEEDED",
                "risk_assessment": risk_assessment,
                "logs": self.get_all_logs()
            }

    def get_all_logs(self):
        """Collect logs from all agents for the dashboard."""
        all_logs = self.memory.copy()
        for agent in self.sub_agents.values():
            all_logs.extend(agent.memory)
        all_logs.sort(key=lambda x: x["timestamp"])
        return all_logs


class ScalestackAgent(Agent):
    """Data Specialist - fetches and normalizes environmental data."""
    def __init__(self):
        super().__init__("Scalestack Agent", "Data Specialist")

    def execute(self, scenario_data: dict):
        """Fetch and analyze environmental data."""
        print(f"📊 [{self.name}] Analyzing environmental data...")
        
        psi_data = scenario_data["psi_data"]
        
        # Calculate statistics
        max_psi = max(psi_data.values())
        avg_psi = sum(psi_data.values()) / len(psi_data)
        high_risk_regions = [region for region, psi in psi_data.items() if psi > 100]
        
        result = {
            "psi_by_region": psi_data,
            "max_psi": max_psi,
            "avg_psi": avg_psi,
            "high_risk_regions": high_risk_regions
        }
        
        self.log_action("analyze_data", result)
        
        print(f"   Max PSI: {max_psi}")
        print(f"   Avg PSI: {avg_psi:.1f}")
        if high_risk_regions:
            print(f"   High-risk regions: {', '.join(high_risk_regions)}")
        
        return result


class DynamiqMedicalAgent(Agent):
    """Clinical Expert - predicts health impacts and assesses risk."""
    def __init__(self):
        super().__init__("Dynamiq Medical Agent", "Clinical Expert")

    def execute(self, environmental_data: dict):
        """Analyze health risk and predict patient surge."""
        print(f"\n🏥 [{self.name}] Predicting healthcare surge...")
        
        current_psi = environmental_data["max_psi"]
        
        # Risk assessment logic
        if current_psi > 200:
            risk_level = "CRITICAL"
            predicted_surge = 0.75  # 75% surge
            recommendations = [
                "Activate all emergency respiratory teams",
                "Prepare 200% normal nebulizer stock",
                "Alert all CHAS clinics in affected regions"
            ]
        elif current_psi > 150:
            risk_level = "HIGH"
            predicted_surge = 0.45  # 45% surge
            recommendations = [
                "Increase respiratory specialist availability by 50%",
                "Pre-position N95 masks at clinics",
                "Activate telemedicine for non-urgent cases"
            ]
        elif current_psi > 100:
            risk_level = "MODERATE"
            predicted_surge = 0.25  # 25% surge
            recommendations = [
                "Monitor clinic capacity closely",
                "Ensure standard respiratory supplies",
                "Prepare advisory messages for vulnerable groups"
            ]
        else:
            risk_level = "LOW"
            predicted_surge = 0.05  # 5% surge
            recommendations = ["Continue normal operations"]

        result = {
            "risk_level": risk_level,
            "predicted_surge": predicted_surge,
            "current_psi": current_psi,
            "affected_regions": environmental_data["high_risk_regions"],
            "recommendations": recommendations
        }
        
        self.log_action("predict_surge", result)
        
        print(f"   Predicted surge: +{predicted_surge:.0%} patients")
        print(f"   Risk level: {risk_level}")
        
        return result


class HealthcarePreparednessAgent(Agent):
    """Logistics Coordinator - alerts clinics and prepares facilities."""
    def __init__(self):
        super().__init__("Healthcare Preparedness Agent", "Logistics Coordinator")

    def execute(self, risk_assessment: dict):
        """Send alerts to clinics in affected regions."""
        print(f"\n🏥 [{self.name}] Alerting healthcare facilities...")
        
        affected_regions = risk_assessment["affected_regions"]
        alert_msg = f"ALERT: Prepare for {risk_assessment['predicted_surge']:.0%} patient surge. PSI: {risk_assessment['current_psi']}"
        
        # Mock clinic database (in reality, this would query a real database)
        clinic_mapping = {
            "central": ["Singapore General Hospital", "Raffles Medical", "Tan Tock Seng Hospital"],
            "east": ["Changi General Hospital", "Bedok Polyclinic"],
            "north": ["Khoo Teck Puat Hospital", "Yishun Polyclinic"],
            "south": ["National University Hospital", "Alexandra Hospital"],
            "west": ["Ng Teng Fong General Hospital", "Jurong Polyclinic"]
        }
        
        clinics_alerted = []
        for region in affected_regions:
            if region in clinic_mapping:
                clinics_alerted.extend(clinic_mapping[region])
        
        result = {
            "clinics_alerted": clinics_alerted,
            "alert_message": alert_msg,
            "total_clinics": len(clinics_alerted)
        }
        
        self.log_action("send_clinic_alerts", result)
        
        print(f"   Clinics alerted: {len(clinics_alerted)}")
        for clinic in clinics_alerted[:3]:  # Show first 3
            print(f"   - {clinic}")
        if len(clinics_alerted) > 3:
            print(f"   - ... and {len(clinics_alerted) - 3} more")
        
        return result


class SupplyChainAgent(Agent):
    """Procurement Specialist - manages supply chain via Xero (mocked)."""
    def __init__(self):
        super().__init__("Supply Chain Agent", "Procurement Specialist")

    def execute(self, risk_assessment: dict):
        """Create purchase orders for medical supplies."""
        print(f"\n📦 [{self.name}] Executing supply chain actions...")
        
        risk_level = risk_assessment["risk_level"]
        
        # Determine order quantity based on risk
        if risk_level == "CRITICAL":
            order_details = {
                "n95_masks": 5000,
                "inhalers": 1000,
                "nebulizers": 200
            }
        elif risk_level == "HIGH":
            order_details = {
                "n95_masks": 2000,
                "inhalers": 500,
                "nebulizers": 100
            }
        else:
            order_details = {
                "n95_masks": 500,
                "inhalers": 200,
                "nebulizers": 50
            }

        # Mock Xero integration
        xero_po_id = f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        result = {
            "action": "Created Purchase Order in Xero",
            "po_id": xero_po_id,
            "order_details": order_details,
            "total_value": f"S${sum(order_details.values()) * 10:,}"  # Mock calculation
        }
        
        self.log_action("execute_supply_chain_action", result)
        
        print(f"   Purchase Order: {xero_po_id}")
        print(f"   N95 Masks: {order_details['n95_masks']}")
        print(f"   Inhalers: {order_details['inhalers']}")
        print(f"   Nebulizers: {order_details['nebulizers']}")
        
        return result
