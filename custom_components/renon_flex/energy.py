"""Daily energy estimate, independent of the transport and Home Assistant."""

from dataclasses import dataclass
from datetime import datetime

MAX_SAMPLE_GAP = 30  # Do not estimate production during extended outages.


@dataclass
class DailyEnergy:
    """Integrate the previous positive power sample using elapsed seconds."""

    day: str | None = None
    kwh: float = 0.0
    last_time: float | None = None
    last_power: float = 0.0

    def reset_sample(self) -> None:
        """Forget the sample after a failed read or a restart."""
        self.last_time = None
        self.last_power = 0.0

    def update(self, power: float, now: datetime, timestamp: float) -> float:
        """Return energy for the local calendar day, in kWh."""
        today = now.date().isoformat()
        new_day = self.day != today
        if new_day:
            self.day = today
            self.kwh = 0.0
        if self.last_time is not None:
            elapsed = timestamp - self.last_time
            if 0 <= elapsed <= MAX_SAMPLE_GAP:
                if new_day:
                    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    elapsed = min(elapsed, now.timestamp() - midnight.timestamp())
                self.kwh += self.last_power * elapsed / 3_600_000
        self.last_time = timestamp
        self.last_power = max(0.0, power)
        return round(self.kwh, 6)
