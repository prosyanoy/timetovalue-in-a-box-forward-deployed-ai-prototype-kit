"""Government network-anomaly pack: flag exfiltration, scanning and credential attacks on hosts."""
from .base import Fault, Feature, RoiDefaults, Scenario

NETWORK_ANOMALY = Scenario(
    name="network-anomaly",
    title="Government network anomaly detection",
    description="Flow telemetry from agency hosts; surfaces exfiltration, scanning and brute-force activity.",
    entity_noun="host",
    entities=tuple(f"gw-{i:02d}.agency.local" for i in range(1, 9)),
    features=(
        Feature("bytes_out_kb", "outbound traffic", "KB/min", 800.0, 150.0),
        Feature("conn_per_min", "connection rate", "conn/min", 120.0, 25.0),
        Feature("distinct_ports", "distinct destination ports", "ports", 6.0, 2.0, 1.0),
        Feature("failed_logins", "failed logins", "per min", 1.0, 1.0),
        Feature("dns_entropy", "DNS query entropy", "bits", 3.2, 0.3, 0.0),
    ),
    faults=(
        Fault("exfiltration", "possible data exfiltration", {"bytes_out_kb": 9.0, "dns_entropy": 4.0},
              "isolate the host from external egress and review recent file access"),
        Fault("port_scan", "possible port scan", {"distinct_ports": 12.0, "conn_per_min": 5.0},
              "block the source at the perimeter and check firewall logs for follow-on access"),
        Fault("brute_force", "possible credential brute-force", {"failed_logins": 10.0, "conn_per_min": 3.5},
              "lock the targeted accounts and enforce MFA re-enrolment"),
    ),
    roi=RoiDefaults(
        anomalies_per_month=40,
        baseline_detect_minutes=240,
        baseline_alerts_per_month=1500,
        baseline_fp_share=0.85,
        triage_minutes_per_alert=12,
        analyst_hourly_cost=85,
        incident_cost_per_hour=450,
    ),
)
