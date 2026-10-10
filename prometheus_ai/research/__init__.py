"""Research Engineering Subsystem Package."""

from dataclasses import dataclass


@dataclass
class Hypothesis:
    """Scientific research hypothesis definition."""

    id: str
    statement: str
    control_condition: str
    treatment_condition: str
    sample_size: int
    metric_target: str
