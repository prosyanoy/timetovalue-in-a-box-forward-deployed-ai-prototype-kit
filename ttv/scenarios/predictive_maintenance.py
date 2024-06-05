"""Manufacturing predictive-maintenance pack: catch failing machines before they stop the line."""
from .base import Fault, Feature, RoiDefaults, Scenario

PREDICTIVE_MAINTENANCE = Scenario(
    name="predictive-maintenance",
    title="Manufacturing predictive maintenance",
    description="Vibration, thermal and electrical telemetry from CNC machines; flags wear and faults early.",
    entity_noun="machine",
    entities=tuple(f"cnc-{i:02d}" for i in range(1, 11)),
    features=(
        Feature("vibration_mm_s", "vibration", "mm/s", 2.5, 0.5),
        Feature("bearing_temp_c", "bearing temperature", "°C", 62.0, 4.0),
        Feature("motor_current_a", "motor current", "A", 14.0, 1.2),
        Feature("rpm", "spindle speed", "rpm", 3000.0, 60.0),
        Feature("acoustic_db", "acoustic level", "dB", 68.0, 2.5),
    ),
    faults=(
        Fault("bearing_wear", "bearing wear", {"vibration_mm_s": 9.0, "acoustic_db": 5.0, "bearing_temp_c": 2.5},
              "schedule a bearing replacement at the next changeover"),
        Fault("overheating", "overheating", {"bearing_temp_c": 8.0, "motor_current_a": 5.0},
              "reduce load and inspect coolant flow before the next shift"),
        Fault("imbalance", "rotor imbalance", {"vibration_mm_s": 8.0, "rpm": -6.0},
              "stop the spindle and re-balance the tool holder"),
    ),
    roi=RoiDefaults(
        anomalies_per_month=25,
        baseline_detect_minutes=360,
        baseline_alerts_per_month=600,
        baseline_fp_share=0.7,
        triage_minutes_per_alert=20,
        analyst_hourly_cost=60,
        incident_cost_per_hour=1200,
    ),
)
